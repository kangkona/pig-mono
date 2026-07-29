"""Tests for chat UI."""

from typing import Any, cast
from unittest.mock import patch

from pig_tui.chat import ChatUI, MarkdownStreamWriter
from pig_tui.rendering import normalize_markdown_for_terminal
from pig_tui.theme import Theme


def _console_mock(chat: ChatUI) -> Any:
    """Return the patched console with its runtime mock surface."""
    return cast(Any, chat.console)


@patch("pig_tui.chat.Console")
def test_chat_ui_creation(mock_console: Any) -> None:
    """Test creating chat UI."""
    chat = ChatUI(title="Test Chat")
    assert chat.title == "Test Chat"
    assert chat.show_timestamps is False
    assert chat.markdown_mode is True


@patch("pig_tui.chat.Console")
def test_chat_ui_with_theme(mock_console: Any) -> None:
    """Test chat UI with custom theme."""
    theme = Theme(user_color="blue")
    chat = ChatUI(theme=theme)
    assert chat.theme.user_color == "blue"


@patch("pig_tui.chat.Console")
def test_chat_ui_user_message(mock_console: Any) -> None:
    """Test displaying user message."""
    chat = ChatUI()
    chat.user("Hello!")

    # Verify console.print was called
    _console_mock(chat).print.assert_called()


@patch("pig_tui.chat.Console")
def test_chat_ui_assistant_message(mock_console: Any) -> None:
    """Test displaying assistant message."""
    chat = ChatUI()
    chat.assistant("Hi there!")

    _console_mock(chat).print.assert_called()


@patch("pig_tui.chat.Console")
@patch("pig_tui.chat.Markdown")
def test_chat_ui_normalizes_markdown_before_render(mock_markdown: Any, mock_console: Any) -> None:
    chat = ChatUI()

    chat.assistant("10. keep marker\n- [x] done")

    mock_markdown.assert_called_once_with(
        normalize_markdown_for_terminal("10. keep marker\n- [x] done")
    )


@patch("pig_tui.chat.Console")
@patch("pig_tui.chat.Markdown", side_effect=ValueError("markdown exploded"))
def test_chat_ui_falls_back_to_plain_text_when_markdown_render_fails(
    mock_markdown: Any, mock_console: Any
) -> None:
    chat = ChatUI()

    chat.assistant("# Hello")

    calls = _console_mock(chat).print.call_args_list
    assert calls[0].args[0].endswith("Assistant:[/] ")
    assert calls[0].kwargs["end"] == ""
    assert calls[1].args == ("# Hello",)


@patch("pig_tui.chat.Console")
@patch("pig_tui.chat.Markdown", return_value=object())
def test_chat_ui_falls_back_to_plain_text_when_printing_rendered_markdown_fails(
    mock_markdown: Any, mock_console: Any
) -> None:
    chat = ChatUI()
    _console_mock(chat).print.side_effect = [None, RuntimeError("render exploded"), None]

    chat.assistant("# Hello")

    calls = _console_mock(chat).print.call_args_list
    assert calls[0].args[0].endswith("Assistant:[/] ")
    assert calls[0].kwargs["end"] == ""
    assert calls[1].args == (mock_markdown.return_value,)
    assert calls[2].args == ("# Hello",)


@patch("pig_tui.chat.Console")
def test_chat_ui_system_message(mock_console: Any) -> None:
    """Test displaying system message."""
    chat = ChatUI()
    chat.system("System ready")

    _console_mock(chat).print.assert_called()


@patch("pig_tui.chat.Console")
def test_chat_ui_system_message_normalizes_thai_and_lao_am(mock_console: Any) -> None:
    chat = ChatUI()
    chat.system("ำabc ຳdef")

    rendered = _console_mock(chat).print.call_args.args[0]
    assert "ําabc" in rendered
    assert "ໍາdef" in rendered


