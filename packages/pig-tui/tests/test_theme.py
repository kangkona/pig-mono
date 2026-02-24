"""Tests for theme."""

from pig_tui.theme import Theme


def test_theme_defaults():
    """Test default theme values."""
    theme = Theme()
    assert theme.user_color == "cyan"
    assert theme.assistant_color == "green"
    assert theme.system_color == "yellow"
    assert theme.error_color == "red"


def test_theme_custom():
    """Test custom theme values."""
    theme = Theme(
        user_color="blue",
        assistant_color="magenta",
    )
    assert theme.user_color == "blue"
    assert theme.assistant_color == "magenta"


def test_theme_dark():
    """Test dark theme."""
    theme = Theme.dark()
    assert theme.user_color == "cyan"
    assert theme.assistant_color == "green"


def test_theme_light():
    """Test light theme."""
    theme = Theme.light()
    assert theme.user_color == "blue"
    assert theme.assistant_color == "green"
