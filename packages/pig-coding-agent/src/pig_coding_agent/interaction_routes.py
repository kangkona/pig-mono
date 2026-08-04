"""Declarative slash-command routing helpers for pig-coding-agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InteractionRoutes:
    """Build the command maps used by InteractionRuntime."""

    agent_owner: Any
    runtime_owner: Any

    @staticmethod
    def parse_arg(command: str) -> str | None:
        return command.split(maxsplit=1)[1] if " " in command else None

    def build_simple_routes(self) -> dict[str, Any]:
        owner = self.agent_owner
        runtime = self.runtime_owner
        return {
            "/help": runtime.views.show_help,
            "/files": runtime.views.show_files,
            "/status": runtime.views.show_status,
            "/session": runtime.views.show_session_info,
            "/sessions": runtime.views.list_sessions,
            "/skills": runtime.views.list_skills,
            "/extensions": runtime.views.list_extensions,
            "/prompts": runtime.views.list_prompts,
            "/reload": runtime.commands.reload_resources,
            "/config": runtime.views.show_config,
            "/queue": runtime.views.show_queue,
            "/share": runtime.commands.share_session,
            "/login": runtime.commands.show_login,
            "/resilience": runtime.views.show_resilience_status,
            "/cost": lambda: runtime.views.show_cost_summary("Cost"),
            "/usage": lambda: runtime.views.show_cost_summary("Usage"),
            "/new": lambda: runtime.views.report_session_result(owner.app_actions.new_session()),
            "/clone": lambda: runtime.views.report_session_result(
                owner.app_actions.clone_session()
            ),
            "/copy": lambda: runtime.views.report_session_result(
                owner.app_actions.copy_last_message()
            ),
        }

    def build_prefix_routes(self) -> dict[str, Any]:
        owner = self.agent_owner
        runtime = self.runtime_owner
        return {
            "/fork": lambda command: runtime.views.report_session_result(
                owner.app_actions.fork_session(self.parse_arg(command))
            ),
            "/compact": lambda command: runtime.views.report_compact_result(
                owner.app_actions.compact_session(self.parse_arg(command))
            ),
            "/skill:": lambda command: runtime.commands.invoke_skill(
                command.lower().split(":", 1)[1]
            ),
            "/export": lambda command: runtime.views.report_export_result(
                owner.app_actions.export_session(self.parse_arg(command))
            ),
            "/model": lambda command: runtime.commands.switch_model(self.parse_arg(command)),
            "/logout": lambda command: runtime.commands.logout(self.parse_arg(command)),
            "/resume": lambda command: runtime.views.report_session_result(
                owner.app_actions.resume_session(
                    self.parse_arg(command) or runtime.flows.choose_session_to_resume()
                )
            ),
            "/name": lambda command: runtime.views.report_session_result(
                owner.app_actions.name_session(
                    self.parse_arg(command) or runtime.flows.edit_session_name()
                )
            ),
            "/import": lambda command: runtime.views.report_session_result(
                owner.app_actions.import_session(self.parse_arg(command))
            ),
            "/settings": lambda command: runtime.flows.show_settings(self.parse_arg(command)),
        }
