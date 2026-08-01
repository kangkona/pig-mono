"""Tests for pig-tui runtime primitives."""

import asyncio
import threading
import time
from collections.abc import AsyncIterator
from typing import Any, Literal
from unittest.mock import Mock, patch

import pytest
from pig_tui.components import ConfirmView, SelectListView
from pig_tui.core import (
    ContainerContent,
    PanelContent,
    SelectionEditResult,
    SelectOption,
    StatusMessage,
    TreeBrowserResult,
    TreeBrowserState,
    TreeDetailState,
    TreeOption,
    TreePathState,
    TreeSummaryState,
)
from pig_tui.runtime import (
    EditorSession,
    FocusContainer,
    FocusManager,
    OverlaySession,
    OverlayStack,
    PromptStep,
    SelectionActionResult,
    SelectionActionSession,
    SelectionEditorSession,
    SelectionSession,
    ShellLoopResult,
    ShellLoopSession,
    StreamingTurnController,
    TerminalRuntime,
    TreeBrowserSession,
    TurnResult,
)


def test_focus_manager_tracks_and_restores_focus() -> None:
    manager = FocusManager()
    first = SelectListView([("a", None)])
    second = SelectListView([("b", None)])
    manager.focus("prompt", component=first)
    manager.focus("overlay", component=second)

    assert manager.current == "overlay"
    assert first.focused is False
    assert second.focused is True
    assert manager.restore_previous() == "prompt"
    assert manager.current == "prompt"
    assert second.focused is False


def test_focus_container_cycles_focusable_components() -> None:
    first = SelectListView([("a", None)])
    second = SelectListView([("b", None)])
    container = FocusContainer([first, second])

    assert container.current() is first
    assert first.focused is True
    assert second.focused is False

    assert container.focus_next() is second
    assert first.focused is False
    assert second.focused is True

    assert container.focus_previous() is first
    assert first.focused is True
    assert second.focused is False


def test_focus_container_skips_non_focusable_components() -> None:
    text = PanelContent(title="Info", content="display only")
    first = SelectListView([("a", None)])
    second = SelectListView([("b", None)])

    class _PanelAsComponent:
        def render(self, width: int) -> list[str]:
            return [text.content]

        def invalidate(self) -> None:
            return None

    container = FocusContainer([_PanelAsComponent(), first, second], selected_index=0)

    assert container.current() is first
    assert first.focused is True
    assert container.focus_next() is second


def test_overlay_stack_push_peek_pop() -> None:
    stack = OverlayStack()
    panel = PanelContent(title="Dialog", content="Hello")
    component = SelectListView([("a", None)])

    stack.push(panel, component)

    assert len(stack) == 1
    assert stack.peek() == panel
    popped = stack.pop()
    assert popped is not None
    popped_panel, popped_component = popped
    assert popped_panel == panel
    assert popped_component == component
    assert stack.peek() is None


def test_streaming_turn_controller_returns_content_and_abort_state() -> None:
    controller = StreamingTurnController(commands=["/help"])
    ui = Mock()
    writer = Mock()

    class _StreamCtx:
        def __enter__(self) -> Any:
            return writer

        def __exit__(self, *args: Any) -> Literal[False]:
            return False

    ui.assistant_stream_markdown.return_value = _StreamCtx()

    class _Listener:
        async def __aenter__(self) -> "_Listener":
            return self

        async def __aexit__(self, *args: Any) -> Literal[False]:
            return False

    async def stream() -> AsyncIterator[str]:
        yield "hello "
        yield "world"

    with patch("pig_tui.runtime.LiveInputListener", return_value=_Listener()):
        result = asyncio.run(controller.run(stream=stream(), ui=ui, on_steering=lambda _: None))

    assert isinstance(result, TurnResult)
    assert result.content == "hello world"
    assert result.aborted is False
    writer.write.assert_any_call("hello ")
    writer.write.assert_any_call("world")


