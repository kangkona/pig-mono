"""Safe terminal rendering helpers.

These helpers are intentionally small and dependency-light. They protect common
render paths from unbounded wrapping work, lossy markdown normalization, and
OSC-8 escape leakage on unsupported terminals.
"""

from __future__ import annotations

import os
import re
import subprocess
import unicodedata
from collections.abc import Callable, Mapping

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC_RE = re.compile(r"\x1b\][^\x1b\x07]*?(?:\x1b\\|\x07)")
THAI_LAO_AM_REGEX = re.compile(r"[\u0e33\u0eb3]")
THAI_LAO_AM_DECOMPOSED = {"\u0e4d\u0e32", "\u0ecd\u0eb2"}
OSC8_END_TOKENS = {"\x1b]8;;\x1b\\", "\x1b]8;;\x07"}
SGR_RESET_TOKENS = {"\x1b[0m", "\x1b[m"}


def strip_terminal_sequences(text: str) -> str:
    """Strip non-printing ANSI and OSC 8 hyperlink sequences."""
    return ANSI_RE.sub("", OSC_RE.sub("", text))


def normalize_terminal_output(text: str) -> str:
    """Normalize terminal-bound text for AM vowel renderer quirks."""
    if not THAI_LAO_AM_REGEX.search(text):
        return text
    return text.replace("\u0e33", "\u0e4d\u0e32").replace("\u0eb3", "\u0ecd\u0eb2")


def _display_width(text: str) -> int:
    """Estimate terminal cell width for plain Unicode text."""
    width = 0
    index = 0
    while index < len(text):
        if text[index : index + 2] in THAI_LAO_AM_DECOMPOSED:
            width += 1
            index += 2
            continue

        char = text[index]
        if unicodedata.combining(char):
            index += 1
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        index += 1
    return width


def _display_width_char(char: str) -> int:
    """Return terminal cell width for a single Unicode character."""
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def _tokenize_terminal_text(text: str) -> list[tuple[str, str]]:
    """Split text into ANSI/OSC control tokens and visible text tokens."""
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(text):
        ansi_match = ANSI_RE.match(text, i)
        if ansi_match:
            tokens.append(("control", ansi_match.group(0)))
            i = ansi_match.end()
            continue
        osc_match = OSC_RE.match(text, i)
        if osc_match:
            tokens.append(("control", osc_match.group(0)))
            i = osc_match.end()
            continue
        tokens.append(("text", text[i]))
        i += 1
    return tokens


def _update_control_state(
    token: str,
    active_sgr: list[str],
    active_hyperlink: str | None,
) -> tuple[list[str], str | None]:
    """Track ANSI and OSC8 controls so wrapped/truncated segments stay well-formed."""
    next_sgr = list(active_sgr)
    next_hyperlink = active_hyperlink

    if token in OSC8_END_TOKENS:
        next_hyperlink = None
        return next_sgr, next_hyperlink

    if token.startswith("\x1b]8;;"):
        next_hyperlink = token
        return next_sgr, next_hyperlink

    if token.endswith("m"):
        if token in SGR_RESET_TOKENS:
            next_sgr = []
        else:
            next_sgr.append(token)

    return next_sgr, next_hyperlink


def _preserve_control_token(token: str) -> bool:
    """Return True when a control token should survive wrapping/truncation."""
    if token in OSC8_END_TOKENS:
        return True
    if token.startswith("\x1b]8;;"):
        return True
    return bool(ANSI_RE.fullmatch(token))


def _active_control_prefixes(active_sgr: list[str], active_hyperlink: str | None) -> list[str]:
    prefixes: list[str] = []
    if active_hyperlink is not None:
        prefixes.append(active_hyperlink)
    prefixes.extend(active_sgr)
    return prefixes


def _active_control_closers(active_sgr: list[str], active_hyperlink: str | None) -> list[str]:
    closers: list[str] = []
    if active_sgr:
        closers.append("\x1b[0m")
    if active_hyperlink is not None:
        closers.append("\x1b]8;;\x1b\\")
    return closers


def terminal_size(default: tuple[int, int] = (80, 24)) -> tuple[int, int]:
    """Return terminal size with conservative environment fallback."""
    columns = os.environ.get("COLUMNS")
    lines = os.environ.get("LINES")
    fallback_columns = int(columns) if columns and columns.isdigit() else None
    fallback_lines = int(lines) if lines and lines.isdigit() else None

    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except OSError:
        return fallback_columns or default[0], fallback_lines or default[1]


def visible_length(text: str) -> int:
    """Return display length ignoring ANSI escape sequences."""
    return _display_width(strip_terminal_sequences(text))


