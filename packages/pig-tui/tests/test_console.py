"""Tests for console."""

from typing import Any, cast
from unittest.mock import patch

from pig_tui.console import Console


def _rich_console_mock(console: Console) -> Any:
    """Return the patched Rich console with its runtime mock surface."""
    return cast(Any, console.console)


def test_console_creation() -> None:
    """Test creating a console."""
    console = Console()
    assert console.theme == "monokai"


def test_console_custom_theme() -> None:
    """Test console with custom theme."""
    console = Console(theme="solarized")
    assert console.theme == "solarized"


@patch("pig_tui.console.RichConsole")
def test_console_print(mock_rich_console: Any) -> None:
    """Test console print."""
    console = Console()
    console.print("Hello", style="bold")

    # Verify rich console print was called
    _rich_console_mock(console).print.assert_called_once()


@patch("pig_tui.console.RichConsole")
def test_console_print_normalizes_thai_and_lao_am(mock_rich_console: Any) -> None:
    console = Console()

    console.print("ำabc", "ຳdef")

    args = _rich_console_mock(console).print.call_args.args
    assert args == ("ําabc", "ໍາdef")


@patch("pig_tui.console.RichConsole")
def test_console_markdown(mock_rich_console: Any) -> None:
    """Test markdown rendering."""
    console = Console()
    console.markdown("# Hello")

    _rich_console_mock(console).print.assert_called_once()


@patch("pig_tui.console.RichConsole")
@patch("pig_tui.console.Markdown", side_effect=ValueError("markdown exploded"))
def test_console_markdown_falls_back_to_plain_text_on_render_error(
    mock_markdown: Any, mock_rich_console: Any
) -> None:
    console = Console()

    console.markdown("# Hello")

    _rich_console_mock(console).print.assert_called_once_with("# Hello")


@patch("pig_tui.console.RichConsole")
@patch("pig_tui.console.Markdown", return_value=object())
def test_console_markdown_falls_back_to_plain_text_when_printing_rendered_markdown_fails(
    mock_markdown: Any, mock_rich_console: Any
) -> None:
    console = Console()
    _rich_console_mock(console).print.side_effect = [RuntimeError("render exploded"), None]

    console.markdown("# Hello")

    calls = _rich_console_mock(console).print.call_args_list
    assert calls[0].args == (mock_markdown.return_value,)
    assert calls[1].args == ("# Hello",)


@patch("pig_tui.console.RichConsole")
def test_console_code(mock_rich_console: Any) -> None:
    """Test code highlighting."""
    console = Console()
    console.code('print("hello")', language="python")

    _rich_console_mock(console).print.assert_called_once()


@patch("pig_tui.console.RichConsole")
def test_console_json(mock_rich_console: Any) -> None:
    """Test JSON printing."""
    console = Console()
    console.json({"key": "value"})

    _rich_console_mock(console).print.assert_called_once()


@patch("pig_tui.console.RichConsole")
def test_console_rule(mock_rich_console: Any) -> None:
    """Test rule printing."""
    console = Console()
    console.rule("Section")

    _rich_console_mock(console).rule.assert_called_once()


@patch("pig_tui.console.RichConsole")
def test_console_clear(mock_rich_console: Any) -> None:
    """Test clearing console."""
    console = Console()
    console.clear()

    _rich_console_mock(console).clear.assert_called_once()