def test_confirmation_during_stream_owns_terminal_and_is_not_timed_out() -> None:
    """A slow human confirmation must not run inside a tool worker timeout."""
    prompt_thread_ids: list[int] = []
    listener_events: list[str] = []
    writer_events: list[str] = []
    allowed: list[bool] = []
    runtime_thread_id: list[int] = []

    class _PromptRuntime:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def ask(self, prompt_text: str = "You> ") -> str:
            assert prompt_text == "Confirm> "
            prompt_thread_ids.append(threading.get_ident())
            time.sleep(0.05)
            return "yes"

    class _Writer:
        def write(self, text: str) -> None:
            del text

        def set_input(
            self,
            text: str,
            cursor: int | None = None,
            suggestions: list[str] | None = None,
        ) -> None:
            del text, cursor, suggestions

        def tick(self) -> None:
            return None

        def suspend(self) -> None:
            writer_events.append("suspend")

        def resume(self) -> None:
            writer_events.append("resume")

    writer = _Writer()

    class _StreamContext:
        def __enter__(self) -> _Writer:
            return writer

        def __exit__(self, *args: Any) -> Literal[False]:
            del args
            return False

    ui = Mock()
    ui.assistant_stream_markdown.return_value = _StreamContext()

    class _Listener:
        async def __aenter__(self) -> "_Listener":
            listener_events.append("enter")
            return self

        async def __aexit__(self, *args: Any) -> Literal[False]:
            del args
            listener_events.append("exit")
            return False

        def suspend(self) -> None:
            listener_events.append("suspend")

        def resume(self) -> None:
            listener_events.append("resume")

    def _turn_controller_factory(**kwargs: Any) -> StreamingTurnController:
        def _listener_factory(*args: Any, **listener_kwargs: Any) -> _Listener:
            del args, listener_kwargs
            return _Listener()

        return StreamingTurnController(
            commands=kwargs["commands"],
            live_input_listener_factory=_listener_factory,
        )

    prompt_runtime_factory: Any = _PromptRuntime
    runtime = TerminalRuntime(
        ui=ui,
        commands=["/help"],
        workspace=".",
        prompt_runtime_factory=prompt_runtime_factory,
        turn_controller_factory=_turn_controller_factory,
    )

    async def stream() -> AsyncIterator[str]:
        runtime_thread_id.append(threading.get_ident())
        loop = asyncio.get_running_loop()
        decision = await loop.run_in_executor(None, runtime.confirm, "Allow write?")
        allowed.append(decision)
        yield "done"

    result = asyncio.run(runtime.stream_turn(stream=stream(), on_steering=lambda _: None))

    assert result.content == "done"
    assert allowed == [True]
    assert prompt_thread_ids == runtime_thread_id
    assert listener_events == ["enter", "suspend", "resume", "exit"]
    assert writer_events == ["suspend", "resume"]


def test_terminal_runtime_tracks_prompt_focus() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "hello"
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        value = runtime.ask()

    assert value == "hello"
    assert runtime.focus.current == "prompt"


def test_terminal_runtime_exposes_display_output_surface() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")

    runtime.show_panel(PanelContent(title="Session", content="ID : abc"))
    runtime.show_text_panel("Raw", "content")
    runtime.show_status(StatusMessage("ok", "Ready"))
    runtime.show_error("Boom")
    runtime.show_system("Note")
    runtime.show_user("Hello")
    runtime.show_assistant("Hi")
    runtime.clear()
    runtime.separator()

    assert ui.panel.call_args_list[0].args[0] == "ID : abc"
    assert ui.panel.call_args_list[0].kwargs["title"] == "Session"
    assert ui.panel.call_args_list[1].args[0] == "content"
    assert ui.panel.call_args_list[1].kwargs["title"] == "Raw"
    ui.system.assert_any_call("[ok] Ready")
    ui.system.assert_any_call("Note")
    ui.error.assert_called_once_with("Boom")
    ui.user.assert_called_once_with("Hello")
    ui.assistant.assert_called_once_with("Hi")
    ui.clear.assert_called_once_with()
    ui.separator.assert_called_once_with()


def test_terminal_runtime_run_shell_loop_returns_eof_reason() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = EOFError()
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.run_shell_loop(ShellLoopSession(run_turn=lambda _: _never()))

    assert isinstance(result, ShellLoopResult)
    assert result.reason == "eof"


