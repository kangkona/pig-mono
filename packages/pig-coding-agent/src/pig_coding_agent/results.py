"""Structured result types for pig-coding-agent app/runtime boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    error: str | None = None

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)

    def get(self, key: str, default: object = None) -> object:
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

    def session(
        self,
        *,
        ok: bool,
        error: str | None = None,
        name: str | None = None,
        session_id: str | None = None,
        save_path: str | None = None,
        entries: int | None = None,
        messages_restored: int | None = None,
        current_name: str | None = None,
        chars: int | None = None,
    ) -> SessionActionResult:
        return SessionActionResult(
            ok=ok,
            error=error,
            name=name,
            session_id=session_id,
            save_path=save_path,
            entries=entries,
            messages_restored=messages_restored,
            current_name=current_name,
            chars=chars,
        )

    def tree(
        self,
        *,
        ok: bool,
        error: str | None = None,
        entry_id: str | None = None,
        label: str | None = None,
    ) -> TreeActionResult:
        return TreeActionResult(ok=ok, error=error, entry_id=entry_id, label=label)

    def setting(
        self,
        *,
        ok: bool,
        error: str | None = None,
        key: str | None = None,
        value: object | None = None,
        project_config: str | None = None,
        needs_restart: bool = False,
    ) -> SettingActionResult:
        return SettingActionResult(
            ok=ok,
            error=error,
            key=key,
            value=value,
            project_config=project_config,
            needs_restart=needs_restart,
        )

    def compact(
        self,
        *,
        ok: bool,
        error: str | None = None,
        before: int | None = None,
        after: int | None = None,
        instructions: str | None = None,
        reason: str | None = None,
        checkpoint_id: str | None = None,
    ) -> CompactActionResult:
        return CompactActionResult(
            ok=ok,
            error=error,
            before=before,
            after=after,
            instructions=instructions,
            reason=reason,
            checkpoint_id=checkpoint_id,
        )

    def export(
        self,
        *,
        ok: bool,
        error: str | None = None,
        exported: str | None = None,
        export_url: str | None = None,
    ) -> ExportActionResult:
        return ExportActionResult(
            ok=ok,
            error=error,
            exported=exported,
            export_url=export_url,
        )
