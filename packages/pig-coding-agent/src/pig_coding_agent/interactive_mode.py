"""Interactive shell mode and turn orchestration for pig-coding-agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pig_tui import ShellLoopSession


@dataclass
class InteractiveMode:
    """Own the interactive shell loop and per-turn runtime orchestration."""

    agent_owner: Any
    interaction_runtime: Any

    _CONTEXT_WINDOWS = {
        "gpt-4.1": 1_000_000,
        "gpt-4o": 128_000,
        "o1": 200_000,
        "o3": 200_000,
        "o4": 200_000,
        "claude": 200_000,
        "gemini-1.5": 1_000_000,
        "gemini-2": 1_000_000,
        "gemini-3": 1_000_000,
        "deepseek": 128_000,
        "llama": 128_000,
        "mixtral": 32_000,
        "qwen": 128_000,
        "grok": 128_000,
    }
    _DEFAULT_CONTEXT_WINDOW = 128_000

    def _show_queue_status(self) -> None:
        owner = self.agent_owner
        if owner.agent.message_queue:
            queue_status = owner.agent.message_queue.get_status()
            if "Queued" in queue_status:
                self.interaction_runtime.show_system(f"📬 {queue_status}")

    def _expand_file_references(self, user_input: str) -> str:
        owner = self.agent_owner
        if "@" not in user_input:
            return user_input

        preview = owner.file_ref_parser.get_reference_preview(user_input)
        if preview:
            self.interaction_runtime.show_system(preview)
            expanded_input = owner.file_ref_parser.expand_references(user_input)
            if len(expanded_input) > len(user_input) + 100:
                added = len(expanded_input) - len(user_input)
                self.interaction_runtime.show_system(f"→ Added {added} chars from files")
            return expanded_input
        return user_input

    def _handle_non_turn_input(self, user_input: str) -> bool:
        owner = self.agent_owner
        if not user_input:
            return True

        if user_input.startswith("/"):
            self.interaction_runtime.handle_command(user_input)
            return True

        if user_input.startswith("!"):
            steering_msg = user_input.lstrip("!")
            owner.agent.message_queue.add_steering(steering_msg)
            self.interaction_runtime.show_system(
                f"⚡ Queued steering message: {steering_msg[:50]}..."
            )
            return True

        if user_input.startswith(">>"):
            followup_msg = user_input.lstrip(">").strip()
            owner.agent.message_queue.add_followup(followup_msg)
            self.interaction_runtime.show_system(
                f"📝 Queued follow-up message: {followup_msg[:50]}..."
            )
            return True

        return False

    @staticmethod
    def _parse_running_message(line: str) -> tuple[str, str, str] | None:
        raw = line.strip()
        if not raw:
            return None
        if raw.startswith(">>"):
            content = raw[2:].strip()
            if not content:
                return None
            return ("followup", content, f">>{content}")
        if raw.startswith("!"):
            content = raw[1:].strip()
            if not content:
                return None
            return ("steering", content, f"!{content}")
        return ("steering", raw, raw)

    def _finalize_interactive_session(self, reason: str) -> None:
        owner = self.agent_owner
        owner._shutdown_extensions(reason)
        if owner.agent.message_queue:
            cleared = owner.agent.message_queue.clear()
            if cleared:
                self.interaction_runtime.show_system(f"\nCleared {len(cleared)} queued messages")
        if owner.session:
            session_dir_hint = ""
            if owner.sessions_dir != owner.workspace / ".sessions":
                session_dir_hint = f" --session-dir {owner.sessions_dir}"
            self.interaction_runtime.show_system(
                f"💾 Session saved. Resume with:  "
                f"pig --session-id {owner.session.id}{session_dir_hint}"
            )
            self.interaction_runtime.show_system(
                "(or pig --continue to resume the most recent session)"
            )
        self.interaction_runtime.show_system("Goodbye!")

    def context_window(self) -> int:
        """Return the current model context window for interactive telemetry."""
        model = self.agent_owner.agent.llm.config.model or ""
        from pig_llm import get_model_info

        info = get_model_info(model)
        if info is not None:
            return int(info["context_window"])

        lowered = model.lower()
        best = None
        for key, window in self._CONTEXT_WINDOWS.items():
            if key in lowered and (best is None or len(key) > len(best[0])):
                best = (key, window)
        return best[1] if best else self._DEFAULT_CONTEXT_WINDOW

    def context_tokens(self) -> int | None:
        usage = self.agent_owner.agent.last_llm_usage
        if not usage:
            return None
        return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))

    @staticmethod
    def format_k(n: int) -> str:
        return f"{n / 1000:.0f}k" if n >= 1000 else str(n)

    def total_cost(self) -> float:
        if not self.agent_owner.cost_tracker:
            return 0.0
        try:
            return float(self.agent_owner.cost_tracker.get_usage_summary().get("total_cost", 0.0))
        except Exception:
            return 0.0

    def show_turn_status(self, cost_before: float) -> None:
        owner = self.agent_owner
        parts: list[str] = []
        ctx = self.context_tokens()
        if ctx is not None:
            window = self.context_window()
            pct = (ctx / window * 100) if window else 0
            parts.append(f"context {self.format_k(ctx)}/{self.format_k(window)} ({pct:.0f}%)")
        if owner.cost_tracker:
            total = self.total_cost()
            delta = total - cost_before
            parts.append(f"+${delta:.4f} (total ${total:.4f})")
        if parts:
            self.interaction_runtime.show_system(" · ".join(parts))

    def maybe_auto_compact(self) -> None:
        owner = self.agent_owner
        cfg = owner.config_manager.load_config()
        if not cfg.auto_compact:
            return
        ctx = self.context_tokens()
        if ctx is None:
            return
        window = self.context_window()
        if ctx <= int(window * cfg.auto_compact_threshold):
            return
        self.interaction_runtime.show_system(
            f"⚠ Context {self.format_k(ctx)}/{self.format_k(window)} "
            "— auto-compacting to free space…"
        )
        try:
            self.interaction_runtime.views.report_compact_result(
                owner.app_actions.compact_session(
                    None,
                    reason="threshold",
                    before_tokens=ctx,
                )
            )
            owner.app_actions.rebuild_history_from_session()
            owner.agent.last_llm_usage = None
        except Exception as e:
            self.interaction_runtime.show_error(f"Auto-compaction failed: {e}")

    async def run_turn(self, user_input: str, cancel: asyncio.Event | None = None) -> None:
        owner = self.agent_owner
        cancel = cancel or asyncio.Event()

        if owner.session:
            owner.session.add_message("user", user_input)

        def on_steering(line: str) -> None:
            parsed = self._parse_running_message(line)
            if parsed is None:
                return
            kind, content, visible = parsed
            self.interaction_runtime.show_user(visible)
            if kind == "followup":
                owner.agent.message_queue.add_followup(content)
                self.interaction_runtime.show_system(
                    f"📝 Queued follow-up message: {content[:50]}..."
                )
                return
            owner.agent.message_queue.add_steering(content)
            self.interaction_runtime.show_system(f"⚡ Queued steering message: {content[:50]}...")

        runtime = self.interaction_runtime._build_terminal_runtime()
        result = await runtime.stream_turn(
            stream=owner.agent.respond_stream(user_input, cancel=cancel, max_iterations=0),
            on_steering=on_steering,
            cancel_event=cancel,
        )

        if result.aborted:
            self.interaction_runtime.show_system("[aborted]")

        if owner.session and result.content:
            owner.session.add_message("assistant", result.content)

    def run_interactive(self) -> None:
        owner = self.agent_owner
        self.interaction_runtime.show_system(f"Workspace: {owner.workspace}")
        self.interaction_runtime.separator()
        runtime = self.interaction_runtime._build_terminal_runtime()
        turn_state = {"cost_before": 0.0}

        def _before_turn(user_input: str) -> None:
            del user_input
            turn_state["cost_before"] = self.total_cost()

        def _after_turn(user_input: str) -> None:
            del user_input
            self.show_turn_status(turn_state["cost_before"])
            self.maybe_auto_compact()

        def _exception_to_reason(exc: Exception) -> str | None:
            if exc.__class__.__name__ == "SessionExitRequested":
                return "normal"
            if isinstance(exc, RuntimeError) and "lost terminal" in str(exc).lower():
                return "lost_terminal"
            return None

        shutdown_reason = "normal"
        try:
            result = runtime.run_shell_loop(
                ShellLoopSession(
                    run_turn=self.run_turn,
                    before_prompt=self._show_queue_status,
                    handle_input=self._handle_non_turn_input,
                    prepare_input=self._expand_file_references,
                    display_input=lambda text: self.interaction_runtime.show_user(
                        text[:200] + "..." if len(text) > 200 else text
                    ),
                    before_turn=_before_turn,
                    after_turn=_after_turn,
                    on_turn_interrupt=lambda: self.interaction_runtime.show_system("[aborted]"),
                    exception_to_reason=_exception_to_reason,
                    re_raise_mapped_exceptions=True,
                )
            )
            shutdown_reason = result.reason
        except Exception as exc:
            mapped = _exception_to_reason(exc)
            if mapped is None:
                raise
            shutdown_reason = mapped
            if mapped != "normal":
                self._finalize_interactive_session(shutdown_reason)
                raise
        self._finalize_interactive_session(shutdown_reason)