@patch("pig_tui.chat.Console")
def test_assistant_stream_normalizes_thai_and_lao_am(mock_console: Any) -> None:
    chat = ChatUI()

    with chat.assistant_stream() as writer:
        writer.write("ำabc ຳdef")

    stream_call = _console_mock(chat).print.call_args_list[0]
    assert stream_call.args == ("ําabc ໍາdef",)
    assert stream_call.kwargs["end"] == ""


@patch("pig_tui.chat.Console")
def test_chat_ui_error_message(mock_console: Any) -> None:
    """Test displaying error message."""
    chat = ChatUI()
    chat.error("Error occurred")

    _console_mock(chat).print.assert_called()


@patch("pig_tui.chat.Console")
def test_chat_ui_with_timestamps(mock_console: Any) -> None:
    """Test chat with timestamps."""
    chat = ChatUI(show_timestamps=True)
    assert chat.show_timestamps is True

    chat.user("Hello")
    # Timestamp should be included
    _console_mock(chat).print.assert_called()


@patch("pig_tui.chat.Console")
def test_chat_ui_separator(mock_console: Any) -> None:
    """Test separator."""
    chat = ChatUI()
    chat.separator()

    _console_mock(chat).rule.assert_called_once()


@patch("pig_tui.chat.Console")
def test_chat_ui_clear(mock_console: Any) -> None:
    """Test clearing chat."""
    chat = ChatUI()
    chat.clear()

    _console_mock(chat).clear.assert_called_once()


def test_assistant_stream_markdown_renders_accumulated_markdown() -> None:
    """The markdown stream writer accumulates text and live-renders it."""
    import io
    import re

    chat = ChatUI()
    chat.console.file = io.StringIO()

    with chat.assistant_stream_markdown(refresh_per_second=4) as writer:
        writer.write("# Heading\n")
        writer.write("- item one\n")
        writer.write("- item two")

    assert writer.text == "# Heading\n- item one\n- item two"
    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", chat.console.file.getvalue())
    assert "Heading" in plain
    assert "item one" in plain


def test_markdown_stream_writer_shows_then_drops_status_spinner() -> None:
    """A spinner + elapsed status shows while busy and is dropped on finalize."""
    import io
    import re

    from rich.console import Console

    def render(renderable: Any) -> str:
        buf = io.StringIO()
        Console(file=buf, force_terminal=True, width=40).print(renderable)
        return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", buf.getvalue())

    writer = MarkdownStreamWriter()
    # Busy with no content yet -> status line only.
    assert "working" in render(writer._renderable())
    # Busy with content -> content + status.
    writer.write("# Hi")
    out = render(writer._renderable())
    assert "Hi" in out and "working" in out
    # Finalized -> status dropped.
    writer.finalize()
    final = render(writer._renderable())
    assert "Hi" in final and "working" not in final


def test_markdown_stream_writer_shows_input_affordance() -> None:
    """A 'You ›' input line shows the in-progress steering text during a turn."""
    import io
    import re

    from rich.console import Console

    def render(r: Any) -> str:
        buf = io.StringIO()
        Console(file=buf, force_terminal=True, width=50).print(r)
        return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", buf.getvalue())

    writer = MarkdownStreamWriter()
    assert "You ›" in render(writer._renderable())
    writer.set_input("add an AI mode")
    assert "add an AI mode" in render(writer._renderable())
    writer.finalize()
    assert "You ›" not in render(writer._renderable())


def test_markdown_stream_writer_keeps_runtime_events_in_transcript() -> None:
    import io
    import re

    chat = ChatUI()
    chat.console.file = io.StringIO()

    with chat.assistant_stream_markdown(refresh_per_second=4) as writer:
        writer.write("hello")
        chat.user("!steer now")
        chat.system("queued steer")
        writer.write(" world")

    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", chat.console.file.getvalue())
    assert "User: !steer now" in plain
    assert "System: queued steer" in plain
    assert "hello world" in plain
