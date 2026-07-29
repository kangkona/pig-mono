"""Command and presentation runtime orchestration for pig-coding-agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pig_tui import ChatPresenter, ChatUI, PanelContent, StatusMessage, TerminalRuntime
from pig_tui.runtime import TerminalUI

from .interaction_commands import InteractionCommands
from .interaction_dispatcher import InteractionDispatcher
from .interaction_flows import InteractionFlows
from .interaction_routes import InteractionRoutes
from .interaction_views import InteractionViews

if TYPE_CHECKING:
    from .agent import CodingAgent


InteractionUI = TerminalUI


@dataclass
class InteractionRuntime:
    """Own the prompt loop and streaming-turn orchestration for CodingAgent."""

    agent_owner: CodingAgent
    terminal_runtime_factory: Any | None = None
    prompt_runtime_factory: Any | None = None
    turn_controller_factory: Any | None = None
    ui_factory: Callable[[], InteractionUI] | None = None
    ui: InteractionUI | None = None
    _terminal_runtime: TerminalRuntime | None = None
    presenter: ChatPresenter | None = None
    views: InteractionViews | None = None
    flows: InteractionFlows | None = None
    commands: InteractionCommands | None = None
    routes: InteractionRoutes | None = None
    dispatcher: InteractionDispatcher | None = None

    def __post_init__(self) -> None:
        if self.ui is None:
            factory = self.ui_factory or (
                lambda: ChatUI(title="Coding Agent", show_timestamps=False)
            )
            self.ui = factory()
        if self.presenter is None:
            self.presenter = ChatPresenter(self._require_ui)
        if self.views is None:
            self.views = InteractionViews(self.agent_owner, self)
        if self.flows is None:
            self.flows = InteractionFlows(self.agent_owner, self)
        if self.commands is None:
            self.commands = InteractionCommands(self.agent_owner, self)
        if self.routes is None:
            self.routes = InteractionRoutes(self.agent_owner, self)
        if self.dispatcher is None:
            self.dispatcher = InteractionDispatcher(self.agent_owner, self)

    def _build_simple_command_routes(self) -> dict[str, Any]:
        assert self.routes is not None
        return self.routes.build_simple_routes()

    def _build_prefix_command_routes(self) -> dict[str, Any]:
        assert self.routes is not None
        return self.routes.build_prefix_routes()

    def _require_ui(self) -> InteractionUI:
        assert self.ui is not None
        return self.ui

    @staticmethod
    def _split_required_arg_pair(raw_args: str | None) -> tuple[str, str] | None:
        if not raw_args:
            return None
        parts = raw_args.split(maxsplit=1)
        if len(parts) < 2:
            return None
        first = parts[0].strip()
        second = parts[1].strip()
        if not first or not second:
            return None
        return first, second

    def _build_terminal_runtime(self) -> TerminalRuntime:
        if self._terminal_runtime is not None:
            return self._terminal_runtime

        history_file = str(self.agent_owner.sessions_dir / ".input_history")
        runtime_factory = self.terminal_runtime_factory or TerminalRuntime
        runtime_kwargs: dict[str, Any] = {
            "ui": self.ui,
            "commands": self.agent_owner.interaction_catalog.build_commands,
            "workspace": str(self.agent_owner.workspace),
            "history_file": history_file,
        }
        if self.prompt_runtime_factory is not None:
            runtime_kwargs["prompt_runtime_factory"] = self.prompt_runtime_factory
        if self.turn_controller_factory is not None:
            runtime_kwargs["turn_controller_factory"] = self.turn_controller_factory
        self._terminal_runtime = runtime_factory(**runtime_kwargs)
        return self._terminal_runtime

    def _terminal_output_surface(self) -> Any | None:
        return self._terminal_runtime

    def set_ui(self, ui: InteractionUI) -> None:
        self.ui = ui
        if self._terminal_runtime is not None:
            self._terminal_runtime.ui = ui

    def show_panel(self, panel: PanelContent) -> None:
        runtime = self._terminal_output_surface()
        if runtime is not None and hasattr(runtime, "show_panel"):
            runtime.show_panel(panel)
            return
        assert self.presenter is not None
        self.presenter.show_panel(panel)

    def show_text_panel(self, title: str, content: str) -> None:
        self.show_panel(PanelContent(title=title, content=content))

    def show_status(self, status: StatusMessage) -> None:
        runtime = self._terminal_output_surface()
        if runtime is not None and hasattr(runtime, "show_status"):
            runtime.show_status(status)
            return
        assert self.presenter is not None
        self.presenter.show_status(status)

    def show_error(self, message: str) -> None:
        runtime = self._terminal_output_surface()
        if runtime is not None and hasattr(runtime, "show_error"):
            runtime.show_error(message)
            return
        assert self.presenter is not None
        self.presenter.show_error(message)

    def show_system(self, message: str) -> None:
        runtime = self._terminal_output_surface()
        if runtime is not None and hasattr(runtime, "show_system"):
            runtime.show_system(message)
            return
        assert self.ui is not None
        self.ui.system(message)

    def show_user(self, message: str) -> None:
        runtime = self._terminal_output_surface()
        if runtime is not None and hasattr(runtime, "show_user"):
            runtime.show_user(message)
            return
        assert self.ui is not None
        self.ui.user(message)

    def show_assistant(self, message: str) -> None:
        runtime = self._terminal_output_surface()
        if runtime is not None and hasattr(runtime, "show_assistant"):
            runtime.show_assistant(message)
            return
        assert self.ui is not None
        self.ui.assistant(message)

    def clear(self) -> None:
        runtime = self._terminal_output_surface()
        if runtime is not None and hasattr(runtime, "clear"):
            runtime.clear()
            return
        assert self.ui is not None
        self.ui.clear()

    def separator(self) -> None:
        runtime = self._terminal_output_surface()
        if runtime is not None and hasattr(runtime, "separator"):
            runtime.separator()
            return
        assert self.ui is not None
        self.ui.separator()

    def handle_command(self, command: str) -> None:
        """Delegate interactive slash-command dispatch to the dedicated dispatcher."""
        assert self.dispatcher is not None
        self.dispatcher.dispatch(command)
