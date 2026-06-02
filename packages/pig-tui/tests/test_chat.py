"""Tests for chat UI."""

from unittest.mock import patch

from pig_tui.chat import ChatUI
from pig_tui.rendering import normalize_markdown_for_terminal
from pig_tui.theme import Theme


@patch("pig_tui.chat.Console")
def test_chat_ui_creation(mock_console):
    """Test creating chat UI."""
    chat = ChatUI(title="Test Chat")
    assert chat.title == "Test Chat"
    assert chat.show_timestamps is False
    assert chat.markdown_mode is True


@patch("pig_tui.chat.Console")
def test_chat_ui_with_theme(mock_console):
    """Test chat UI with custom theme."""
    theme = Theme(user_color="blue")
    chat = ChatUI(theme=theme)
    assert chat.theme.user_color == "blue"


@patch("pig_tui.chat.Console")
def test_chat_ui_user_message(mock_console):
    """Test displaying user message."""
    chat = ChatUI()
    chat.user("Hello!")

    # Verify console.print was called
    chat.console.print.assert_called()


@patch("pig_tui.chat.Console")
def test_chat_ui_assistant_message(mock_console):
    """Test displaying assistant message."""
    chat = ChatUI()
    chat.assistant("Hi there!")

    chat.console.print.assert_called()


@patch("pig_tui.chat.Console")
@patch("pig_tui.chat.Markdown")
def test_chat_ui_normalizes_markdown_before_render(mock_markdown, mock_console):
    chat = ChatUI()

    chat.assistant("10. keep marker\n- [x] done")

    mock_markdown.assert_called_once_with(
        normalize_markdown_for_terminal("10. keep marker\n- [x] done")
    )


@patch("pig_tui.chat.Console")
@patch("pig_tui.chat.Markdown", side_effect=ValueError("markdown exploded"))
def test_chat_ui_falls_back_to_plain_text_when_markdown_render_fails(mock_markdown, mock_console):
    chat = ChatUI()

    chat.assistant("# Hello")

    calls = chat.console.print.call_args_list
    assert calls[0].args[0].endswith("Assistant:[/] ")
    assert calls[0].kwargs["end"] == ""
    assert calls[1].args == ("# Hello",)


@patch("pig_tui.chat.Console")
@patch("pig_tui.chat.Markdown", return_value=object())
def test_chat_ui_falls_back_to_plain_text_when_printing_rendered_markdown_fails(
    mock_markdown, mock_console
):
    chat = ChatUI()
    chat.console.print.side_effect = [None, RuntimeError("render exploded"), None]

    chat.assistant("# Hello")

    calls = chat.console.print.call_args_list
    assert calls[0].args[0].endswith("Assistant:[/] ")
    assert calls[0].kwargs["end"] == ""
    assert calls[1].args == (mock_markdown.return_value,)
    assert calls[2].args == ("# Hello",)


@patch("pig_tui.chat.Console")
def test_chat_ui_system_message(mock_console):
    """Test displaying system message."""
    chat = ChatUI()
    chat.system("System ready")

    chat.console.print.assert_called()


@patch("pig_tui.chat.Console")
def test_chat_ui_system_message_normalizes_thai_and_lao_am(mock_console):
    chat = ChatUI()
    chat.system("ำabc ຳdef")

    rendered = chat.console.print.call_args.args[0]
    assert "ําabc" in rendered
    assert "ໍາdef" in rendered


@patch("pig_tui.chat.Console")
def test_assistant_stream_normalizes_thai_and_lao_am(mock_console):
    chat = ChatUI()

    with chat.assistant_stream() as writer:
        writer.write("ำabc ຳdef")

    stream_call = chat.console.print.call_args_list[0]
    assert stream_call.args == ("ําabc ໍາdef",)
    assert stream_call.kwargs["end"] == ""


@patch("pig_tui.chat.Console")
def test_chat_ui_error_message(mock_console):
    """Test displaying error message."""
    chat = ChatUI()
    chat.error("Error occurred")

    chat.console.print.assert_called()


@patch("pig_tui.chat.Console")
def test_chat_ui_with_timestamps(mock_console):
    """Test chat with timestamps."""
    chat = ChatUI(show_timestamps=True)
    assert chat.show_timestamps is True

    chat.user("Hello")
    # Timestamp should be included
    chat.console.print.assert_called()


@patch("pig_tui.chat.Console")
def test_chat_ui_separator(mock_console):
    """Test separator."""
    chat = ChatUI()
    chat.separator()

    chat.console.rule.assert_called_once()


@patch("pig_tui.chat.Console")
def test_chat_ui_clear(mock_console):
    """Test clearing chat."""
    chat = ChatUI()
    chat.clear()

    chat.console.clear.assert_called_once()