def test_terminal_runtime_run_shell_loop_handles_non_turn_input_and_continues() -> None:
    ui = Mock()
    handled: list[str] = []
    turns: list[str] = []

    async def _run_turn(user_input: str) -> None:
        turns.append(user_input)

    def _handle_input(text: str) -> bool:
        handled.append(text)
        return text.startswith("/")

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["/help", "hello", EOFError()]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.run_shell_loop(
            ShellLoopSession(
                run_turn=_run_turn,
                handle_input=_handle_input,
            )
        )

    assert result.reason == "eof"
    assert handled == ["/help", "hello"]
    assert turns == ["hello"]


def test_terminal_runtime_run_shell_loop_reuses_one_event_loop_across_turns() -> None:
    ui = Mock()
    loop_ids: list[int] = []

    async def _run_turn(user_input: str) -> None:
        del user_input
        loop_ids.append(id(asyncio.get_event_loop()))

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["first", "second", EOFError()]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.run_shell_loop(ShellLoopSession(run_turn=_run_turn))

    assert result.reason == "eof"
    assert len(loop_ids) == 2
    assert len(set(loop_ids)) == 1


def test_terminal_runtime_run_shell_loop_reports_turn_interrupt_and_continues() -> None:
    ui = Mock()
    turns: list[str] = []
    interrupts: list[str] = []

    async def _run_turn(user_input: str) -> None:
        if not turns:
            turns.append(user_input)
            raise KeyboardInterrupt()
        turns.append(user_input)

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["first", "second", EOFError()]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.run_shell_loop(
            ShellLoopSession(
                run_turn=_run_turn,
                on_turn_interrupt=lambda: interrupts.append("interrupt"),
            )
        )

    assert result.reason == "eof"
    assert turns == ["first", "second"]
    assert interrupts == ["interrupt"]


def test_terminal_runtime_run_shell_loop_can_re_raise_mapped_exception() -> None:
    ui = Mock()

    async def _run_turn(user_input: str) -> None:
        del user_input
        raise RuntimeError("lost terminal")

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["first"]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        with pytest.raises(RuntimeError, match="lost terminal"):
            runtime.run_shell_loop(
                ShellLoopSession(
                    run_turn=_run_turn,
                    exception_to_reason=lambda exc: (
                        "lost_terminal"
                        if isinstance(exc, RuntimeError) and "lost terminal" in str(exc)
                        else None
                    ),
                    re_raise_mapped_exceptions=True,
                )
            )


async def _never() -> None:
    raise AssertionError("run_turn should not be called")


def test_prompt_runtime_reuses_underlying_prompt_instance() -> None:
    from pig_tui.runtime import PromptRuntime

    prompt = Mock()
    prompt.ask.return_value = "hello"
    factory = Mock(return_value=prompt)

    runtime = PromptRuntime(commands=["/help"], prompt_factory=factory)

    assert runtime.ask() == "hello"
    assert runtime._prompt_instance() is prompt
    factory.assert_called_once()


def test_terminal_runtime_overlay_focuses_component() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    component = SelectListView([("item", None)])
    panel = PanelContent(title="Overlay", content="content")

    runtime.push_overlay(panel, component=component)

    assert runtime.focus.current == "overlay"
    assert component.focused is True
    assert runtime.active_container is not None
    assert runtime.pop_overlay() == panel
    assert component.focused is False


def test_terminal_runtime_delegates_stream_turn_and_restores_focus() -> None:
    ui = Mock()

    with (
        patch("pig_tui.runtime.PromptRuntime"),
        patch("pig_tui.runtime.StreamingTurnController") as controller_cls,
    ):
        controller = Mock()

        async def _run(**kwargs: Any) -> TurnResult:
            return TurnResult(content="done", aborted=False)

        controller.run = Mock(side_effect=_run)
        controller_cls.return_value = controller

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        runtime.focus.focus("prompt")

        async def empty_stream() -> AsyncIterator[str]:
            if False:
                yield ""

        result = asyncio.run(runtime.stream_turn(stream=empty_stream(), on_steering=lambda _: None))

    assert result.content == "done"
    assert runtime.focus.current == "prompt"


def test_terminal_runtime_select_returns_explicit_option_value() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "2"
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        value = runtime.select(
            "Resume Session",
            [
                SelectOption(value="session-a.jsonl", label="Session A", description="recent"),
                SelectOption(value="session-b.jsonl", label="Session B", description="older"),
            ],
        )

    assert value == "session-b.jsonl"
    assert runtime.focus.current == "prompt"
    ui.panel.assert_called_once()


