"""Tool permission policy for side-effectful coding-agent operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pig_agent_core.tools import ToolResult

PermissionDecision = Literal["allow", "deny"]

PERMISSION_DENIED_CODE = "tool_permission_denied"
UNATTENDED_PERMISSION_DENIAL = (
    "Permission denied: side-effectful tools are disabled in unattended mode"
)
SIDE_EFFECTFUL_TOOL_NAMES = frozenset({"write_file", "edit_file", "run_command"})


@dataclass(frozen=True)
class PermissionRequest:
    """A side-effectful operation that needs an explicit policy decision."""

    action: str
    target: str
    details: dict[str, Any] = field(default_factory=dict)


ConfirmCallback = Callable[[PermissionRequest], bool]


def permission_denial_payload(action: str, target: str, message: str) -> dict[str, str]:
    """Return the stable machine-readable permission-denial envelope."""
    return {
        "code": PERMISSION_DENIED_CODE,
        "message": message,
        "action": action,
        "target": target,
    }


def format_permission_denial(denial: dict[str, str]) -> str:
    """Return the stable plain-text representation used by unattended hosts."""
    return f"{denial['code']}: {denial['message']}"


def permission_denied_result(action: str, target: str, message: str) -> ToolResult:
    """Return a failed tool result with human and machine-readable denial data."""
    return ToolResult(
        ok=False,
        error=message,
        meta={
            "permission_denial": permission_denial_payload(action, target, message),
            "abort_batch": True,
            "terminate": True,
            "terminal_outcome": "incomplete",
            "finish_reason": "permission_denied",
        },
    )


class PermissionPolicy:
    """Uniform allow/deny/confirm gate for tool side effects."""

    def __init__(
        self,
        *,
        default: PermissionDecision = "deny",
        confirm: ConfirmCallback | None = None,
        deny_reason: str | None = None,
    ) -> None:
        self.default = default
        self.confirm = confirm
        self.deny_reason = deny_reason or "Permission denied"
        self._denials: list[dict[str, str]] = []

    @classmethod
    def allow_all(cls) -> PermissionPolicy:
        """Allow every request without prompting."""
        return cls(default="allow")

    @classmethod
    def deny_all(cls, reason: str = "Permission denied") -> PermissionPolicy:
        """Deny every request with a stable human-readable reason."""
        return cls(default="deny", deny_reason=reason)

    @classmethod
    def unattended(cls) -> PermissionPolicy:
        """Deny side effects for a non-interactive host or CLI route."""
        return cls.deny_all(UNATTENDED_PERMISSION_DENIAL)

    @classmethod
    def confirm_all(cls, confirm: ConfirmCallback) -> PermissionPolicy:
        """Ask *confirm* for every request."""
        return cls(default="deny", confirm=confirm)

    def check(self, action: str, target: str, **details: Any) -> tuple[bool, str | None]:
        """Return whether the request is allowed and a denial reason if not."""
        request = PermissionRequest(action=action, target=target, details=details)
        if self.confirm is not None:
            try:
                if self.confirm(request):
                    return True, None
                reason = self.deny_reason
            except Exception as exc:
                reason = f"Permission check failed: {exc}"
        elif self.default == "allow":
            return True, None
        else:
            reason = self.deny_reason

        self._denials.append(permission_denial_payload(action, target, reason))
        return False, reason

    def consume_denials(self) -> list[dict[str, str]]:
        """Return and clear denials recorded since the previous boundary call."""
        denials = self._denials
        self._denials = []
        return denials

    def authorize(self, action: str, target: str, **details: Any) -> ToolResult | None:
        """Return a structured denial, or ``None`` when the request is allowed."""
        allowed, reason = self.check(action, target, **details)
        if allowed:
            return None
        return permission_denied_result(action, target, reason or "Permission denied")
