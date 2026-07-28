"""Tool permission policy for side-effectful coding-agent operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

PermissionDecision = Literal["allow", "deny"]


@dataclass(frozen=True)
class PermissionRequest:
    """A side-effectful operation that needs an explicit policy decision."""

    action: str
    target: str
    details: dict[str, Any] = field(default_factory=dict)


ConfirmCallback = Callable[[PermissionRequest], bool]


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

    @classmethod
    def allow_all(cls) -> PermissionPolicy:
        """Allow every request without prompting."""
        return cls(default="allow")

    @classmethod
    def deny_all(cls, reason: str = "Permission denied") -> PermissionPolicy:
        """Deny every request with a stable human-readable reason."""
        return cls(default="deny", deny_reason=reason)

    @classmethod
    def confirm_all(cls, confirm: ConfirmCallback) -> PermissionPolicy:
        """Ask *confirm* for every request."""
        return cls(default="deny", confirm=confirm)

    def check(self, action: str, target: str, **details: Any) -> tuple[bool, str | None]:
        """Return whether the request is allowed and a denial reason if not."""
        request = PermissionRequest(action=action, target=target, details=details)
        if self.confirm is not None:
            try:
                return (True, None) if self.confirm(request) else (False, self.deny_reason)
            except Exception as exc:
                return False, f"Permission check failed: {exc}"
        if self.default == "allow":
            return True, None
        return False, self.deny_reason
