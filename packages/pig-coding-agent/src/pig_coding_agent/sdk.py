"""Embeddable SDK surface for pig-coding-agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pig_llm import LLM

from .agent import AgentTurnResult, CodingAgent
from .permissions import PermissionPolicy


@dataclass
class AgentSessionRuntime:
    """Stable runtime wrapper for embedding a CodingAgent in Python apps."""

    agent: CodingAgent

    @property
    def session_id(self) -> str:
        return self.agent.session.id

    @property
    def workspace(self) -> Path:
        return self.agent.workspace

    def prompt(self, message: str) -> str:
        """Send one prompt and return the final assistant text."""
        return self.agent.run_once(message)

    def prompt_result(self, message: str) -> AgentTurnResult:
        """Send one prompt and return text plus machine-readable permission denials."""
        return self.agent.run_once_result(message)

    def close(self, reason: str = "normal") -> None:
        """Release runtime resources and notify extensions."""
        self.agent._shutdown_extensions(reason)


def create_agent_session(
    *,
    workspace: str | Path = ".",
    llm: LLM | None = None,
    verbose: bool = False,
    session_name: str | None = None,
    session_id: str | None = None,
    session_dir: str | Path | None = None,
    enable_extensions: bool = True,
    enable_skills: bool = True,
    permission_policy: PermissionPolicy | None = None,
) -> AgentSessionRuntime:
    """Create an embeddable coding-agent runtime.

    Side-effectful tools default to deny in SDK usage. Pass
    ``PermissionPolicy.allow_all()`` or ``PermissionPolicy.confirm_all(...)`` when
    the host application intentionally wants to allow writes or shell commands.
    """
    policy = permission_policy or PermissionPolicy.unattended()
    agent = CodingAgent(
        llm=llm,
        workspace=str(workspace),
        verbose=verbose,
        session_name=session_name,
        session_id=session_id,
        session_dir=session_dir,
        enable_extensions=enable_extensions,
        enable_skills=enable_skills,
        permission_policy=policy,
    )
    return AgentSessionRuntime(agent=agent)
