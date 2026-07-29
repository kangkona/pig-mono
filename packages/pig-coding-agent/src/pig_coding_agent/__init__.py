"""Interactive coding agent CLI."""

from .agent import AgentTurnResult, CodingAgent
from .permissions import (
    PERMISSION_DENIED_CODE,
    SIDE_EFFECTFUL_TOOL_NAMES,
    UNATTENDED_PERMISSION_DENIAL,
    PermissionPolicy,
    PermissionRequest,
)
from .project_trust import (
    ProjectTrustRequest,
    ProjectTrustResponse,
    ProjectTrustStore,
    canonical_workspace_identity,
    resolve_project_trust,
)
from .sdk import AgentSessionRuntime, create_agent_session
from .tools import FileTools, ShellTools, build_coding_tools

__version__ = "0.1.1"

__all__ = [
    "CodingAgent",
    "AgentTurnResult",
    "AgentSessionRuntime",
    "FileTools",
    "PERMISSION_DENIED_CODE",
    "PermissionPolicy",
    "PermissionRequest",
    "ProjectTrustRequest",
    "ProjectTrustResponse",
    "ProjectTrustStore",
    "SIDE_EFFECTFUL_TOOL_NAMES",
    "ShellTools",
    "UNATTENDED_PERMISSION_DENIAL",
    "build_coding_tools",
    "canonical_workspace_identity",
    "create_agent_session",
    "resolve_project_trust",
]
