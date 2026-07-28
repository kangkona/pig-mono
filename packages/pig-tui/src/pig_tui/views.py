"""Application-facing view adapters built on pig-tui core abstractions."""

from __future__ import annotations

from .components import KeyValueList, SelectListView
from .core import PanelContent


def render_info_panel(title: str, rows: list[tuple[str, str]], width: int = 100) -> PanelContent:
    """Create panel-friendly content from framework-level key/value rows."""
    view = KeyValueList(rows)
    return PanelContent(title=title, content="\n".join(view.render_lines(width)))


def render_status_message(kind: str, message: str) -> str:
    """Create a small, prefix-based status line."""
    return f"[{kind}] {message}"


def render_select_panel(
    title: str,
    items: list[tuple[str, str | None]],
    *,
    footer_rows: list[tuple[str, str]] | None = None,
    note: str | None = None,
    width: int = 100,
) -> PanelContent:
    """Render a selector-style panel using framework-level list and kv views."""
    lines = SelectListView(items).render_lines(width)
    if footer_rows:
        lines.extend(["", *KeyValueList(footer_rows).render_lines(width)])
    if note:
        lines.extend(["", note])
    return PanelContent(title=title, content="\n".join(lines))


def render_bullet_panel(
    title: str,
    bullets: list[str],
    *,
    note: str | None = None,
) -> PanelContent:
    """Render a bullet-list panel."""
    lines = [f"• {bullet}" for bullet in bullets] if bullets else ["(empty)"]
    if note:
        lines.extend(["", note])
    return PanelContent(title=title, content="\n".join(lines))
