"""Structured result types for pig-coding-agent app/runtime boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    error: str | None = None

    def __getitem__(self, key: str):
        return getattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)


@dataclass(frozen=True)
class SessionActionResult(ActionResult):
    name: str | None = None
    session_id: str | None = None
    save_path: str | None = None
    entries: int | None = None
    messages_restored: int | None = None
    current_name: str | None = None
    chars: int | None = None


@dataclass(frozen=True)
class TreeActionResult(ActionResult):
    entry_id: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class SettingActionResult(ActionResult):
    key: str | None = None
    value: object | None = None
    project_config: str | None = None
    needs_restart: bool = False


@dataclass(frozen=True)
class CompactActionResult(ActionResult):
    before: int | None = None
    after: int | None = None
    instructions: str | None = None
    reason: str | None = None
    checkpoint_id: str | None = None


@dataclass(frozen=True)
class ExportActionResult(ActionResult):
    exported: str | None = None
    export_url: str | None = None


class ResultFactory:
    """Factory for action result instances used between app and runtime layers."""

    def session(self, **kwargs) -> SessionActionResult:
        return SessionActionResult(**kwargs)

    def tree(self, **kwargs) -> TreeActionResult:
        return TreeActionResult(**kwargs)

    def setting(self, **kwargs) -> SettingActionResult:
        return SettingActionResult(**kwargs)

    def compact(self, **kwargs) -> CompactActionResult:
        return CompactActionResult(**kwargs)

    def export(self, **kwargs) -> ExportActionResult:
        return ExportActionResult(**kwargs)
