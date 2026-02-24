"""Tests for chat UI."""

from unittest.mock import Mock, patch
from pig_tui.chat import ChatUI
from pig_tui.theme import Theme


@patch('pig_tui.chat.Console')
def test_chat_ui_creation(mock_console):
    """Test creating chat UI."""
    chat = ChatUI(title="Test Chat")
    assert chat.title == "Test Chat"
    assert chat.show_timestamps is False
    assert chat.markdown_mode is True


@patch('pig_tui.chat.Console')
def test_chat_ui_with_theme(mock_console):
    """Test chat UI with custom theme."""
    theme = Theme(user_color="blue")
    chat = ChatUI(theme=theme)
    assert chat.theme.user_color == "blue"


@patch('pig_tui.chat.Console')
def test_chat_ui_user_message(mock_console):
    """Test displaying user message."""
    chat = ChatUI()
    chat.user("Hello!")
    
    # Verify console.print was called
    chat.console.print.assert_called()


@patch('pig_tui.chat.Console')
def test_chat_ui_assistant_message(mock_console):
    """Test displaying assistant message."""
    chat = ChatUI()
    chat.assistant("Hi there!")
    
    chat.console.print.assert_called()


@patch('pig_tui.chat.Console')
def test_chat_ui_system_message(mock_console):
    """Test displaying system message."""
    chat = ChatUI()
    chat.system("System ready")
    
    chat.console.print.assert_called()


@patch('pig_tui.chat.Console')
def test_chat_ui_error_message(mock_console):
    """Test displaying error message."""
    chat = ChatUI()
    chat.error("Error occurred")
    
    chat.console.print.assert_called()


@patch('pig_tui.chat.Console')
def test_chat_ui_with_timestamps(mock_console):
    """Test chat with timestamps."""
    chat = ChatUI(show_timestamps=True)
    assert chat.show_timestamps is True
    
    chat.user("Hello")
    # Timestamp should be included
    chat.console.print.assert_called()


@patch('pig_tui.chat.Console')
def test_chat_ui_separator(mock_console):
    """Test separator."""
    chat = ChatUI()
    chat.separator()
    
    chat.console.rule.assert_called_once()


@patch('pig_tui.chat.Console')
def test_chat_ui_clear(mock_console):
    """Test clearing chat."""
    chat = ChatUI()
    chat.clear()
    
    chat.console.clear.assert_called_once()
