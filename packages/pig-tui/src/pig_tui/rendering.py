"""Safe terminal rendering helpers.

These helpers are intentionally small and dependency-light. They protect common
render paths from unbounded wrapping work, lossy markdown normalization, and
OSC-8 escape leakage on unsupported terminals.
"""

from __future__ import annotations

import os
import re
import textwrap

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def terminal_size(default: tuple[int, int] = (80, 24)) -> tuple[int, int]:
    """Return terminal size with conservative environment fallback."""
    columns = os.environ.get("COLUMNS")
    lines = os.environ.get("LINES")
    if columns and lines and columns.isdigit() and lines.isdigit():
        return int(columns), int(lines)

    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except OSError:
        return default


def visible_length(text: str) -> int:
    """Return display length ignoring ANSI escape sequences."""
    return len(ANSI_RE.sub("", text))


def safe_wrap(text: str, width: int, *, max_lines: int | None = None) -> list[str]:
    """Wrap text iteratively without recursive formatting or spread operations."""
    if width <= 0:
        width = 1

    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        if visible_length(raw_line) <= width:
            lines.append(raw_line)
        else:
            wrapped = textwrap.wrap(
                raw_line,
                width=width,
                replace_whitespace=False,
                drop_whitespace=False,
                break_long_words=True,
                break_on_hyphens=False,
            )
            lines.extend(wrapped or [""])

        if max_lines is not None and len(lines) >= max_lines:
            return lines[:max_lines]

    return lines


def truncate_visible(text: str, width: int, *, suffix: str = "…") -> str:
    """Truncate plain text by visible width."""
    if visible_length(text) <= width:
        return text
    if width <= len(suffix):
        return suffix[:width]
    return ANSI_RE.sub("", text)[: width - len(suffix)] + suffix


def normalize_markdown_for_terminal(markdown: str) -> str:
    """Preserve ordered-list markers and task checkboxes before Rich rendering."""
    lines = []
    ordered_item = re.compile(r"^(\s*)(\d+)([.)])\s+")
    task_item = re.compile(r"^(\s*)[-*]\s+\[([ xX])\]\s+")

    for line in markdown.splitlines():
        if ordered_item.match(line):
            lines.append(line)
            continue
        task_match = task_item.match(line)
        if task_match:
            checked = task_match.group(2).lower() == "x"
            marker = "[x]" if checked else "[ ]"
            lines.append(task_item.sub(rf"\1- {marker} ", line, count=1))
            continue
        lines.append(line)

    return "\n".join(lines)


def supports_osc8_hyperlinks(env: dict[str, str] | None = None) -> bool:
    """Detect whether OSC 8 hyperlinks are safe to emit."""
    env = env or os.environ
    if env.get("NO_COLOR"):
        return False
    term_program = env.get("TERM_PROGRAM", "").lower()
    if term_program in {"wezterm", "vscode", "iterm.app", "ghostty"}:
        return True
    if env.get("WT_SESSION"):
        return True
    return env.get("PIG_TUI_HYPERLINKS") == "1"


def hyperlink(text: str, url: str, *, env: dict[str, str] | None = None) -> str:
    """Return an OSC 8 hyperlink when supported, otherwise visible text."""
    if not supports_osc8_hyperlinks(env):
        return text
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
