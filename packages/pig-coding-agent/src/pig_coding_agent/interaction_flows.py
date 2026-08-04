"""Selector/editor interaction flows for pig-coding-agent commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pig_tui import (
    EditorSession,
    SelectionEditorSession,
    SelectionSession,
    SelectOption,
    StatusMessage,
    TreeBrowserSession,
)


@dataclass
class InteractionFlows:
    """Own interactive selector/editor flows coordinated by InteractionRuntime."""

    agent_owner: Any
    runtime_owner: Any

    def choose_session_to_resume(self) -> str | None:
        owner = self.agent_owner
        session_mgr = owner._session_manager()
        sessions = session_mgr.list_sessions(limit=20)
        if not sessions:
            self.runtime_owner.views.show_no_sessions_available()
            return None

        runtime = self.runtime_owner._build_terminal_runtime()
        options = [
            SelectOption(
                value=info.path.stem,
                label=info.session_name,
                description=f"{session_mgr._format_age(info.modified)} ({info.entries} entries)",
            )
            for info in sessions
        ]
        selected = runtime.run_selection_session(
            SelectionSession(
                title="Resume Session",
                options=options,
                note="Enter a number or exact label/value to resume a session.",
            )
        )
        return selected.value if selected is not None else None

    def edit_session_name(self) -> str | None:
        owner = self.agent_owner
        if not owner.session:
            self.runtime_owner.show_error("No session loaded")
            return None
        runtime = self.runtime_owner._build_terminal_runtime()
        value = runtime.run_editor_session(
            EditorSession(
                title="Rename Session",
                initial_value=owner.session.name,
                note="Enter the new display name for this session.",
            )
        ).strip()
        return value or None

    @staticmethod
    def tree_actions() -> list[SelectOption]:
        """Return the actions available for a selected session-tree entry."""
        return [
            SelectOption("switch", "Switch branch", "Move the active conversation path here"),
            SelectOption("label", "Label entry", "Rename or annotate the selected entry"),
            SelectOption(
                "fork",
                "Fork session here",
                "Create a new session from this history node",
            ),
            SelectOption(
                "parent",
                "Jump parent",
                "Recenter the browser on the selected entry's parent",
            ),
            SelectOption(
                "current",
                "Jump current",
                "Recenter the browser on the active conversation tip",
            ),
            SelectOption(
                "children",
                "Show children",
                "Limit the browser to the selected entry's direct children",
            ),
            SelectOption(
                "siblings",
                "Show siblings",
                "Limit the browser to entries sharing the selected entry's parent",
            ),
            SelectOption(
                "all",
                "Show full tree",
                "Return to the full session tree browser",
            ),
            SelectOption(
                "close",
                "Close browser",
                "Return to the conversation without changing branches",
            ),
        ]

    def browse_tree(self) -> None:
        """Run the prompt-based tree browser until an action closes it."""
        owner = self.agent_owner
        if not owner.session:
            self.runtime_owner.show_error("No session loaded")
            return

        runtime = self.runtime_owner._build_terminal_runtime()
        selected_entry_id: str | None = None
        scope = "all"

        while True:
            browser = owner.app_actions.tree_browser_view_data(selected_entry_id, scope=scope)
            if browser is None:
                self.runtime_owner.show_status(StatusMessage("info", "No session entries found"))
                return
            if not browser["options"]:
                if scope != "all":
                    self.runtime_owner.show_status(
                        StatusMessage(
                            "info",
                            f"No {scope} entries found; returning to the full session tree",
                        )
                    )
                    scope = "all"
                    continue
                self.runtime_owner.show_status(StatusMessage("info", "No session entries found"))
                return

            result = runtime.run_tree_browser_session(
                TreeBrowserSession(
                    title="Session Tree",
                    entries=browser["options"],
                    actions=self.tree_actions(),
                    action_title="Actions",
                    state=browser["state"],
                    note=browser["note"],
                    default_entry_index=browser["default_index"],
                )
            )
            if result.entry is None or result.action is None:
                return

            selected_entry_id = result.entry.value

            if result.action.value == "close":
                return

            if result.action.value == "switch":
                self.runtime_owner.views.report_tree_result(
                    owner.app_actions.switch_tree(selected_entry_id)
                )
                return

            if result.action.value == "label":
                current_label = owner.session.tree.entries[selected_entry_id].metadata.get("label")
                label = self.edit_tree_label(current_label)
                if label is None:
                    continue
                self.label_tree_entry(selected_entry_id, label)
                continue

            if result.action.value == "fork":
                self.runtime_owner.views.report_session_result(
                    owner.app_actions.fork_tree_entry(selected_entry_id)
                )
                return

            if result.action.value == "parent":
                selected_entry_id = owner.app_actions.parent_tree_entry_id(selected_entry_id)
                scope = "all"
                continue

            if result.action.value == "current":
                selected_entry_id = owner.session.tree.current_id
                scope = "all"
                continue

            if result.action.value == "children":
                scope = "children"
                continue

            if result.action.value == "siblings":
                scope = "siblings"
                continue

            if result.action.value == "all":
                scope = "all"
                continue

    def edit_tree_label(self, current_label: str | None = None) -> str | None:
        runtime = self.runtime_owner._build_terminal_runtime()
        value = runtime.run_editor_session(
            EditorSession(
                title="Edit Tree Label",
                initial_value=current_label or "",
                note="Enter the label for the selected session entry.",
            )
        ).strip()
        return value or None

    def choose_and_edit_tree_label(self) -> tuple[str | None, str | None]:
        owner = self.agent_owner
        options = owner.app_actions.build_tree_selector_options()
        if not options:
            self.runtime_owner.show_status(StatusMessage("info", "No session entries found"))
            return None, None
        runtime = self.runtime_owner._build_terminal_runtime()
        result = runtime.run_selection_editor_session(
            SelectionEditorSession(
                title="Label Session Entry",
                options=options,
                edit_title="Edit Tree Label",
                edit_note="Enter the label for the selected session entry.",
                use_selected_description_as_initial=False,
            )
        )
        return (result.option.value if result.option else None, result.edited_value)

    def label_tree_entry(self, entry_id_or_prefix: str, label: str) -> None:
        self.runtime_owner.views.report_tree_result(
            self.agent_owner.app_actions.label_tree(entry_id_or_prefix, label)
        )

    def handle_tree_label_command(self, raw_args: str | None) -> None:
        owner = self.agent_owner
        if not raw_args:
            entry_id, label = self.choose_and_edit_tree_label()
            if entry_id is None or label is None:
                return
            self.label_tree_entry(entry_id, label)
            return

        parsed = self.runtime_owner._split_required_arg_pair(raw_args)
        if parsed is not None:
            entry_id_or_prefix, label = parsed
            self.label_tree_entry(entry_id_or_prefix, label)
            return

        entry_id = owner.app_actions.resolve_entry_id(raw_args.strip())
        if entry_id is None:
            self.runtime_owner.show_error(
                f"Session entry not found or ambiguous: {raw_args.strip()}"
            )
            return
        current_label = owner.session.tree.entries[entry_id].metadata.get("label")
        label = self.edit_tree_label(current_label)
        if label is None:
            return
        self.label_tree_entry(entry_id, label)

    def handle_tree_command(self, raw_args: str | None) -> None:
        owner = self.agent_owner
        if raw_args:
            if raw_args == "label" or raw_args.startswith("label "):
                _, _, rest = raw_args.partition(" ")
                self.handle_tree_label_command(rest.strip() or None)
                return
            self.runtime_owner.views.report_tree_result(owner.app_actions.switch_tree(raw_args))
            return

        if self.runtime_owner._terminal_runtime is not None:
            self.browse_tree()
            return

        self.runtime_owner.views.show_tree()

    def settings_options(self) -> list[SelectOption]:
        """Build selector options for settings with live runtime support."""
        owner = self.agent_owner
        cfg = owner.config_manager.load_config()
        return [
            SelectOption(
                value=key,
                label=key,
                description=(
                    f"{getattr(cfg, key, '?')} [{owner.app_actions.setting_apply_mode(key)}]"
                ),
                initial_value=str(getattr(cfg, key, "?")),
            )
            for key in owner._EDITABLE_SETTINGS
        ]

    def edit_setting_interactively(self) -> None:
        """Prompt for one project-scoped setting and persist the selected value."""
        owner = self.agent_owner
        runtime = self.runtime_owner._build_terminal_runtime()
        result = runtime.run_selection_editor_session(
            SelectionEditorSession(
                title="Edit Setting",
                options=self.settings_options(),
                edit_title="Edit Setting Value",
                edit_note=(
                    f"Project: {owner.config_manager.project_config}. "
                    f"Global fallback: {owner.config_manager.global_config}. "
                    "The project value applies immediately. "
                    "Booleans accept true/false, yes/no, on/off, or 1/0."
                ),
            )
        )
        if result.option is None or result.edited_value is None:
            return
        self.runtime_owner.views.report_setting_result(
            owner.app_actions.set_setting(result.option.value, result.edited_value)
        )

    def show_settings(self, args: str | None = None) -> None:
        """Show settings or apply one supported project-scoped value."""
        owner = self.agent_owner
        if args:
            parsed = self.runtime_owner._split_required_arg_pair(args)
            if parsed is None:
                self.runtime_owner.show_error("Usage: /settings <key> <value>")
                return
            key, value = parsed
            self.runtime_owner.views.report_setting_result(
                owner.app_actions.set_setting(key, value)
            )
            return

        if self.runtime_owner._terminal_runtime is not None:
            self.edit_setting_interactively()
            return

        self.runtime_owner.views.show_settings()
