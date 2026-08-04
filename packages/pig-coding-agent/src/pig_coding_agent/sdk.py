"""Embeddable SDK surface for pig-coding-agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pig_agent_core import RunAuthority, SQLiteRunStore
from pig_llm import LLM

from .agent import AgentTurnResult, CodingAgent
from .permissions import PermissionPolicy
from .project_trust import ProjectTrustDecider, ProjectTrustStore


@dataclass
class AgentSessionRuntime:
    """Stable runtime wrapper for embedding a CodingAgent in Python apps."""

    agent: CodingAgent
    run_store: SQLiteRunStore | None = None

    @property
    def session_id(self) -> str:
        return self.agent.session.id

    @property
    def workspace(self) -> Path:
        return self.agent.workspace

    @property
    def last_run_id(self) -> str | None:
        """Return the latest durable run ID when integrity recording is enabled."""
        authority = self.agent.run_authority
        return authority.last_run_id if authority is not None else None

    def prompt(self, message: str) -> str:
        """Send one prompt and return the final assistant text."""
        return self.agent.run_once(message)

    def prompt_result(self, message: str) -> AgentTurnResult:
        """Send one prompt and return text plus machine-readable permission denials."""
        return self.agent.run_once_result(message)

    def close(self, reason: str = "normal") -> None:
        """Release runtime resources and notify extensions."""
        self.agent._shutdown_extensions(reason)
        if self.run_store is not None:
            self.run_store.close()


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
    project_trust: bool | None = None,
    project_trust_decider: ProjectTrustDecider | None = None,
    project_trust_store: ProjectTrustStore | None = None,
    run_ledger_path: str | Path | None = None,
    run_owner_id: str = "python-embedder",
) -> AgentSessionRuntime:
    """Create an embeddable coding-agent runtime.

    Side-effectful tools default to deny in SDK usage. Pass
    ``PermissionPolicy.allow_all()`` or ``PermissionPolicy.confirm_all(...)`` when
    the host application intentionally wants to allow writes or shell commands.
    Project-local resources independently default to deny unless an explicit or
    persisted decision exists. Interactive hosts may provide a trust decider.
    """
    policy = permission_policy or PermissionPolicy.unattended()
    run_store = SQLiteRunStore(run_ledger_path) if run_ledger_path is not None else None
    run_authority = (
        RunAuthority(run_store, owner_id=run_owner_id) if run_store is not None else None
    )
    try:
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
            project_trust=project_trust,
            project_trust_decider=project_trust_decider,
            project_trust_store=project_trust_store,
            run_authority=run_authority,
        )
    except BaseException:
        if run_store is not None:
            run_store.close()
        raise
    return AgentSessionRuntime(agent=agent, run_store=run_store)
