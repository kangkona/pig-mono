"""Extension system for customizing agent behavior."""

import importlib.util
import inspect
from pathlib import Path
from typing import Any, Callable, Optional

from .tools import Tool


class ExtensionAPI:
    """API exposed to extensions."""

    def __init__(self, agent):
        """Initialize extension API.

        Args:
            agent: Agent instance
        """
        self.agent = agent
        self._event_handlers: dict[str, list[Callable]] = {}
        self._commands: dict[str, Callable] = {}

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

    def tool(self, **kwargs) -> Callable:
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

        def decorator(func: Callable) -> Tool:
            t = tool_decorator(**kwargs)(func)
            self.register_tool(t)
            return t

        return decorator

    def register_command(self, name: str, handler: Callable, description: str = ""):
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

    def command(self, name: str, description: str = "") -> Callable:
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

        def decorator(func: Callable) -> Callable:
            self.register_command(name, func, description)
            return func

        return decorator

    def on(self, event: str, handler: Callable) -> None:
        """Register an event handler.

        Args:
            event: Event name
            handler: Event handler function

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
        if event not in self._event_handlers:
            self._event_handlers[event] = []

        self._event_handlers[event].append(handler)

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

    def get_commands(self) -> dict[str, Callable]:
        """Get registered commands.

        Returns:
            Dictionary of command name -> handler
        """
        return self._commands.copy()


class ExtensionManager:
    """Manages extensions."""

    def __init__(self, agent):
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
            for name, obj in inspect.getmembers(module, inspect.isfunction):
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

    def handle_command(self, command: str, args: Optional[str] = None) -> Any:
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
