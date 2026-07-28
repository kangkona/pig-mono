"""Runtime primitives for pig-tui platform-level interactions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .components import (
    ChoiceEditorContainer,
    ConfirmView,
    SelectionActionContainer,
    SelectListView,
    TextBlock,
    TextEditorView,
    TreeBrowserContainer,
    TreeListView,
)
from .core import (
    Component,
    Container,
    ContainerContent,
    PanelContent,
    SelectionActionResult,
    SelectionEditResult,
    SelectOption,
    StatusMessage,
    TextEditorState,
    TreeBrowserResult,
    TreeBrowserState,
    TreeOption,
    is_focusable,
)
from .keylistener import LiveInputListener
from .presenter import ChatPresenter
from .prompt import InteractivePrompt


@dataclass
class FocusManager:
    """Track focus transitions across prompt, streaming, and overlay states."""

    current: str | None = None
    history: list[str] = field(default_factory=list)
    component: Component | None = None

    def focus(self, target: str, component: Component | None = None) -> None:
        if self.current is not None:
            self.history.append(self.current)
        if is_focusable(self.component):
            self.component.focused = False
        self.current = target
        self.component = component
        if is_focusable(component):
            component.focused = True

    def restore_previous(self) -> str | None:
        if is_focusable(self.component):
            self.component.focused = False
        self.current = self.history.pop() if self.history else None
        self.component = None
        return self.current


@dataclass
class OverlayStack:
    """Lightweight overlay stack abstraction for platform-driven panels/dialogs."""

    entries: list[tuple[PanelContent, Component | None]] = field(default_factory=list)

    def push(self, panel: PanelContent, component: Component | None = None) -> None:
        self.entries.append((panel, component))

    def pop(self) -> tuple[PanelContent, Component | None] | None:
        return self.entries.pop() if self.entries else None

    def peek(self) -> PanelContent | None:
        return self.entries[-1][0] if self.entries else None

    def __len__(self) -> int:
        return len(self.entries)


@dataclass
class FocusContainer(Container):
    """Own focus traversal across a small ordered set of focusable components."""

    components: list[Component]
    selected_index: int = 0

    def __post_init__(self) -> None:
        self.selected_index = self._first_focusable_index(self.selected_index)
        for index, component in enumerate(self.components):
            if is_focusable(component):
                component.focused = index == self.selected_index

    def _first_focusable_index(self, fallback: int = 0) -> int:
        for index, component in enumerate(self.components):
            if is_focusable(component):
                return index
        return fallback

    def _move_focus(self, step: int) -> Component | None:
        if not self.components:
            return None
        current = self.current()
        if is_focusable(current):
            current.focused = False

        total = len(self.components)
        index = self.selected_index
        for _ in range(total):
            index = (index + step) % total
            candidate = self.components[index]
            if is_focusable(candidate):
                self.selected_index = index
                candidate.focused = True
                return candidate

        self.selected_index = self._first_focusable_index(self.selected_index)
        current = self.current()
        if is_focusable(current):
            current.focused = True
        return current

    def current(self) -> Component | None:
        if not self.components:
            return None
        return self.components[self.selected_index]

    def render_sections(self, width: int) -> list[str]:
        sections: list[str] = []
        for component in self.components:
            sections.append("\n".join(component.render(width)))
        return sections

    def focus_next(self) -> Component | None:
        return self._move_focus(1)

    def focus_previous(self) -> Component | None:
        return self._move_focus(-1)

    def focus_index(self, index: int) -> Component | None:
        if not self.components:
            return None
        index = max(0, min(index, len(self.components) - 1))
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = index
        component = self.current()
        if is_focusable(component):
            component.focused = True
            return component

        step = 1 if index < len(self.components) - 1 else -1
        return self._move_focus(step)


class ChatStreamUI(Protocol):
    def assistant_stream_markdown(self) -> AbstractAsyncContextManager | object: ...


@dataclass
class TurnResult:
    content: str
    aborted: bool


@dataclass(frozen=True)
class ShellLoopResult:
    """Outcome of a runtime-owned interactive shell loop."""

    reason: str


@dataclass(frozen=True)
class ShellLoopSession:
    """Configuration for one runtime-owned interactive shell loop."""

    run_turn: Callable[[str], Awaitable[None]]
    prompt_text: str = "You> "
    before_prompt: Callable[[], None] | None = None
    handle_input: Callable[[str], bool] | None = None
    prepare_input: Callable[[str], str] | None = None
    display_input: Callable[[str], None] | None = None
    before_turn: Callable[[str], None] | None = None
    after_turn: Callable[[str], None] | None = None
    on_turn_interrupt: Callable[[], None] | None = None
    exception_to_reason: Callable[[Exception], str | None] | None = None
    re_raise_mapped_exceptions: bool = False


@dataclass(frozen=True)
class OverlaySession:
    """Runtime-owned overlay session state for a single interactive container flow."""

    content: ContainerContent
    container: Container
    focus_component: Component | None = None


@dataclass(frozen=True)
class PromptStep:
    """One prompt collection step executed inside a runtime-owned overlay session."""

    prompt_text: str
    strip: bool = False


@dataclass(frozen=True)
class SelectionSession:
    """Runtime-owned structured selection session."""

    title: str
    options: list[SelectOption]
    prompt_text: str = "Select> "
    note: str | None = None
    header_component: Component | None = None
    default_index: int = 0


@dataclass(frozen=True)
class EditorSession:
    """Runtime-owned short-text editing session."""

    title: str
    initial_value: str = ""
    note: str | None = None
    prompt_text: str = "Edit> "


@dataclass(frozen=True)
class SelectionEditorSession:
    """Runtime-owned combined selection and editing session."""

    title: str
    options: list[SelectOption]
    edit_title: str
    edit_note: str | None = None
    use_selected_description_as_initial: bool = True
    select_prompt_text: str = "Select> "
    edit_prompt_text: str = "Edit> "


@dataclass(frozen=True)
class SelectionActionSession:
    """Runtime-owned combined selection and action session."""

    title: str
    options: list[SelectOption]
    actions: list[SelectOption]
    action_title: str = "Actions"
    note: str | None = None
    header_component: Component | None = None
    default_option_index: int = 0
    default_action_index: int = 0
    select_prompt_text: str = "Select> "
    action_prompt_text: str = "Action> "


@dataclass(frozen=True)
class TreeBrowserSession:
    """Runtime-owned tree browser session."""

    title: str
    entries: list[TreeOption]
    actions: list[SelectOption]
    action_title: str = "Actions"
    state: TreeBrowserState = field(default_factory=TreeBrowserState)
    note: str | None = None
    header_component: Component | None = None
    default_entry_index: int = 0
    default_action_index: int = 0
    select_prompt_text: str = "Select> "
    action_prompt_text: str = "Action> "


class PromptRuntime:
    """Stable runtime wrapper around the interactive prompt implementation."""

    def __init__(
        self,
        commands: list[str] | Callable[[], list[str]],
        workspace: str = ".",
        history_file: str | Path | None = None,
        prompt_factory=InteractivePrompt,
    ) -> None:
        self.commands = commands
        self.workspace = workspace
        self.history_file = str(history_file) if history_file is not None else None
        self.prompt_factory = prompt_factory
        self._prompt = None

    def _resolve_commands(self) -> list[str]:
        return self.commands() if callable(self.commands) else list(self.commands)

    def _prompt_instance(self):
        if self._prompt is None:
            self._prompt = self.prompt_factory(
                commands=self._resolve_commands(),
                workspace=self.workspace,
                history_file=self.history_file,
            )
        return self._prompt

    def ask(self, prompt_text: str = "You> ") -> str:
        return self._prompt_instance().ask(prompt_text)


class StreamingTurnController:
    """Own the live-input + live-markdown orchestration for one streaming turn."""

    def __init__(
        self,
        commands: list[str] | Callable[[], list[str]],
        *,
        live_input_listener_factory=LiveInputListener,
    ) -> None:
        self.commands = commands
        self.live_input_listener_factory = live_input_listener_factory

    def _resolve_commands(self) -> list[str]:
        return self.commands() if callable(self.commands) else list(self.commands)

    async def run(
        self,
        *,
        stream: AsyncIterator[str],
        ui,
        on_steering: Callable[[str], None],
        cancel_event: asyncio.Event | None = None,
    ) -> TurnResult:
        cancel = cancel_event or asyncio.Event()
        parts: list[str] = []

        with ui.assistant_stream_markdown() as writer:
            async with self.live_input_listener_factory(
                cancel,
                on_steering=on_steering,
                on_change=writer.set_input,
                completions=self._resolve_commands(),
                echo=False,
            ):

                async def _tick() -> None:
                    while True:
                        await asyncio.sleep(0.4)
                        writer.tick()

                ticker = asyncio.create_task(_tick())
                try:
                    async for chunk in stream:
                        parts.append(chunk)
                        writer.write(chunk)
                finally:
                    ticker.cancel()

        return TurnResult(content="".join(parts), aborted=cancel.is_set())


class TerminalRuntime:
    """Coordinate prompt input, focus state, overlays, and streaming turns."""

    def __init__(
        self,
        *,
        ui,
        commands: list[str] | Callable[[], list[str]],
        workspace: str = ".",
        history_file: str | Path | None = None,
        prompt_runtime_factory: Callable[..., PromptRuntime] | None = None,
        turn_controller_factory: Callable[..., StreamingTurnController] | None = None,
    ) -> None:
        self.ui = ui
        self.commands = commands
        self.focus = FocusManager()
        self.overlays = OverlayStack()
        self.active_container: Container | None = None
        self._container_history: list[Container | None] = []
        prompt_runtime_factory = prompt_runtime_factory or PromptRuntime
        turn_controller_factory = turn_controller_factory or StreamingTurnController
        self.presenter = ChatPresenter(lambda: self.ui)
        self.prompt_runtime = prompt_runtime_factory(
            commands=commands,
            workspace=workspace,
            history_file=history_file,
        )
        self.turn_controller = turn_controller_factory(commands=commands)

    def show_panel(self, panel: PanelContent) -> None:
        self.presenter.show_panel(panel)

    def show_text_panel(self, title: str, content: str) -> None:
        self.show_panel(PanelContent(title=title, content=content))

    def show_status(self, status: StatusMessage) -> None:
        self.presenter.show_status(status)

    def show_error(self, message: str) -> None:
        self.presenter.show_error(message)

    def show_system(self, message: str) -> None:
        self.ui.system(message)

    def show_user(self, message: str) -> None:
        self.ui.user(message)

    def show_assistant(self, message: str) -> None:
        self.ui.assistant(message)

    def clear(self) -> None:
        self.ui.clear()

    def separator(self) -> None:
        self.ui.separator()

    def ask(self, prompt_text: str = "You> ") -> str:
        self.focus.focus("prompt")
        return self.prompt_runtime.ask(prompt_text)

    def run_shell_loop(self, session: ShellLoopSession) -> ShellLoopResult:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        reason = "normal"

        try:
            while True:
                if session.before_prompt is not None:
                    session.before_prompt()

                try:
                    user_input = self.ask(session.prompt_text)
                except KeyboardInterrupt:
                    reason = "interrupt"
                    break
                except EOFError:
                    reason = "eof"
                    break

                if session.handle_input is not None and session.handle_input(user_input):
                    continue

                prepared_input = (
                    session.prepare_input(user_input)
                    if session.prepare_input is not None
                    else user_input
                )

                if session.display_input is not None:
                    session.display_input(prepared_input)
                if session.before_turn is not None:
                    session.before_turn(prepared_input)

                try:
                    loop.run_until_complete(session.run_turn(prepared_input))
                except KeyboardInterrupt:
                    if session.on_turn_interrupt is not None:
                        session.on_turn_interrupt()
                    continue

                if session.after_turn is not None:
                    session.after_turn(prepared_input)

        except KeyboardInterrupt:
            reason = "interrupt"
        except Exception as exc:
            if session.exception_to_reason is None:
                raise
            mapped = session.exception_to_reason(exc)
            if mapped is None:
                raise
            reason = mapped
            if session.re_raise_mapped_exceptions:
                raise
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

        return ShellLoopResult(reason=reason)

    async def stream_turn(
        self,
        *,
        stream: AsyncIterator[str],
        on_steering: Callable[[str], None],
        cancel_event: asyncio.Event | None = None,
    ) -> TurnResult:
        self.focus.focus("streaming")
        try:
            return await self.turn_controller.run(
                stream=stream,
                ui=self.ui,
                on_steering=on_steering,
                cancel_event=cancel_event,
            )
        finally:
            self.focus.restore_previous()

    def push_overlay(self, panel: PanelContent, component: Component | None = None) -> None:
        self.focus.focus("overlay", component=component)
        self.overlays.push(panel, component)
        if component is not None:
            self.active_container = FocusContainer([component])

    def pop_overlay(self) -> PanelContent | None:
        entry = self.overlays.pop()
        panel = entry[0] if entry else None
        if len(self.overlays) == 0:
            self.focus.restore_previous()
            self.active_container = None
        return panel

    def set_active_container(self, container: Container | None) -> None:
        self.active_container = container
        current = container.current() if container is not None else None
        if current is not None:
            self.focus.focus("container", component=current)

    def open_container(self, content: ContainerContent, container: Container) -> None:
        self.set_active_container(container)
        rendered_sections = container.render_sections(100)
        sections = rendered_sections or content.sections
        self.show_text_panel(content.title, "\n\n".join(sections))

    def begin_overlay_session(self, session: OverlaySession) -> None:
        self._container_history.append(self.active_container)
        self.set_active_container(session.container)
        rendered_sections = session.container.render_sections(100)
        sections = rendered_sections or session.content.sections
        panel_text = "\n\n".join(sections)
        self.push_overlay(
            PanelContent(title=session.content.title, content=panel_text),
            component=session.focus_component or session.container.current(),
        )
        self.open_container(session.content, session.container)

    def end_overlay_session(self) -> None:
        prior_container = self._container_history.pop() if self._container_history else None
        self.pop_overlay()
        if prior_container is not None:
            self.set_active_container(prior_container)
            return
        self.focus.focus("prompt")
        self.active_container = None

    def run_prompt_step(self, step: PromptStep) -> str:
        self.focus.focus("prompt")
        value = self.prompt_runtime.ask(step.prompt_text)
        return value.strip() if step.strip else value

    def run_selection_session(self, session: SelectionSession) -> SelectOption | None:
        items = [(option.label, option.description) for option in session.options]
        selector = SelectListView(items, selected_index=session.default_index)
        components: list[Component] = []
        if session.header_component is not None:
            components.append(session.header_component)
        if session.note:
            components.append(TextBlock(session.note))
        components.append(selector)
        container = FocusContainer(components, selected_index=len(components) - 1)
        content = ContainerContent(title=session.title, sections=[""])
        self.begin_overlay_session(
            OverlaySession(content=content, container=container, focus_component=selector)
        )
        try:
            choice = self.run_prompt_step(PromptStep(prompt_text=session.prompt_text, strip=True))
            selected = self.resolve_option_choice(choice, session.options)
            if selected is None:
                return None
            selector.selected_index = session.options.index(selected)
            return selected
        finally:
            self.end_overlay_session()

    def confirm(self, question: str, *, default: bool = False) -> bool:
        options = [
            SelectOption(
                value="yes",
                label="Yes",
                description="Proceed with the requested action",
                aliases=("y", "yes", "true", "1"),
            ),
            SelectOption(
                value="no",
                label="No",
                description="Cancel the requested action",
                aliases=("n", "no", "false", "0"),
            ),
        ]
        option = self.run_selection_session(
            SelectionSession(
                title="Confirm",
                options=options,
                prompt_text="Confirm> ",
                header_component=ConfirmView(question=question, default=default),
                default_index=0 if default else 1,
            )
        )
        if option is None:
            return default
        return option.value == "yes"

    @staticmethod
    def resolve_option_choice(choice: str, options: list[SelectOption]) -> SelectOption | None:
        if not choice:
            return None
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(options):
                return options[index]
            return None
        for option in options:
            if option.value == choice or option.label == choice or choice in option.aliases:
                return option
        return None

    @staticmethod
    def resolve_tree_choice(choice: str, entries: list[TreeOption]) -> TreeOption | None:
        if not choice:
            return None
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(entries):
                return entries[index]
            return None
        for entry in entries:
            if entry.value == choice or entry.label == choice or choice in entry.aliases:
                return entry
        return None

    def select_option(
        self,
        title: str,
        options: list[SelectOption],
        *,
        note: str | None = None,
        prompt_text: str = "Select> ",
    ) -> SelectOption | None:
        return self.run_selection_session(
            SelectionSession(
                title=title,
                options=options,
                prompt_text=prompt_text,
                note=note,
            )
        )

    def focus_next_component(self) -> Component | None:
        if self.active_container is None:
            return None
        component = self.active_container.focus_next()
        if component is not None:
            self.focus.focus("container", component=component)
        return component

    def focus_previous_component(self) -> Component | None:
        if self.active_container is None:
            return None
        component = self.active_container.focus_previous()
        if component is not None:
            self.focus.focus("container", component=component)
        return component

    def focus_component_index(self, index: int) -> Component | None:
        if self.active_container is None:
            return None
        component = self.active_container.focus_index(index)
        if component is not None:
            self.focus.focus("container", component=component)
        return component

    def select(
        self,
        title: str,
        options: list[SelectOption],
        *,
        note: str | None = None,
        prompt_text: str = "Select> ",
    ) -> str | None:
        selected = self.select_option(
            title,
            options,
            note=note,
            prompt_text=prompt_text,
        )
        return selected.value if selected is not None else None

    def run_editor_session(self, session: EditorSession) -> str:
        editor = TextEditorState(
            title=session.title,
            value=session.initial_value,
            note=session.note,
        )
        editor_view = TextEditorView(editor)
        lines = editor_view.render_lines(100)
        container = FocusContainer([editor_view])
        content = ContainerContent(title=session.title, sections=["\n".join(lines)])
        self.begin_overlay_session(
            OverlaySession(content=content, container=container, focus_component=editor_view)
        )
        try:
            updated = self.run_prompt_step(PromptStep(prompt_text=session.prompt_text))
            editor.value = updated
            return editor.value
        finally:
            self.end_overlay_session()

    def edit_text(
        self,
        title: str,
        *,
        initial_value: str = "",
        note: str | None = None,
        prompt_text: str = "Edit> ",
    ) -> str:
        return self.run_editor_session(
            EditorSession(
                title=title,
                initial_value=initial_value,
                note=note,
                prompt_text=prompt_text,
            )
        )

    def run_selection_editor_session(
        self,
        session: SelectionEditorSession,
    ) -> SelectionEditResult:
        items = [(option.label, option.description) for option in session.options]
        selector = SelectListView(items)
        editor_state = TextEditorState(title=session.edit_title, value="", note=session.edit_note)
        editor_view = TextEditorView(editor_state)
        container = ChoiceEditorContainer(
            selector=selector,
            editor=editor_view,
        )
        self.begin_overlay_session(
            OverlaySession(
                content=ContainerContent(title=session.title, sections=[]),
                container=container,
                focus_component=selector,
            )
        )
        try:
            choice = self.run_prompt_step(
                PromptStep(prompt_text=session.select_prompt_text, strip=True)
            )
            selected_option = self.resolve_option_choice(choice, session.options)
            if selected_option is None:
                return SelectionEditResult(option=None, edited_value=None)
            selector.selected_index = session.options.index(selected_option)

            self.focus_next_component()
            container.sync_editor_initial_value(
                selected_option,
                use_selected_description_as_initial=session.use_selected_description_as_initial,
            )
            self.open_container(
                ContainerContent(title=session.edit_title, sections=[]),
                container,
            )
            edited = self.run_prompt_step(PromptStep(prompt_text=session.edit_prompt_text))
            editor_state.value = edited
            return SelectionEditResult(option=selected_option, edited_value=edited)
        finally:
            self.end_overlay_session()

    def choose_and_edit(
        self,
        *,
        title: str,
        options: list[SelectOption],
        edit_title: str,
        edit_note: str | None = None,
        use_selected_description_as_initial: bool = True,
    ) -> SelectionEditResult:
        return self.run_selection_editor_session(
            SelectionEditorSession(
                title=title,
                options=options,
                edit_title=edit_title,
                edit_note=edit_note,
                use_selected_description_as_initial=use_selected_description_as_initial,
            )
        )

    def run_selection_action_session(
        self,
        session: SelectionActionSession,
    ) -> SelectionActionResult:
        selector = SelectListView(
            [(option.label, option.description) for option in session.options],
            selected_index=session.default_option_index,
        )
        action_list = SelectListView(
            [(option.label, option.description) for option in session.actions],
            selected_index=session.default_action_index,
        )
        container = SelectionActionContainer(
            selector=selector,
            actions=action_list,
            action_title=session.action_title,
        )
        components: list[Component] = []
        if session.header_component is not None:
            components.append(session.header_component)
        if session.note:
            components.append(TextBlock(session.note))
        browser_container: Container = container
        if components:
            components.append(container)
            browser_container = FocusContainer(components, selected_index=len(components) - 1)
        self.begin_overlay_session(
            OverlaySession(
                content=ContainerContent(title=session.title, sections=[]),
                container=browser_container,
                focus_component=selector,
            )
        )
        try:
            choice = self.run_prompt_step(
                PromptStep(prompt_text=session.select_prompt_text, strip=True)
            )
            selected_option = self.resolve_option_choice(choice, session.options)
            if selected_option is None:
                return SelectionActionResult(option=None, action=None)
            selector.selected_index = session.options.index(selected_option)

            self.focus_next_component()
            self.open_container(
                ContainerContent(title=session.title, sections=[]),
                browser_container,
            )
            action_choice = self.run_prompt_step(
                PromptStep(prompt_text=session.action_prompt_text, strip=True)
            )
            selected_action = self.resolve_option_choice(action_choice, session.actions)
            if selected_action is None:
                return SelectionActionResult(option=selected_option, action=None)
            action_list.selected_index = session.actions.index(selected_action)
            return SelectionActionResult(option=selected_option, action=selected_action)
        finally:
            self.end_overlay_session()

    def run_tree_browser_session(
        self,
        session: TreeBrowserSession,
    ) -> TreeBrowserResult:
        selector = TreeListView(
            session.entries,
            selected_index=session.default_entry_index,
        )
        action_list = SelectListView(
            [(option.label, option.description) for option in session.actions],
            selected_index=session.default_action_index,
        )
        container = TreeBrowserContainer(
            selector=selector,
            actions=action_list,
            action_title=session.action_title,
            state=session.state,
        )
        components: list[Component] = []
        if session.header_component is not None:
            components.append(session.header_component)
        if session.note:
            components.append(TextBlock(session.note))
        browser_container: Container = container
        if components:
            components.append(container)
            browser_container = FocusContainer(components, selected_index=len(components) - 1)
        self.begin_overlay_session(
            OverlaySession(
                content=ContainerContent(title=session.title, sections=[]),
                container=browser_container,
                focus_component=selector,
            )
        )
        try:
            choice = self.run_prompt_step(
                PromptStep(prompt_text=session.select_prompt_text, strip=True)
            )
            selected_entry = self.resolve_tree_choice(choice, session.entries)
            if selected_entry is None:
                return TreeBrowserResult(entry=None, action=None)
            container.select_index(session.entries.index(selected_entry))

            self.focus_next_component()
            self.open_container(
                ContainerContent(title=session.title, sections=[]),
                browser_container,
            )
            action_choice = self.run_prompt_step(
                PromptStep(prompt_text=session.action_prompt_text, strip=True)
            )
            selected_action = self.resolve_option_choice(action_choice, session.actions)
            if selected_action is None:
                return TreeBrowserResult(entry=selected_entry, action=None)
            action_list.selected_index = session.actions.index(selected_action)
            return TreeBrowserResult(entry=selected_entry, action=selected_action)
        finally:
            self.end_overlay_session()
