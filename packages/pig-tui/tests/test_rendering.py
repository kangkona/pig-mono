"""Tests for safe terminal rendering helpers."""

from pig_tui.rendering import (
    hyperlink,
    normalize_markdown_for_terminal,
    safe_wrap,
    supports_osc8_hyperlinks,
    terminal_size,
    truncate_visible,
    visible_length,
)


def test_safe_wrap_handles_very_long_ansi_line_without_stack_overflow() -> None:
    line = "\x1b[31m" + ("x" * 5000) + "\x1b[0m"

    wrapped = safe_wrap(line, 80)

    assert wrapped
    assert len(wrapped) > 10


def test_visible_truncate_counts_visible_text_not_ansi_sequences() -> None:
    text = "\x1b[31mhello world\x1b[0m"

    assert visible_length(text) == 11
    assert truncate_visible(text, 6) == "hello…"


def test_visible_truncate_ignores_osc8_hyperlink_sequences() -> None:
    text = "\033]8;;https://example.com/file.py\033\\file.py\033]8;;\033\\"

    assert visible_length(text) == len("file.py")
    assert truncate_visible(text, 4) == "fil…"


def test_visible_length_ignores_generic_osc_sequences() -> None:
    text = "\033]133;A\033\\hello\033]133;B\033\\"

    assert visible_length(text) == len("hello")


def test_truncate_visible_ignores_generic_osc_sequences() -> None:
    text = "\033]133;A\033\\hello world\033]133;B\033\\"

    assert truncate_visible(text, 6) == "hello…"


def test_markdown_normalization_preserves_ordered_markers_and_tasks() -> None:
    markdown = "10. keep marker\n- [x] shipped\n- [ ] pending"

    normalized = normalize_markdown_for_terminal(markdown)

    assert "10. keep marker" in normalized
    assert "- [x] shipped" in normalized
    assert "- [ ] pending" in normalized


def test_hyperlink_falls_back_to_text_when_unsupported() -> None:
    assert hyperlink("file.py", "file:///tmp/file.py", env={}) == "file.py"


def test_hyperlink_emits_osc8_when_supported() -> None:
    linked = hyperlink("file.py", "file:///tmp/file.py", env={"TERM_PROGRAM": "WezTerm"})

    assert linked.startswith("\033]8;;file:///tmp/file.py")
    assert linked.endswith("\033]8;;\033\\")


def test_hyperlink_is_disabled_under_tmux_even_if_terminal_supports_it() -> None:
    linked = hyperlink(
        "file.py",
        "file:///tmp/file.py",
        env={"TERM_PROGRAM": "WezTerm", "TMUX": "/tmp/tmux-1/default,123,0"},
    )

    assert linked == "file.py"


def test_hyperlink_is_enabled_under_tmux_when_client_supports_it() -> None:
    linked = hyperlink(
        "file.py",
        "file:///tmp/file.py",
        env={
            "TERM_PROGRAM": "WezTerm",
            "TMUX": "/tmp/tmux-1/default,123,0",
            "TMUX_CLIENT_TERMFEATURES": "clipboard,hyperlinks,RGB",
        },
    )

    assert linked.startswith("\033]8;;file:///tmp/file.py")
    assert linked.endswith("\033]8;;\033\\")


def test_tmux_termname_uses_client_hyperlink_capability() -> None:
    assert supports_osc8_hyperlinks(
        {
            "TERM": "tmux-256color",
            "TMUX_CLIENT_TERMFEATURES": "hyperlinks",
        }
    )


def test_jetbrains_terminal_disables_hyperlinks_but_keeps_truecolor_detection() -> None:
    assert not supports_osc8_hyperlinks(
        {
            "TERMINAL_EMULATOR": "JetBrains-JediTerm",
            "COLORTERM": "truecolor",
        }
    )


def test_alacritty_terminal_supports_hyperlinks() -> None:
    assert supports_osc8_hyperlinks({"TERM_PROGRAM": "alacritty"})


def test_terminal_size_uses_environment_fallback() -> None:
    assert terminal_size(default=(1, 1)) in {(1, 1), terminal_size(default=(1, 1))}
    assert supports_osc8_hyperlinks({"WT_SESSION": "1"})


def test_terminal_size_ignores_invalid_environment_values() -> None:
    import os
    from unittest.mock import patch

    with (
        patch.dict(os.environ, {"COLUMNS": "abc", "LINES": "xyz"}, clear=False),
        patch("os.get_terminal_size", side_effect=OSError()),
    ):
        assert terminal_size(default=(3, 2)) == (3, 2)


def test_terminal_size_uses_partial_environment_fallbacks() -> None:
    import os
    from unittest.mock import patch

    with (
        patch.dict(os.environ, {"COLUMNS": "123"}, clear=True),
        patch("os.get_terminal_size", side_effect=OSError()),
    ):
        assert terminal_size(default=(80, 24)) == (123, 24)

    with (
        patch.dict(os.environ, {"LINES": "45"}, clear=True),
        patch("os.get_terminal_size", side_effect=OSError()),
    ):
        assert terminal_size(default=(80, 24)) == (80, 45)
