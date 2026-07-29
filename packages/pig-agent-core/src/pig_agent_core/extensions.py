"""Extension system for customizing agent behavior."""

import importlib.util
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, overload

from .tools import Tool

if TYPE_CHECKING:
    from .agent import Agent

CommandHandler = Callable[..., Any]
EventHandler = Callable[[dict[str, Any], "ExtensionAPI"], Any]


class ExtensionAPI:
    """API exposed to extensions."""

    def __init__(self, agent: "Agent") -> None:
        """Initialize extension API.

        Args:
            agent: Agent instance
        """
        self.agent = agent
        self._event_handlers: dict[str, list[EventHandler]] = {}
        self._commands: dict[str, CommandHandler] = {}

    def register_tool(self, tool: Tool) -> None:
        """Register a custom tool.

        Args:
            tool: Tool to register

        Example:
            @api.tool(description="My tool")
            def my_tool(arg: str) -> str:
                return f"Result: {arg}"
        """
        self.agent.add_tool(tool)

    def tool(self, **kwargs: Any) -> Callable[[CommandHandler], Tool]:
        """Decorator to register a tool.

        Args:
            **kwargs: Arguments for Tool

        Returns:
            Decorator function

        Example:
            @api.tool(description="My tool")
            def my_tool(arg: str) -> str:
                return f"Result: {arg}"
        """
        from .tools import tool as tool_decorator

        def decorator(func: CommandHandler) -> Tool:
            t = cast(Tool, tool_decorator(**kwargs)(func))
            self.register_tool(t)
            return t

        return decorator

    def register_command(self, name: str, handler: CommandHandler, description: str = "") -> None:
        """Register a slash command.

        Args:
            name: Command name (without /)
            handler: Command handler function
            description: Command description

        Example:
            @api.command("stats")
            def show_stats():
                return "Statistics..."
        """
        self._commands[name] = handler

    def command(
        self, name: str, description: str = ""
    ) -> Callable[[CommandHandler], CommandHandler]:
        """Decorator to register a command.

        Args:
            name: Command name
            description: Command description

        Returns:
            Decorator function

        Example:
            @api.command("stats", "Show statistics")
            def show_stats():
                return "Statistics..."
        """

        def decorator(func: CommandHandler) -> CommandHandler:
            self.register_command(name, func, description)
            return func

        return decorator

    @overload
    def on(self, event: str, handler: None = None) -> Callable[[EventHandler], EventHandler]: ...

    @overload
    def on(self, event: str, handler: EventHandler) -> None: ...

    def on(
        self, event: str, handler: EventHandler | None = None
    ) -> Callable[[EventHandler], EventHandler] | None:
        """Register an event handler. Can be used as decorator or direct call.

        Args:
            event: Event name
            handler: Event handler function (optional if used as decorator)

        Events:
            - tool_call_start: Before tool execution
            - tool_call_end: After tool execution
            - message_received: When message is received
            - response_generated: When response is generated
            - session_start: When session starts
            - session_end: When session ends

        Example:
            @api.on("tool_call_start")
            def on_tool_start(event, context):
                print(f"Tool {event['tool_name']} starting")
        """

        def _register(h: EventHandler) -> EventHandler:
            if event not in self._event_handlers:
                self._event_handlers[event] = []
            self._event_handlers[event].append(h)
            return h

        if handler is not None:
            _register(handler)
            return None
        else:
            return _register

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event.

        Args:
            event: Event name
            data: Event data
        """
        handlers = self._event_handlers.get(event, [])
        for handler in handlers:
            try:
                handler(data, self)
            except Exception as e:
                print(f"Error in event handler for {event}: {e}")

    def get_commands(self) -> dict[str, CommandHandler]:
        """Get registered commands.

        Returns:
            Dictionary of command name -> handler
        """
        return self._commands.copy()


class ExtensionManager:
    """Manages extensions."""

    def __init__(self, agent: "Agent") -> None:
        """Initialize extension manager.

        Args:
            agent: Agent instance
        """
        self.agent = agent
        self.api = ExtensionAPI(agent)
        self.extensions: dict[str, Any] = {}

    def load_extension(self, path: Path | str) -> None:
        """Load an extension from a Python file.

        Args:
            path: Path to extension file

        The extension file should define a function:
            def extension(api: ExtensionAPI):
                # Register tools, commands, event handlers
                pass
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Extension not found: {path}")

        # Load module
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load extension: {path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find and execute extension function
        extension_func = None

        # Look for default export or extension function
        if hasattr(module, "extension"):
            extension_func = module.extension
        elif hasattr(module, "default"):
            extension_func = module.default
        else:
            # Look for any function that takes ExtensionAPI
            for _name, obj in inspect.getmembers(module, inspect.isfunction):
                sig = inspect.signature(obj)
                params = list(sig.parameters.values())
                if params and "api" in params[0].name.lower():
                    extension_func = obj
                    break

        if extension_func is None:
            raise ValueError(
                f"Extension {path} must define an 'extension' function that takes ExtensionAPI"
            )

        # Execute extension
        extension_func(self.api)

        # Store loaded extension
        self.extensions[path.name] = module

    def discover_extensions(self, directory: Path | str) -> list[Path]:
        """Discover extensions in a directory.

        Args:
            directory: Directory to search

        Returns:
            List of extension file paths
        """
        directory = Path(directory)

        if not directory.exists():
            return []

        # Find all .py files
        extensions = []
        for path in directory.glob("**/*.py"):
            if path.name.startswith("_"):  # Skip private files
                continue
            extensions.append(path)

        return extensions

    def cleanup(self, reason: str = "normal", target_session_file: str | None = None) -> None:
        """Tear down loaded extensions for shutdown paths.

        Current extensions are plain Python modules without an explicit unload
        hook, so cleanup is intentionally conservative: clear the loaded-module
        registry and command/event handler state.
        """
        event = {"reason": reason}
        if target_session_file is not None:
            event["targetSessionFile"] = target_session_file
        self.emit_event("session_shutdown", event)
        self.extensions.clear()
        self.api._commands.clear()
        self.api._event_handlers.clear()

    def load_from_directory(self, directory: Path | str) -> None:
        """Load all extensions from a directory.

        Args:
            directory: Directory path
        """
        extensions = self.discover_extensions(directory)

        for ext_path in extensions:
            try:
                self.load_extension(ext_path)
            except Exception as e:
                print(f"Failed to load extension {ext_path}: {e}")

    def emit_event(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event to all extensions.

        Args:
            event: Event name
            data: Event data
        """
        self.api.emit(event, data)

    def handle_command(self, command: str, args: str | None = None) -> Any:
        """Handle a slash command.

        Args:
            command: Command name (without /)
            args: Command arguments

        Returns:
            Command result
        """
        commands = self.api.get_commands()

        if command not in commands:
            raise ValueError(f"Unknown command: /{command}")

        handler = commands[command]

        # Call handler with args if it accepts them
        sig = inspect.signature(handler)
        if len(sig.parameters) > 0:
            return handler(args)
        else:
            return handler()