def test_terminal_runtime_select_option_returns_structured_option() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "2"
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        option = runtime.select_option(
            "Resume Session",
            [
                SelectOption(value="session-a.jsonl", label="Session A", description="recent"),
                SelectOption(value="session-b.jsonl", label="Session B", description="older"),
            ],
        )

    assert option is not None
    assert option.value == "session-b.jsonl"
    assert option.label == "Session B"


def test_terminal_runtime_run_selection_session_supports_header_component() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "yes"
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        option = runtime.run_selection_session(
            SelectionSession(
                title="Confirm",
                options=[
                    SelectOption("yes", "Yes", aliases=("y", "yes")),
                    SelectOption("no", "No", aliases=("n", "no")),
                ],
                prompt_text="Confirm> ",
                header_component=ConfirmView("Allow delete?", default=False),
            )
        )

    assert option is not None
    assert option.value == "yes"


def test_terminal_runtime_resolve_option_choice_supports_index_and_labels() -> None:
    options = [
        SelectOption(value="session-a", label="Session A", description="recent"),
        SelectOption(value="session-b", label="Session B", description="older"),
    ]

    assert TerminalRuntime.resolve_option_choice("2", options) == options[1]
    assert TerminalRuntime.resolve_option_choice("Session A", options) == options[0]
    assert TerminalRuntime.resolve_option_choice("session-b", options) == options[1]
    assert TerminalRuntime.resolve_option_choice("missing", options) is None


def test_terminal_runtime_edit_text_uses_overlay_and_returns_updated_value() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "Renamed Session"
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        value = runtime.edit_text(
            "Rename Session",
            initial_value="Original Session",
            note="Press enter to save",
        )

    assert value == "Renamed Session"
    assert runtime.focus.current == "prompt"
    ui.panel.assert_called_once()


def test_terminal_runtime_run_editor_session_returns_updated_value() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "edited"
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        value = runtime.run_editor_session(
            EditorSession(title="Rename", initial_value="original", note="Edit it")
        )

    assert value == "edited"
    assert runtime.focus.current == "prompt"


def test_terminal_runtime_set_active_container_updates_focus() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    first = SelectListView([("a", None)])
    second = SelectListView([("b", None)])
    container = FocusContainer([first, second])

    runtime.set_active_container(container)

    assert runtime.active_container is container
    assert runtime.focus.current == "container"
    assert first.focused is True


def test_terminal_runtime_focus_next_component_uses_active_container() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    first = SelectListView([("a", None)])
    second = SelectListView([("b", None)])
    container = FocusContainer([first, second])
    runtime.set_active_container(container)

    current = runtime.focus_next_component()

    assert current is second
    assert runtime.focus.current == "container"
    assert first.focused is False
    assert second.focused is True


def test_terminal_runtime_focus_component_index_selects_specific_section() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    first = SelectListView([("a", None)])
    second = SelectListView([("b", None)])
    container = FocusContainer([first, second])
    runtime.set_active_container(container)

    current = runtime.focus_component_index(1)

    assert current is second
    assert runtime.focus.current == "container"
    assert first.focused is False
    assert second.focused is True


def test_terminal_runtime_open_container_sets_active_container_and_renders_panel() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    first = SelectListView([("a", None)])
    second = SelectListView([("b", None)])
    container = FocusContainer([first, second])

    runtime.open_container(
        ContainerContent(title="Container", sections=["first", "second"]),
        container,
    )

    assert runtime.active_container is container
    assert runtime.focus.current == "container"
    ui.panel.assert_called_once_with("=> a\n\n-> b", title="Container")


def test_terminal_runtime_open_container_prefers_container_rendered_sections() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    view = SelectListView([("session-a", "recent")])
    container = FocusContainer([view])

    runtime.open_container(
        ContainerContent(title="Container", sections=["fallback"]),
        container,
    )

    rendered = "\n".join(view.render(100))
    ui.panel.assert_called_once_with(rendered, title="Container")


