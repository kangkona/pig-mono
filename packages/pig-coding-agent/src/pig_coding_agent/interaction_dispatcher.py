"""Slash-command dispatch orchestration for pig-coding-agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InteractionDispatcher:
    """Own slash-command matching and dispatch across runtime sub-surfaces."""

    agent_owner: Any
    runtime_owner: Any

    def dispatch(self, command: str) -> None:
        """Dispatch one slash command using exact command-token boundaries."""
        owner = self.agent_owner
        runtime = self.runtime_owner
        cmd = command.lower().strip()
        command_token = cmd.split(maxsplit=1)[0] if cmd else ""

        if cmd == "/exit" or cmd == "/quit":
            from .agent import SessionExitRequested

            raise SessionExitRequested()

        if cmd == "/clear":
            owner.agent.clear_history()
            runtime.clear()
            runtime.show_system("Conversation cleared")
            return

        simple_routes = runtime._build_simple_command_routes()
        handler = simple_routes.get(cmd)
        if handler is not None:
            handler()
            return

        if command_token == "/tree":
            tree_args = command.strip().split(maxsplit=1)
            runtime.flows.handle_tree_command(tree_args[1].strip() if len(tree_args) > 1 else None)
            return

        prefix_routes = runtime._build_prefix_command_routes()
        for prefix, handler in prefix_routes.items():
            if command_token == prefix or (
                prefix.endswith(":") and command_token.startswith(prefix)
            ):
                handler(command)
                return

        if cmd.startswith("/"):
            template_name = cmd.lstrip("/").split()[0]
            if owner.prompt_manager and template_name in owner.prompt_manager:
                args_str = cmd.split(maxsplit=1)[1] if " " in cmd else ""
                runtime.commands.expand_prompt(template_name, args_str)
                return

            if owner.extension_manager:
                ext_cmd = cmd.lstrip("/").split()[0]
                cmd_args = cmd.split(maxsplit=1)[1] if " " in cmd else None
                try:
                    result = owner.extension_manager.handle_command(ext_cmd, cmd_args)
                    runtime.show_text_panel(f"/{ext_cmd}", str(result))
                    return
                except (ValueError, KeyError):
                    pass

            runtime.show_error(f"Unknown command: {command}")
