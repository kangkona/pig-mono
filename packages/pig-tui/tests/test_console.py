"""Tests for console."""

from unittest.mock import Mock, patch
from pig_tui.console import Console


def test_console_creation():
    """Test creating a console."""
    console = Console()
    assert console.theme == "monokai"


def test_console_custom_theme():
    """Test console with custom theme."""
    console = Console(theme="solarized")
    assert console.theme == "solarized"


@patch('pig_tui.console.RichConsole')
def test_console_print(mock_rich_console):
    """Test console print."""
    console = Console()
    console.print("Hello", style="bold")
    
    # Verify rich console print was called
    console.console.print.assert_called_once()


@patch('pig_tui.console.RichConsole')
def test_console_markdown(mock_rich_console):
    """Test markdown rendering."""
    console = Console()
    console.markdown("# Hello")
    
    console.console.print.assert_called_once()


@patch('pig_tui.console.RichConsole')
def test_console_code(mock_rich_console):
    """Test code highlighting."""
    console = Console()
    console.code('print("hello")', language="python")
    
    console.console.print.assert_called_once()


@patch('pig_tui.console.RichConsole')
def test_console_json(mock_rich_console):
    """Test JSON printing."""
    console = Console()
    console.json({"key": "value"})
    
    console.console.print.assert_called_once()


@patch('pig_tui.console.RichConsole')
def test_console_rule(mock_rich_console):
    """Test rule printing."""
    console = Console()
    console.rule("Section")
    
    console.console.rule.assert_called_once()


@patch('pig_tui.console.RichConsole')
def test_console_clear(mock_rich_console):
    """Test clearing console."""
    console = Console()
    console.clear()
    
    console.console.clear.assert_called_once()
