"""Trust boundary for project-local agent resources."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TrustDecision = Literal["allow", "deny"]


def canonical_workspace_identity(workspace: str | Path) -> str:
    """Return the stable identity used for persisted trust decisions."""
    path = Path(workspace).expanduser().resolve(strict=False)
    return os.path.normcase(str(path))


@dataclass(frozen=True)
class ProjectTrustRequest:
    """Information presented to an interactive trust decider."""

    workspace: Path
    identity: str
    resources: tuple[Path, ...]


@dataclass(frozen=True)
class ProjectTrustResponse:
    """A host decision and whether it should be persisted."""

    allow: bool
    remember: bool = True


ProjectTrustDecider = Callable[[ProjectTrustRequest], bool | ProjectTrustResponse]


class ProjectTrustStore:
    """Persist allow/deny decisions keyed by canonical workspace identity."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = (
            Path(path).expanduser()
            if path is not None
            else Path.home() / ".agents" / "project-trust.json"
        )

    def get(self, identity: str) -> TrustDecision | None:
        """Return the persisted decision for a canonical workspace identity."""
        data = self._read()
        value = data.get("decisions", {}).get(identity)
        if value == "allow":
            return "allow"
        if value == "deny":
            return "deny"
        if isinstance(value, dict):
            decision = value.get("decision")
            if decision == "allow":
                return "allow"
            if decision == "deny":
                return "deny"
        return None

    def set(self, identity: str, decision: TrustDecision) -> None:
        """Atomically persist an allow or deny decision for one workspace."""
        data = self._read()
        decisions = data.setdefault("decisions", {})
        decisions[identity] = {"decision": decision, "workspace": identity}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        temporary.replace(self.path)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "decisions": {}}
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError, TypeError):
            return {"version": 1, "decisions": {}}
        if not isinstance(data, dict) or not isinstance(data.get("decisions", {}), dict):
            return {"version": 1, "decisions": {}}
        data.setdefault("version", 1)
        data.setdefault("decisions", {})
        return data


def find_project_resources(workspace: str | Path) -> tuple[Path, ...]:
    """Return existing project-local settings, instructions, and resource roots."""
    root = Path(workspace).expanduser().resolve(strict=False)
    candidates = [
        root / ".agents" / "config.json",
        root / "AGENTS.md",
        root / "SYSTEM.md",
        root / "APPEND_SYSTEM.md",
        root / ".agents" / "AGENTS.md",
        root / ".agents" / "SYSTEM.md",
        root / ".agents" / "APPEND_SYSTEM.md",
        root / ".pi" / "AGENTS.md",
        root / ".pi" / "SYSTEM.md",
        root / ".pi" / "APPEND_SYSTEM.md",
    ]
    for namespace in (".agents", ".pi"):
        for resource in ("prompts", "skills", "packages", "extensions"):
            candidates.append(root / namespace / resource)
    current = root.parent
    visited = {root}
    while current not in visited:
        visited.add(current)
        for filename in ("AGENTS.md", "SYSTEM.md", "APPEND_SYSTEM.md"):
            candidates.extend(
                (
                    current / filename,
                    current / ".agents" / filename,
                    current / ".pi" / filename,
                )
            )
        if current == current.parent:
            break
        current = current.parent
    return tuple(path for path in candidates if path.exists())


def resolve_project_trust(
    workspace: str | Path,
    *,
    override: bool | None = None,
    decider: ProjectTrustDecider | None = None,
    store: ProjectTrustStore | None = None,
    unattended: bool = True,
) -> bool:
    """Resolve trust without reading or executing project-local resource contents.

    Explicit overrides apply to this invocation. Persisted decisions apply next.
    A decider may remember an interactive decision. With no decision source,
    unattended and embedding hosts fail closed.
    """
    if override is not None:
        return override

    identity = canonical_workspace_identity(workspace)
    trust_store = store or ProjectTrustStore()
    persisted = trust_store.get(identity)
    if persisted is not None:
        return persisted == "allow"

    resources = find_project_resources(workspace)
    if not resources:
        # No project resource needs loading now. Keep the workspace untrusted so
        # a later /reload cannot execute a newly-created extension without a
        # fresh explicit or persisted decision.
        return False

    if unattended or decider is None:
        return False

    request = ProjectTrustRequest(
        workspace=Path(identity),
        identity=identity,
        resources=resources,
    )
    response = decider(request)
    if isinstance(response, ProjectTrustResponse):
        allow = response.allow
        remember = response.remember
    else:
        allow = bool(response)
        remember = True
    if remember:
        trust_store.set(identity, "allow" if allow else "deny")
    return allow