def test_terminal_runtime_begin_overlay_session_sets_runtime_owned_state() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    selector = SelectListView([("session-a", "recent")])
    container = FocusContainer([selector])

    runtime.begin_overlay_session(
        OverlaySession(
            content=ContainerContent(title="Overlay", sections=["fallback"]),
            container=container,
            focus_component=selector,
        )
    )

    assert runtime.active_container is container
    assert runtime.focus.current == "container"
    assert len(runtime.overlays) == 1
    ui.panel.assert_called_once()


def test_terminal_runtime_end_overlay_session_restores_prompt_focus() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    selector = SelectListView([("session-a", "recent")])
    container = FocusContainer([selector])
    runtime.focus.focus("prompt")

    runtime.begin_overlay_session(
        OverlaySession(
            content=ContainerContent(title="Overlay", sections=["fallback"]),
            container=container,
            focus_component=selector,
        )
    )
    runtime.end_overlay_session()

    assert runtime.focus.current == "prompt"
    assert runtime.active_container is None
    assert len(runtime.overlays) == 0


def test_terminal_runtime_end_overlay_session_restores_previous_container() -> None:
    ui = Mock()
    runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
    base = FocusContainer([SelectListView([("root", None)])])
    selector = SelectListView([("child", None)])
    overlay = FocusContainer([selector])

    runtime.set_active_container(base)
    runtime.begin_overlay_session(
        OverlaySession(
            content=ContainerContent(title="Overlay", sections=["fallback"]),
            container=overlay,
            focus_component=selector,
        )
    )
    runtime.end_overlay_session()

    assert runtime.active_container is base
    assert runtime.focus.current == "container"


def test_terminal_runtime_run_prompt_step_restores_prompt_focus_for_input() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "  session-a  "
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        value = runtime.run_prompt_step(PromptStep(prompt_text="Select> ", strip=True))

    assert value == "session-a"
    assert runtime.focus.current == "prompt"


def test_terminal_runtime_confirm_is_first_class_runtime_api() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "yes"
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        allowed = runtime.confirm("Allow delete?", default=True)

    assert allowed is True
    assert runtime.focus.current == "prompt"
    prompt_runtime.ask.assert_called_once_with("Confirm> ")
    ui.panel.assert_called_once()


def test_terminal_runtime_confirm_supports_negative_aliases() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.return_value = "n"
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        allowed = runtime.confirm("Allow delete?", default=True)

    assert allowed is False


def test_terminal_runtime_choose_and_edit_returns_selection_and_value() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["2", "0.5"]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.choose_and_edit(
            title="Edit Setting",
            options=[
                SelectOption("auto_compact", "auto_compact", "True"),
                SelectOption("auto_compact_threshold", "auto_compact_threshold", "0.85"),
            ],
            edit_title="Edit Value",
            edit_note="Enter the new value",
        )

    assert isinstance(result, SelectionEditResult)
    assert result.option is not None
    assert result.option.value == "auto_compact_threshold"
    assert result.edited_value == "0.5"
    assert runtime.focus.current == "prompt"
    assert ui.panel.call_count == 2


def test_terminal_runtime_run_selection_editor_session_returns_structured_result() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["2", "0.5"]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.run_selection_editor_session(
            SelectionEditorSession(
                title="Edit Setting",
                options=[
                    SelectOption("auto_compact", "auto_compact", "True"),
                    SelectOption("auto_compact_threshold", "auto_compact_threshold", "0.85"),
                ],
                edit_title="Edit Value",
                edit_note="Enter the new value",
            )
        )

    assert result.option is not None
    assert result.option.value == "auto_compact_threshold"
    assert result.edited_value == "0.5"


def test_terminal_runtime_run_selection_action_session_returns_structured_result() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["2", "label"]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.run_selection_action_session(
            SelectionActionSession(
                title="Tree Browser",
                options=[
                    SelectOption("entry-a", "Entry A", "current"),
                    SelectOption("entry-b", "Entry B", "older"),
                ],
                actions=[
                    SelectOption("switch", "Switch branch"),
                    SelectOption("label", "Label entry"),
                ],
                action_title="Actions",
            )
        )

    assert isinstance(result, SelectionActionResult)
    assert result.option is not None
    assert result.option.value == "entry-b"
    assert result.action is not None
    assert result.action.value == "label"


