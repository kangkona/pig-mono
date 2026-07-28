"""Slash-command catalog for pig-coding-agent interactive surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InteractionCatalog:
    """Own the slash-command catalog exposed to prompt/completion surfaces."""

    agent_owner: Any

    BASE_COMMANDS = [
        "/help",
        "/exit",
        "/quit",
        "/clear",
        "/files",
        "/status",
        "/tree",
        "/fork",
        "/compact",
        "/session",
        "/sessions",
        "/skills",
        "/extensions",
        "/prompts",
        "/reload",
        "/config",
        "/queue",
        "/export",
        "/share",
        "/model",
        "/login",
        "/logout",
        "/resilience",
        "/cost",
        "/usage",
        "/new",
        "/resume",
        "/clone",
        "/name",
        "/import",
        "/copy",
        "/settings",
    ]

    def build_commands(self) -> list[str]:
        """Build the full interactive slash-command catalog."""
        owner = self.agent_owner
        commands = list(self.BASE_COMMANDS)
        if owner.skill_manager:
            for skill in owner.skill_manager.list_skills():
                commands.append(f"/skill:{skill.name}")
        if owner.prompt_manager:
            for name in owner.prompt_manager.list_templates():
                commands.append(f"/{name}")
        return commands
