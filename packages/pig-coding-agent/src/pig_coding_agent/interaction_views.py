"""Presentation/reporting helpers for pig-coding-agent interaction surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pig_tui import StatusMessage

from .presentation import (
    build_config_panel,
    build_cost_panel,
    build_extensions_panel,
    build_files_panel,
    build_help_panel,
    build_prompts_panel,
    build_queue_panel,
    build_resilience_panel,
    build_session_info_panel,
    build_session_tree_panel,
    build_sessions_panel,
    build_settings_panel,
    build_share_panel,
    build_skills_panel,
    build_status_panel,
)
from .resilience import get_profile_status
from .results import (
    CompactActionResult,
    ExportActionResult,
    SessionActionResult,
    SettingActionResult,
    TreeActionResult,
)


@dataclass
class InteractionViews:
    """Own user-facing panels/status output for command and app action flows."""

    agent_owner: Any
    runtime_owner: Any

    def show_files(self) -> None:
        owner = self.agent_owner
        self.runtime_owner.show_panel(build_files_panel(owner._list_workspace_files()))

    def list_skills(self) -> None:
        owner = self.agent_owner
        if not owner.skill_manager:
            self.runtime_owner.show_error("Skills not enabled")
            return

        if len(owner.skill_manager) == 0:
            self.runtime_owner.show_system("No skills found")
            self.runtime_owner.show_system("Create skills in .agents/skills/skill-name/SKILL.md")
            return

        panel = build_skills_panel(
            [(skill.name, skill.description) for skill in owner.skill_manager.list_skills()]
        )
        self.runtime_owner.show_panel(panel)

    def list_extensions(self) -> None:
        owner = self.agent_owner
        if not owner.extension_manager:
            self.runtime_owner.show_error("Extensions not enabled")
            return

        if len(owner.extension_manager.extensions) == 0:
            self.runtime_owner.show_system("No extensions loaded")
            self.runtime_owner.show_system("Place extensions in .agents/extensions/")
            return

        commands = owner.extension_manager.api.get_commands()
        panel = build_extensions_panel(
            list(owner.extension_manager.extensions.keys()),
            list(commands.keys()),
            tool_count=len(owner.agent.registry),
        )
        self.runtime_owner.show_panel(panel)

    def list_prompts(self) -> None:
        owner = self.agent_owner
        if not owner.prompt_manager or len(owner.prompt_manager) == 0:
            self.runtime_owner.show_system("No prompts found")
            self.runtime_owner.show_system("Create prompts in .agents/prompts/*.md")
            return

        prompt_rows = []
        for template in owner.prompt_manager.list_templates():
            first_line = template.content.split("\n")[0].strip("# ").strip()
            suffix = f" (vars: {', '.join(template.variables)})" if template.variables else ""
            prompt_rows.append(f"/{template.name}{suffix} — {first_line}")

        panel = build_prompts_panel(prompt_rows)
        self.runtime_owner.show_panel(panel)

    def show_queue(self) -> None:
        owner = self.agent_owner
        queue = owner.agent.message_queue

        if not queue:
            self.runtime_owner.show_status(StatusMessage("info", "Message queue is empty"))
            self.runtime_owner.show_system("\nQueue messages while agent is working:")
            self.runtime_owner.show_system(
                "  !message    - Steering (interrupt after current tool)"
            )
            self.runtime_owner.show_system("  >>message   - Follow-up (wait until done)")
            return

        steering = [m for m in queue.queue if m.type.value == "steering"]
        followup = [m for m in queue.queue if m.type.value == "followup"]
        panel = build_queue_panel(
            [msg.content[:60] + "..." for msg in steering],
            [msg.content[:60] + "..." for msg in followup],
            steering_mode=str(queue.steering_mode),
            followup_mode=str(queue.followup_mode),
        )
        self.runtime_owner.show_panel(panel)

    def show_config(self) -> None:
        owner = self.agent_owner
        config = owner.config_manager.load_config()
        panel = build_config_panel(config)
        self.runtime_owner.show_panel(panel)
        self.runtime_owner.show_system("Edit config files or use environment variables")

    def show_settings(self) -> None:
        """Render current settings and the supported project-scoped edit surface."""
        owner = self.agent_owner
        cfg = owner.config_manager.load_config()
        panel = build_settings_panel(
            provider=str(owner.agent.llm.config.provider),
            model=str(owner.agent.llm.config.model),
            workspace=str(owner.workspace),
            session_dir=str(owner.sessions_dir),
            skills_enabled=bool(owner.skill_manager),
            extensions_enabled=bool(owner.extension_manager),
            editable_rows=[
                (
                    key,
                    str(getattr(cfg, key, "?")),
                    owner.app_actions.setting_apply_mode(key),
                )
                for key in owner._EDITABLE_SETTINGS
            ],
            project_config=str(owner.config_manager.project_config),
            global_config=str(owner.config_manager.global_config),
        )
        self.runtime_owner.show_panel(panel)

    def show_resilience_status(self) -> None:
        owner = self.agent_owner
        if not owner.profile_manager:
            self.runtime_owner.show_status(StatusMessage("info", "Resilience not enabled"))
            self.runtime_owner.show_system("\nTo enable resilience:")
            self.runtime_owner.show_system("  1. Set multiple API keys:")
            self.runtime_owner.show_system("     export OPENAI_API_KEY=sk-...")
            self.runtime_owner.show_system("     export OPENAI_API_KEY_2=sk-...")
            self.runtime_owner.show_system("     export ANTHROPIC_API_KEY=sk-ant-...")
            self.runtime_owner.show_system("  2. Restart agent")
            return

        status = get_profile_status(owner.profile_manager)
        panel = build_resilience_panel(status)
        self.runtime_owner.show_panel(panel)

    def show_cost_summary(self, title: str = "Usage & Cost") -> None:
        owner = self.agent_owner
        if not owner.cost_tracker:
            self.runtime_owner.show_status(StatusMessage("info", "Cost tracking not enabled"))
            return

        summary_text = owner.cost_tracker.format_summary()
        panel = build_cost_panel(title, summary_text, str(owner.cost_tracker.usage_file))
        self.runtime_owner.show_panel(panel)

    def show_help(self) -> None:
        self.runtime_owner.show_panel(build_help_panel())

    def show_no_sessions_available(self) -> None:
        owner = self.agent_owner
        self.runtime_owner.show_status(StatusMessage("info", "No sessions found"))
        self.runtime_owner.show_system(f"Sessions are saved to: {owner.sessions_dir}")

    def show_tree(self) -> None:
        owner = self.agent_owner
        if not owner.session:
            self.runtime_owner.show_error("No session loaded")
            return

        items, total_entries, current_path_length = owner.app_actions.tree_panel_items()
        panel = build_session_tree_panel(
            items,
            total_entries=total_entries,
            current_path_length=current_path_length,
        )
        self.runtime_owner.show_panel(panel)

    def list_sessions(self) -> None:
        owner = self.agent_owner
        items, truncated = owner.app_actions.session_list_items(limit=20)
        if not items:
            self.show_no_sessions_available()
            return
        panel = build_sessions_panel(
            items,
            session_dir=str(owner.sessions_dir),
            truncated=truncated,
        )
        self.runtime_owner.show_panel(panel)
        self.runtime_owner.show_system("Use `pig --resume` to select a session")

    def show_session_info(self) -> None:
        owner = self.agent_owner
        info = owner.app_actions.session_info()
        if info is None:
            self.runtime_owner.show_error("No session loaded")
            return
        panel = build_session_info_panel(info)
        self.runtime_owner.show_panel(panel)

    def show_status(self) -> None:
        owner = self.agent_owner
        panel = build_status_panel(**owner.app_actions.status_view_data())
        self.runtime_owner.show_panel(panel)

    def report_session_result(self, result: SessionActionResult) -> None:
        if not result.get("ok"):
            error = result.get("error")
            if error:
                self.runtime_owner.show_error(str(error))
            current_name = result.get("current_name")
            if current_name:
                self.runtime_owner.show_system(f"Current session name: {current_name}")
                self.runtime_owner.show_system("Set it with: /name <display name>")
            return

        if "messages_restored" in result and result.get("name") and result.get("session_id"):
            self.runtime_owner.show_system(
                f"✓ Resumed session: {result['name']} ({result['session_id']})"
            )
            self.runtime_owner.show_system(f"  {result['messages_restored']} messages restored")
            return

        if result.get("name") and result.get("entries") is not None and result.get("save_path"):
            self.runtime_owner.show_system(f"✓ Forked session: {result['name']}")
            self.runtime_owner.show_system(f"  Copied {result['entries']} entries")
            self.runtime_owner.show_system(f"  Saved to: {result['save_path']}")
            return

        if result.get("name") and result.get("save_path") and result.get("session_id"):
            self.runtime_owner.show_system(
                f"✓ Cloned session: {result['name']} ({result['session_id']})"
            )
            self.runtime_owner.show_system(f"  Saved to: {result['save_path']}")
            return

        if result.get("name") and result.get("save_path") and result.get("messages_restored"):
            self.runtime_owner.show_system(
                f"✓ Imported session: {result['name']} ({result['session_id']})"
            )
            self.runtime_owner.show_system(f"  Saved to: {result['save_path']}")
            self.runtime_owner.show_system(f"  {result['messages_restored']} messages restored")
            return

        if result.get("session_id") and result.get("name") == "coding-session":
            self.runtime_owner.show_system(f"✓ Started a new session: {result['session_id']}")
            return

        if (
            result.get("name")
            and result.get("session_id") is None
            and result.get("save_path") is None
            and result.get("messages_restored") is None
            and result.get("entries") is None
            and result.get("chars") is None
        ):
            self.runtime_owner.show_system(f"✓ Session renamed to: {result['name']}")
            return

        if result.get("chars") is not None:
            self.runtime_owner.show_system(
                f"✓ Copied last reply to clipboard ({result['chars']} chars)"
            )

    def report_setting_result(self, result: SettingActionResult) -> None:
        if not result.get("ok"):
            error = result.get("error")
            if error:
                self.runtime_owner.show_error(str(error))
            return

        self.runtime_owner.show_system(
            f"✓ {result['key']} = {result['value']}  (saved to {result['project_config']})"
        )
        if result.get("needs_restart"):
            self.runtime_owner.show_system("  (applies on next launch)")

    def report_tree_result(self, result: TreeActionResult) -> None:
        if not result.get("ok"):
            error = result.get("error")
            if error:
                self.runtime_owner.show_error(str(error))
            return

        if result.get("label") is not None:
            self.runtime_owner.show_status(
                StatusMessage(
                    "ok",
                    f"Labeled session entry {result['entry_id']} as: {result['label']}",
                )
            )
            return

        if result.get("entry_id") is not None:
            self.runtime_owner.show_status(
                StatusMessage("ok", f"Switched session tree to: {result['entry_id']}")
            )

    def report_compact_result(self, result: CompactActionResult) -> None:
        if not result.get("ok"):
            error = result.get("error")
            if error:
                self.runtime_owner.show_error(str(error))
            return

        self.runtime_owner.show_system(
            f"✓ Compacted: {result['before']} entries → {result['after']} entries"
        )
        if result.get("instructions"):
            self.runtime_owner.show_system(f"  Instructions: {result['instructions']}")

    def report_export_result(self, result: ExportActionResult) -> None:
        if not result.get("ok"):
            error = result.get("error")
            if error:
                self.runtime_owner.show_error(str(error))
            return

        from pig_tui import hyperlink

        exported = str(result["exported"])
        self.runtime_owner.show_system(f"✓ Exported to: {exported}")
        self.runtime_owner.show_system(
            f"  Open in browser: {hyperlink(exported, str(result['export_url']))}"
        )

    def show_share_result(self, info: dict[str, Any]) -> None:
        self.runtime_owner.show_panel(build_share_panel(info))
