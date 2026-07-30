"""Application-layer session/tree/settings actions for pig-coding-agent."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from pig_agent_core import Session, SessionEntry, SessionManager
from pig_llm import Message
from pig_tui import (
    SelectOption,
    TreeBrowserState,
    TreeDetailState,
    TreeOption,
    TreePathState,
    TreeSummaryState,
)

from .results import (
    CompactActionResult,
    ExportActionResult,
    SessionActionResult,
    SettingActionResult,
    TreeActionResult,
)
from .turn_lifecycle import ActiveTurnTransitionError

if TYPE_CHECKING:
    from .agent import CodingAgent


@dataclass
class AppActions:
    """Own non-UI application actions for session, tree, and settings flows."""

    _LIVE_SETTINGS = frozenset({"auto_compact", "auto_compact_threshold"})

    owner: CodingAgent

    @classmethod
    def setting_apply_mode(cls, key: str) -> str:
        """Describe when a persisted setting takes effect in the current process."""
        return "live" if key in cls._LIVE_SETTINGS else "unsupported"

    def _tree_children_by_parent(self) -> dict[str | None, list[SessionEntry]]:
        if not self.owner.session or not self.owner.session.tree.entries:
            return {}

        children_by_parent: dict[str | None, list[SessionEntry]] = {}
        for entry in self.owner.session.tree.entries.values():
            children_by_parent.setdefault(entry.parent_id, []).append(entry)

        for children in children_by_parent.values():
            children.sort(key=lambda entry: (entry.timestamp, entry.id))
        return children_by_parent

    @staticmethod
    def _entry_preview(entry: SessionEntry, *, limit: int) -> str:
        return entry.content[:limit].replace("\n", " ")

    def _entry_display_label(
        self,
        entry: SessionEntry,
        *,
        preview_limit: int,
        depth: int | None = None,
        include_metadata_label: bool = True,
    ) -> str:
        indent = "  " * min(depth, 5) if depth is not None else ""
        label = entry.metadata.get("label") if include_metadata_label else None
        label_text = f" {{{label}}}" if label else ""
        preview = self._entry_preview(entry, limit=preview_limit)
        return f"{indent}[{entry.role}]{label_text} {preview}..."

    def _entry_path_labels(self, entry_id: str, *, preview_limit: int = 24) -> tuple[str, ...]:
        if not self.owner.session:
            return ()
        return tuple(
            self._entry_display_label(
                path_entry,
                preview_limit=preview_limit,
                include_metadata_label=False,
            )
            for path_entry in self.owner.session.tree.get_path_to_entry(entry_id)
        )

    def build_tree_selector_options(self) -> list[SelectOption]:
        children_by_parent = self._tree_children_by_parent()
        if not children_by_parent:
            return []

        options: list[SelectOption] = []

        def walk(parent_id: str | None, depth: int) -> None:
            for entry in children_by_parent.get(parent_id, []):
                label = entry.metadata.get("label")
                options.append(
                    SelectOption(
                        value=entry.id,
                        label=self._entry_display_label(
                            entry,
                            preview_limit=60,
                            depth=depth,
                        ),
                        description=entry.id[:8],
                        initial_value=label or "",
                    )
                )
                walk(entry.id, depth + 1)

        walk(None, 0)
        return options

    def build_tree_browser_entries(self) -> list[TreeOption]:
        children_by_parent = self._tree_children_by_parent()
        if not children_by_parent:
            return []

        entries: list[TreeOption] = []

        def walk(parent_id: str | None, depth: int) -> None:
            for entry in children_by_parent.get(parent_id, []):
                preview = self._entry_preview(entry, limit=60)
                label = entry.metadata.get("label")
                is_branch_point = len(children_by_parent.get(entry.id, [])) > 1
                path = self.owner.session.tree.get_path_to_entry(entry.id)
                detail_state = TreeDetailState(
                    role=entry.role,
                    short_id=entry.id[:8],
                    depth=depth,
                    children_count=len(children_by_parent.get(entry.id, [])),
                    label=label,
                    preview=preview,
                    path_length=len(path),
                    path_labels=self._entry_path_labels(entry.id),
                )
                entries.append(
                    TreeOption(
                        value=entry.id,
                        label=self._entry_display_label(entry, preview_limit=60),
                        description=entry.id[:8],
                        depth=depth,
                        is_current=entry.id == self.owner.session.tree.current_id,
                        is_branch_point=is_branch_point,
                        detail_state=detail_state,
                    )
                )
                walk(entry.id, depth + 1)

        walk(None, 0)
        return entries

    def session_list_items(self, limit: int = 20) -> tuple[list[tuple[str, str | None]], bool]:
        session_mgr = SessionManager(self.owner.workspace, session_dir=self.owner.sessions_dir)
        sessions = session_mgr.list_sessions(limit=limit)
        items: list[tuple[str, str | None]] = []
        for info in sessions:
            items.append(
                (
                    str(info.session_name),
                    f"{session_mgr._format_age(info.modified)} ({info.entries} entries)",
                )
            )
        return items, len(sessions) == limit

    def session_info(self) -> dict[str, Any] | None:
        if not self.owner.session:
            return None
        return self.owner.session.get_info()

    def status_view_data(self) -> dict[str, Any]:
        info = self.owner.session.get_info() if self.owner.session else None
        agents_md = self.owner.context_manager.find_context_files("AGENTS.md")
        return {
            "model": self.owner.agent.llm.config.model,
            "provider": self.owner.agent.llm.config.provider,
            "workspace": str(self.owner.workspace),
            "messages": len(self.owner.agent.history),
            "tools": len(self.owner.agent.registry),
            "session_name": self.owner.session.name if self.owner.session else None,
            "session_entries": info["entries"] if info else None,
            "session_path_length": info["current_path_length"] if info else None,
            "session_branches": info["branches"] if info else None,
            "skills": len(self.owner.skill_manager) if self.owner.skill_manager else None,
            "extensions": (
                len(self.owner.extension_manager.extensions),
                len(self.owner.extension_manager.api.get_commands()),
            )
            if self.owner.extension_manager
            else None,
            "prompts": len(self.owner.prompt_manager) if self.owner.prompt_manager else None,
            "context_files": len(agents_md) if agents_md else None,
        }

    def tree_panel_items(self) -> tuple[list[tuple[str, str | None]], int, int]:
        if not self.owner.session:
            return [], 0, 0
        path = self.owner.session.get_current_conversation()
        items: list[tuple[str, str | None]] = []
        for i, entry in enumerate(path):
            items.append(
                (
                    self._entry_display_label(entry, preview_limit=60, depth=i),
                    None,
                )
            )
        return items, len(self.owner.session.tree.entries), len(path)

    def tree_browser_view_data(
        self,
        selected_entry_id: str | None = None,
        *,
        scope: str = "all",
    ) -> dict[str, Any] | None:
        if not self.owner.session:
            return None
        current_id = self.owner.session.tree.current_id
        target_id = selected_entry_id or current_id
        options = self.build_tree_browser_entries()
        anchor_label = None
        breadcrumbs: tuple[str, ...] = ()
        selected_label = None
        if target_id is not None and target_id in self.owner.session.tree.entries:
            target = self.owner.session.tree.entries[target_id]
            anchor_label = self._entry_display_label(
                target,
                preview_limit=40,
                include_metadata_label=False,
            )
            selected_label = anchor_label
            breadcrumbs = self._entry_path_labels(target_id)

        if scope == "children" and target_id is not None:
            options = [
                option
                for option in options
                if self.owner.session.tree.entries[option.value].parent_id == target_id
            ]
        elif scope == "siblings" and target_id is not None:
            sibling_target = self.owner.session.tree.entries.get(target_id)
            parent_id = sibling_target.parent_id if sibling_target is not None else None
            options = [
                option
                for option in options
                if self.owner.session.tree.entries[option.value].parent_id == parent_id
            ]

        if target_id is not None:
            options = [replace(option, is_anchor=option.value == target_id) for option in options]

        default_index = next(
            (index for index, option in enumerate(options) if option.value == target_id),
            0,
        )
        info = self.owner.session.get_info()
        summary_state = TreeSummaryState(
            visible_count=len(options),
            total_count=info["entries"],
            branch_count=info["branches"],
            current_path_length=info["current_path_length"],
            current_entry_short_id=str(current_id)[:8] if current_id else None,
        )
        return {
            "options": options,
            "default_index": default_index,
            "state": TreeBrowserState(
                scope=scope,
                current_entry_id=current_id,
                selected_entry_id=target_id,
                anchor_entry_id=target_id if scope != "all" else None,
                breadcrumbs=breadcrumbs,
                anchor_label=anchor_label,
                summary=summary_state.summary_text,
                path_state=TreePathState(
                    parts=breadcrumbs,
                    selected_label=selected_label,
                    anchor_label=anchor_label,
                ),
                summary_state=summary_state,
            ),
            "note": (
                f"Scope: {scope} | "
                f"Current path: {info['current_path_length']} entries | "
                f"Branches: {info['branches']} | "
                f"Total entries: {info['entries']}"
            ),
        }

    def parent_tree_entry_id(self, entry_id_or_prefix: str) -> str | None:
        if not self.owner.session:
            return None
        entry_id = self.resolve_entry_id(entry_id_or_prefix)
        if entry_id is None:
            return None
        entry = self.owner.session.tree.entries[entry_id]
        return entry.parent_id or entry.id

    def resolve_entry_id(self, entry_id_or_prefix: str) -> str | None:
        if not self.owner.session:
            return None
        if entry_id_or_prefix in self.owner.session.tree.entries:
            return entry_id_or_prefix
        matches = [
            entry_id
            for entry_id in self.owner.session.tree.entries
            if entry_id.startswith(entry_id_or_prefix)
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def label_tree(self, entry_id_or_prefix: str, label: str) -> TreeActionResult:
        try:
            with self.owner.turn_lifecycle.transition("label the session tree"):
                if not self.owner.session:
                    return self.owner.result_factory.tree(ok=False, error="No session loaded")

                entry_id = self.resolve_entry_id(entry_id_or_prefix.strip())
                if entry_id is None:
                    return self.owner.result_factory.tree(
                        ok=False,
                        error=(
                            f"Session entry not found or ambiguous: {entry_id_or_prefix.strip()}"
                        ),
                    )

                normalized_label = label.strip()
                if not normalized_label:
                    return self.owner.result_factory.tree(
                        ok=False, error="Tree label cannot be empty"
                    )

                entry = self.owner.session.tree.entries[entry_id]
                entry.metadata["label"] = normalized_label
                self.owner.session.updated_at = datetime.utcnow()
                self.owner.session.save()
                return self.owner.result_factory.tree(
                    ok=True, entry_id=entry_id, label=normalized_label
                )
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.tree(ok=False, error=str(exc))

    def rebuild_history_from_session(self) -> None:
        system = None
        if self.owner.agent.history and self.owner.agent.history[0].role == "system":
            system = self.owner.agent.history[0]
        history: list[Message] = []
        if system is not None:
            history.append(system)
        if self.owner.session:
            for entry in self.owner.session.get_current_conversation():
                if entry.role == "system" and not (entry.metadata or {}).get("compacted"):
                    continue
                history.append(
                    Message(
                        role=cast(
                            Literal["system", "developer", "user", "assistant", "tool"],
                            entry.role,
                        ),
                        content=entry.content,
                        metadata=entry.metadata or None,
                    )
                )
        self.owner.agent.history = history
        if self.owner.session:
            self.owner.agent.session = self.owner.session
            if hasattr(self.owner.session, "usage_ledger"):
                self.owner.agent.usage = self.owner.session.usage_ledger

    def switch_tree(self, entry_id_or_prefix: str) -> TreeActionResult:
        try:
            with self.owner.turn_lifecycle.transition("switch session tree branches"):
                if not self.owner.session:
                    return self.owner.result_factory.tree(ok=False, error="No session loaded")

                entry_id = self.resolve_entry_id(entry_id_or_prefix)
                if entry_id is None:
                    return self.owner.result_factory.tree(
                        ok=False,
                        error=(f"Session entry not found or ambiguous: {entry_id_or_prefix}"),
                    )

                previous_session_file = str(self.owner.session.save())
                if self.owner.extension_manager:
                    self.owner.extension_manager.emit_event(
                        "session_shutdown",
                        {
                            "reason": "tree",
                            "targetSessionFile": previous_session_file,
                            "targetEntryId": entry_id,
                        },
                    )
                    self.owner.extension_manager.extensions.clear()
                    self.owner.extension_manager.api._commands.clear()
                    self.owner.extension_manager.api._event_handlers.clear()

                self.owner.session.branch_to(entry_id)
                self.owner.agent.session = self.owner.session
                if hasattr(self.owner.session, "usage_ledger"):
                    self.owner.agent.usage = self.owner.session.usage_ledger
                self.rebuild_history_from_session()

                if self.owner.extension_manager:
                    self.owner._load_extensions()
                    self.owner.extension_manager.emit_event(
                        "session_start",
                        {
                            "reason": "tree",
                            "previousSessionFile": previous_session_file,
                            "entryId": entry_id,
                        },
                    )

                return self.owner.result_factory.tree(ok=True, entry_id=entry_id)
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.tree(ok=False, error=str(exc))

    def switch_to_session(self, new_session: Session, reason: str) -> None:
        with self.owner.turn_lifecycle.transition("switch sessions"):
            previous_session_file = str(self.owner.session.save()) if self.owner.session else None
            if self.owner.extension_manager:
                self.owner.extension_manager.cleanup(
                    reason=reason,
                    target_session_file=previous_session_file,
                )
            self.owner.session = new_session
            self.owner.agent.session = self.owner.session
            if hasattr(self.owner.session, "usage_ledger"):
                self.owner.agent.usage = self.owner.session.usage_ledger
            self.rebuild_history_from_session()
            if self.owner.extension_manager:
                self.owner._load_extensions()
                self.owner.extension_manager.emit_event(
                    "session_start",
                    {"reason": reason, "previousSessionFile": previous_session_file},
                )

    def fork_tree_entry(
        self,
        entry_id_or_prefix: str,
        fork_name: str | None = None,
    ) -> SessionActionResult:
        try:
            with self.owner.turn_lifecycle.transition("fork the session tree"):
                if not self.owner.session:
                    return self.owner.result_factory.session(ok=False, error="No session loaded")

                entry_id = self.resolve_entry_id(entry_id_or_prefix.strip())
                if entry_id is None:
                    return self.owner.result_factory.session(
                        ok=False,
                        error=(
                            f"Session entry not found or ambiguous: {entry_id_or_prefix.strip()}"
                        ),
                    )

                name = fork_name or f"{self.owner.session.name}-fork"
                previous_session_file = self.owner.session.save()
                fork = self.owner.session.fork(entry_id, name)
                save_path = fork.save()
                if self.owner.extension_manager:
                    self.owner.extension_manager.cleanup(
                        reason="fork",
                        target_session_file=str(previous_session_file),
                    )

                self.owner.session = fork
                self.owner.agent.session = self.owner.session
                self.rebuild_history_from_session()

                if self.owner.extension_manager:
                    self.owner._load_extensions()
                    self.owner.extension_manager.emit_event(
                        "session_start",
                        {"reason": "fork", "previousSessionFile": str(previous_session_file)},
                    )

                return self.owner.result_factory.session(
                    ok=True,
                    name=name,
                    entries=len(fork.tree.entries),
                    save_path=str(save_path),
                    session_id=fork.id,
                )
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.session(ok=False, error=str(exc))

    def fork_session(self, fork_name: str | None) -> SessionActionResult:
        try:
            with self.owner.turn_lifecycle.transition("fork the current session"):
                if not self.owner.session:
                    return self.owner.result_factory.session(ok=False, error="No session loaded")

                conversation = self.owner.session.get_current_conversation()
                if not conversation:
                    return self.owner.result_factory.session(ok=False, error="No messages to fork")
                return self.fork_tree_entry(conversation[-1].id, fork_name)
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.session(ok=False, error=str(exc))

    def new_session(self) -> SessionActionResult:
        try:
            with self.owner.turn_lifecycle.transition("create a new session"):
                new_session = Session(
                    name="coding-session",
                    workspace=str(self.owner.workspace),
                    auto_save=True,
                    session_dir=self.owner.sessions_dir,
                )
                self.switch_to_session(new_session, reason="new")
                return self.owner.result_factory.session(
                    ok=True,
                    session_id=new_session.id,
                    name=new_session.name,
                )
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.session(ok=False, error=str(exc))

    def resume_session(self, name_or_id: str | None) -> SessionActionResult:
        try:
            with self.owner.turn_lifecycle.transition("resume a session"):
                if not name_or_id:
                    return self.owner.result_factory.session(
                        ok=False, error="Missing session selector"
                    )
                session_mgr = SessionManager(
                    self.owner.workspace, session_dir=self.owner.sessions_dir
                )
                path = session_mgr.find_session(name_or_id)
                if not path or not path.exists():
                    return self.owner.result_factory.session(
                        ok=False, error=f"Session not found: {name_or_id}"
                    )
                try:
                    loaded = Session.load(path)
                except Exception as exc:
                    return self.owner.result_factory.session(
                        ok=False, error=f"Failed to load session: {exc}"
                    )
                self.switch_to_session(loaded, reason="resume")
                return self.owner.result_factory.session(
                    ok=True,
                    name=loaded.name,
                    session_id=loaded.id,
                    messages_restored=len(self.owner.agent.history),
                )
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.session(ok=False, error=str(exc))

    def clone_session(self) -> SessionActionResult:
        try:
            with self.owner.turn_lifecycle.transition("clone the current session"):
                if not self.owner.session:
                    return self.owner.result_factory.session(ok=False, error="No session loaded")
                conversation = self.owner.session.get_current_conversation()
                if not conversation:
                    return self.owner.result_factory.session(ok=False, error="No messages to clone")
                clone = self.owner.session.fork(
                    conversation[-1].id, f"{self.owner.session.name}-clone"
                )
                save_path = clone.save()
                self.switch_to_session(clone, reason="fork")
                return self.owner.result_factory.session(
                    ok=True,
                    name=clone.name,
                    session_id=clone.id,
                    save_path=str(save_path),
                )
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.session(ok=False, error=str(exc))

    def name_session(self, name: str | None) -> SessionActionResult:
        try:
            with self.owner.turn_lifecycle.transition("name the current session"):
                if not self.owner.session:
                    return self.owner.result_factory.session(ok=False, error="No session loaded")
                if not name:
                    return self.owner.result_factory.session(
                        ok=False,
                        error="Missing name",
                        current_name=self.owner.session.name,
                    )
                self.owner.session.name = name
                self.owner.session.save()
                return self.owner.result_factory.session(ok=True, name=name)
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.session(ok=False, error=str(exc))

    def import_session(self, file_path: str | None) -> SessionActionResult:
        try:
            with self.owner.turn_lifecycle.transition("import a session"):
                if not file_path:
                    return self.owner.result_factory.session(
                        ok=False, error="Usage: /import <path-to-session.jsonl>"
                    )
                path = Path(file_path).expanduser()
                if not path.exists():
                    return self.owner.result_factory.session(
                        ok=False, error=f"File not found: {path}"
                    )
                try:
                    loaded = Session.load(path)
                except Exception as exc:
                    return self.owner.result_factory.session(
                        ok=False, error=f"Failed to import session: {exc}"
                    )
                loaded.session_dir = self.owner.sessions_dir
                loaded._save_path = None
                save_path = loaded.save()
                self.switch_to_session(loaded, reason="resume")
                return self.owner.result_factory.session(
                    ok=True,
                    name=loaded.name,
                    session_id=loaded.id,
                    save_path=str(save_path),
                    messages_restored=len(self.owner.agent.history),
                )
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.session(ok=False, error=str(exc))

    def set_setting(self, key: str, raw_value: str) -> SettingActionResult:
        """Validate and persist one runtime-backed project setting."""
        raw = raw_value.strip()
        if key not in self.owner._EDITABLE_SETTINGS:
            return self.owner.result_factory.setting(
                ok=False,
                error=(
                    f"Unknown or read-only setting: {key}. "
                    f"Editable: {', '.join(self.owner._EDITABLE_SETTINGS)}"
                ),
            )

        current = getattr(self.owner.config_manager.load_config(), key, None)
        try:
            if isinstance(current, bool):
                normalized = raw.lower()
                if normalized in {"1", "true", "yes", "on"}:
                    value: object = True
                elif normalized in {"0", "false", "no", "off"}:
                    value = False
                else:
                    return self.owner.result_factory.setting(
                        ok=False,
                        error=(
                            f"Invalid value for {key}: {raw!r}. "
                            "Use true/false, yes/no, on/off, or 1/0."
                        ),
                    )
            elif isinstance(current, int) and not isinstance(current, bool):
                value = int(raw)
            elif isinstance(current, float):
                value = float(raw)
            else:
                value = raw
        except ValueError:
            return self.owner.result_factory.setting(
                ok=False, error=f"Invalid value for {key}: {raw!r}"
            )

        if key == "auto_compact_threshold":
            if not isinstance(value, int | float) or not (0.0 <= value <= 1.0):
                return self.owner.result_factory.setting(
                    ok=False,
                    error="auto_compact_threshold must be between 0.0 and 1.0",
                )

        try:
            self.owner.config_manager.set_config_value(key, value)
        except PermissionError as exc:
            return self.owner.result_factory.setting(ok=False, error=str(exc))
        return self.owner.result_factory.setting(
            ok=True,
            key=key,
            value=value,
            project_config=str(self.owner.config_manager.project_config),
            needs_restart=self.setting_apply_mode(key) != "live",
        )

    def compact_session(
        self,
        instructions: str | None,
        *,
        reason: str = "manual",
        before_tokens: int | None = None,
    ) -> CompactActionResult:
        try:
            with self.owner.turn_lifecycle.transition("compact the current session"):
                if not self.owner.session:
                    return self.owner.result_factory.compact(ok=False, error="No session loaded")

                before = len(self.owner.session.tree.entries)
                previous_checkpoint = getattr(
                    self.owner.session, "last_compaction_checkpoint", None
                )
                previous_checkpoint_id = previous_checkpoint.id if previous_checkpoint else None
                try:
                    compacted = self.owner.agent.compact_session(
                        instructions,
                        reason=reason,
                        before_tokens=before_tokens,
                    )
                except Exception as exc:
                    return self.owner.result_factory.compact(
                        ok=False,
                        error=f"Compaction failed: {exc}",
                        before=before,
                        after=before,
                        instructions=instructions,
                        reason=reason,
                    )
                checkpoint = getattr(self.owner.session, "last_compaction_checkpoint", None)
                checkpoint_id = (
                    checkpoint.id
                    if checkpoint and checkpoint.id != previous_checkpoint_id
                    else None
                )
                return self.owner.result_factory.compact(
                    ok=True,
                    before=before,
                    after=len(compacted),
                    instructions=instructions,
                    reason=reason,
                    checkpoint_id=checkpoint_id,
                )
        except ActiveTurnTransitionError as exc:
            return self.owner.result_factory.compact(ok=False, error=str(exc))

    def export_session(self, filename: str | None) -> ExportActionResult:
        if not self.owner.session:
            return self.owner.result_factory.export(ok=False, error="No session to export")

        from pig_agent_core import SessionExporter

        if filename:
            output_path = Path(filename)
        else:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(f"{self.owner.session.name}_{timestamp}.html")

        try:
            exported = SessionExporter.export_to_html(
                self.owner.session, output_path, title=self.owner.session.name
            )
        except Exception as e:
            return self.owner.result_factory.export(ok=False, error=f"Export failed: {e}")

        return self.owner.result_factory.export(
            ok=True,
            exported=str(exported),
            export_url=f"file://{exported.absolute()}",
        )

    def copy_last_message(self) -> SessionActionResult:
        last = None
        for msg in reversed(self.owner.agent.history):
            if msg.role == "assistant" and msg.content:
                last = msg.content
                break
        if not last:
            return self.owner.result_factory.session(ok=False, error="No assistant message to copy")
        if self.owner._copy_to_clipboard(last):
            return self.owner.result_factory.session(ok=True, chars=len(last))
        return self.owner.result_factory.session(
            ok=False,
            error="Clipboard not available (install pbcopy/xclip/wl-copy)",
        )