def test_terminal_runtime_run_tree_browser_session_returns_structured_result() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["2", "switch"]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.run_tree_browser_session(
            TreeBrowserSession(
                title="Tree Browser",
                entries=[
                    TreeOption("root", "root", "tip", depth=0, is_branch_point=True),
                    TreeOption(
                        "child",
                        "child",
                        "current",
                        depth=1,
                        is_current=True,
                        is_anchor=True,
                    ),
                ],
                actions=[
                    SelectOption("switch", "Switch branch"),
                    SelectOption("label", "Label entry"),
                ],
                action_title="Actions",
                state=TreeBrowserState(
                    scope="children",
                    anchor_entry_id="child-id",
                    anchor_label="[assistant] child...",
                    summary="1 entry visible | current tip: child",
                    breadcrumbs="root > child",
                ),
            )
        )

    assert isinstance(result, TreeBrowserResult)
    assert result.entry is not None
    assert result.entry.value == "child"
    assert result.action is not None
    assert result.action.value == "switch"


def test_terminal_runtime_run_tree_browser_session_supports_note_wrapped_container() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["2", "switch"]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        result = runtime.run_tree_browser_session(
            TreeBrowserSession(
                title="Tree Browser",
                entries=[
                    TreeOption(
                        "child-a",
                        "[assistant] child a...",
                        depth=1,
                        detail_state=TreeDetailState(
                            role="assistant",
                            short_id="child111",
                            depth=1,
                            children_count=0,
                            label=None,
                            preview="child a",
                            path_length=2,
                            path_labels=("root", "child-a"),
                        ),
                    ),
                    TreeOption(
                        "child-b",
                        "[assistant] child b...",
                        depth=1,
                        detail_state=TreeDetailState(
                            role="assistant",
                            short_id="child222",
                            depth=1,
                            children_count=1,
                            label="milestone",
                            preview="child b",
                            path_length=2,
                            path_labels=("root", "child-b"),
                        ),
                    ),
                ],
                actions=[SelectOption("switch", "Switch branch")],
                action_title="Actions",
                note="Scoped browser note",
                state=TreeBrowserState(
                    scope="children",
                    selected_entry_id="child-a",
                    anchor_entry_id="root",
                    path_state=TreePathState(parts=("root",), anchor_label="root"),
                    summary_state=TreeSummaryState(
                        visible_count=2,
                        total_count=4,
                        current_path_length=2,
                        current_entry_short_id="child222",
                    ),
                ),
            )
        )

    assert isinstance(result, TreeBrowserResult)
    assert result.entry is not None
    assert result.entry.value == "child-b"
    assert ui.panel.call_count >= 2
    first_call = ui.panel.call_args_list[0]
    second_call = ui.panel.call_args_list[1]
    assert "Scoped browser note" in first_call.args[0]
    assert "Tree [children]" in first_call.args[0]
    assert "ID: child222" in second_call.args[0]
    assert "Path: root > child-b" in second_call.args[0]


def test_terminal_runtime_choose_and_edit_prefills_editor_from_selected_option_description() -> (
    None
):
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["2", "0.9"]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        runtime.choose_and_edit(
            title="Edit Setting",
            options=[
                SelectOption("auto_compact", "auto_compact", "True"),
                SelectOption("auto_compact_threshold", "auto_compact_threshold", "0.85"),
            ],
            edit_title="Edit Value",
            edit_note="Enter the new value",
        )

    second_call = ui.panel.call_args_list[1]
    assert "0.85" in second_call.args[0]


def test_terminal_runtime_choose_and_edit_uses_multi_component_container() -> None:
    ui = Mock()

    with patch("pig_tui.runtime.PromptRuntime") as prompt_runtime_cls:
        prompt_runtime = Mock()
        prompt_runtime.ask.side_effect = ["1", "new value"]
        prompt_runtime_cls.return_value = prompt_runtime

        runtime = TerminalRuntime(ui=ui, commands=["/help"], workspace=".")
        runtime.choose_and_edit(
            title="Edit Setting",
            options=[SelectOption("x", "x", "1")],
            edit_title="Edit Value",
        )

    # First panel render should come from a container that owns multiple components.
    first_call = ui.panel.call_args_list[0]
    assert "\n\n" in first_call.args[0]
