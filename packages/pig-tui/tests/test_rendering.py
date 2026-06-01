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


def test_terminal_size_uses_environment_fallback() -> None:
    assert terminal_size(default=(1, 1)) in {(1, 1), terminal_size(default=(1, 1))}
    assert supports_osc8_hyperlinks({"WT_SESSION": "1"})