def safe_wrap(text: str, width: int, *, max_lines: int | None = None) -> list[str]:
    """Wrap text iteratively without recursive formatting or spread operations."""
    if width <= 0:
        width = 1

    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        if visible_length(raw_line) <= width:
            lines.append(raw_line)
        else:
            wrapped: list[str] = []
            current: list[str] = []
            current_width = 0
            active_sgr: list[str] = []
            active_hyperlink: str | None = None
            for token_type, token_value in _tokenize_terminal_text(raw_line):
                if token_type == "control":
                    if _preserve_control_token(token_value):
                        current.append(token_value)
                        active_sgr, active_hyperlink = _update_control_state(
                            token_value, active_sgr, active_hyperlink
                        )
                    continue

                char_width = _display_width_char(token_value)
                if current and current_width + char_width > width:
                    wrapped.append(
                        "".join(current + _active_control_closers(active_sgr, active_hyperlink))
                    )
                    current = _active_control_prefixes(active_sgr, active_hyperlink)
                    current_width = 0
                current.append(token_value)
                current_width += char_width

            if current:
                wrapped.append("".join(current))
            lines.extend(wrapped or [""])

        if max_lines is not None and len(lines) >= max_lines:
            return lines[:max_lines]

    return lines


def truncate_visible(text: str, width: int, *, suffix: str = "…") -> str:
    """Truncate text by visible width while preserving active terminal controls."""
    if visible_length(text) <= width:
        return text
    suffix_width = _display_width(suffix)
    if width <= suffix_width:
        return suffix if width == suffix_width else ""

    budget = width - suffix_width
    out: list[str] = []
    used = 0
    active_sgr: list[str] = []
    active_hyperlink: str | None = None
    for token_type, token_value in _tokenize_terminal_text(text):
        if token_type == "control":
            if _preserve_control_token(token_value):
                out.append(token_value)
                active_sgr, active_hyperlink = _update_control_state(
                    token_value, active_sgr, active_hyperlink
                )
            continue

        char_width = _display_width_char(token_value)
        if used + char_width > budget:
            break
        out.append(token_value)
        used += char_width

    return "".join(out + _active_control_closers(active_sgr, active_hyperlink)) + suffix


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


def print_markdown_safely(
    markdown: str,
    *,
    renderer: Callable[[str], object],
    printer: Callable[[object], None],
) -> None:
    """Render markdown with a plain-text fallback for construction or print failures."""
    normalized = normalize_markdown_for_terminal(markdown)
    fallback_text = normalize_terminal_output(normalized)
    try:
        printer(renderer(normalized))
    except Exception:
        printer(fallback_text)


def _probe_tmux_client_termfeatures() -> str | None:
    """Return tmux client_termfeatures, or None when probing is unavailable."""
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{client_termfeatures}"],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.25,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None

    features = result.stdout.strip()
    return features or None


def supports_osc8_hyperlinks(
    env: Mapping[str, str] | None = None,
    *,
    tmux_feature_probe: Callable[[], str | None] | None = None,
) -> bool:
    """Detect whether OSC 8 hyperlinks are safe to emit."""
    resolved_env: Mapping[str, str] = env if env is not None else os.environ
    if resolved_env.get("NO_COLOR"):
        return False
    probe = tmux_feature_probe or _probe_tmux_client_termfeatures
    tmux_feature_value = resolved_env.get("TMUX_CLIENT_TERMFEATURES")
    if not tmux_feature_value and (
        resolved_env.get("TMUX") or resolved_env.get("TERM", "").startswith("tmux")
    ):
        tmux_feature_value = probe()
    tmux_features = {
        feature.strip().lower()
        for feature in (tmux_feature_value or "").split(",")
        if feature.strip()
    }
    if resolved_env.get("TMUX") or resolved_env.get("TERM", "").startswith("tmux"):
        return "hyperlinks" in tmux_features
    if resolved_env.get("STY") or resolved_env.get("TERM", "").startswith("screen"):
        return False
    term_program = resolved_env.get("TERM_PROGRAM", "").lower()
    if term_program in {"wezterm", "vscode", "iterm.app", "ghostty", "alacritty"}:
        return True
    if resolved_env.get("WT_SESSION"):
        return True
    return resolved_env.get("PIG_TUI_HYPERLINKS") == "1"


def hyperlink(
    text: str,
    url: str,
    *,
    env: Mapping[str, str] | None = None,
    tmux_feature_probe: Callable[[], str | None] | None = None,
) -> str:
    """Return an OSC 8 hyperlink when supported, otherwise visible text."""
    if not supports_osc8_hyperlinks(env, tmux_feature_probe=tmux_feature_probe):
        return text
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
