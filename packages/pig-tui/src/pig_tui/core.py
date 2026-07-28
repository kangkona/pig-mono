"""Framework-level rendering abstractions for pig-tui."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable


@runtime_checkable
class RenderableView(Protocol):
    """Minimal reusable view contract for terminal-facing components."""

    def render_lines(self, width: int) -> list[str]:
        """Render the view to terminal-width-aware text lines."""


@runtime_checkable
class Component(Protocol):
    """Minimal runtime-managed TUI component contract."""

    def render(self, width: int) -> list[str]:
        """Render component lines for the given width."""

    def invalidate(self) -> None:
        """Clear any cached render state."""


@runtime_checkable
class Container(Protocol):
    """Protocol for runtime-owned component containers with focus traversal."""

    def render_sections(self, width: int) -> list[str]:
        """Render each child component as a separate container section."""

    def current(self) -> Component | None:
        """Return the currently focused component, if any."""

    def focus_next(self) -> Component | None:
        """Move focus to the next component and return it."""

    def focus_previous(self) -> Component | None:
        """Move focus to the previous component and return it."""

    def focus_index(self, index: int) -> Component | None:
        """Move focus to a specific child component and return it."""


@runtime_checkable
class Focusable(Protocol):
    """Protocol for components that can receive focus from the runtime."""

    focused: bool


def is_focusable(component: Component | None) -> bool:
    return component is not None and isinstance(component, Focusable)


@dataclass(frozen=True)
class PanelContent:
    """Plain data contract for panel-like UI blocks."""

    title: str
    content: str


@dataclass(frozen=True)
class ContainerContent:
    """Panel-like payload representing a runtime-managed component container."""

    title: str
    sections: list[str]


@dataclass(frozen=True)
class StatusMessage:
    """Platform-layer status message contract."""

    kind: str
    message: str


@dataclass(frozen=True)
class SelectOption:
    """A runtime-level selector option."""

    value: str
    label: str
    description: str | None = None
    initial_value: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class TreeOption:
    """A runtime-level tree browser entry."""

    value: str
    label: str
    description: str | None = None
    depth: int = 0
    is_current: bool = False
    is_branch_point: bool = False
    is_anchor: bool = False
    detail_state: TreeDetailState | None = None
    aliases: tuple[str, ...] = ()

    @property
    def detail_rows(self) -> tuple[tuple[str, str], ...]:
        if self.detail_state is None:
            return ()
        return self.detail_state.rows


@dataclass(frozen=True)
class TreeDetailState:
    """Runtime-level detail contract for one tree browser entry."""

    role: str
    short_id: str
    depth: int
    children_count: int
    label: str | None
    preview: str
    path_length: int
    path_labels: tuple[str, ...] = ()
    extra_rows: tuple[tuple[str, str], ...] = ()

    @property
    def rows(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Role", self.role),
            ("ID", self.short_id),
            ("Depth", str(self.depth)),
            ("Children", str(self.children_count)),
            ("Label", self.label or "-"),
            ("Preview", self.preview),
            ("Path", str(self.path_length)),
        ) + self.extra_rows


@dataclass(frozen=True)
class TreePathState:
    """Structured path chrome for a tree browser navigator."""

    parts: tuple[str, ...] = ()
    selected_label: str | None = None
    anchor_label: str | None = None
    extra_rows: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "parts", tuple(part for part in self.parts if part))

    @property
    def breadcrumb_text(self) -> str | None:
        if not self.parts:
            return None
        return " > ".join(self.parts)

    @property
    def rows(self) -> tuple[tuple[str, str], ...]:
        rows: list[tuple[str, str]] = []
        if self.breadcrumb_text:
            rows.append(("Path", self.breadcrumb_text))
        if self.selected_label:
            rows.append(("Selected", self.selected_label))
        if self.anchor_label:
            rows.append(("Anchor", self.anchor_label))
        rows.extend(self.extra_rows)
        return tuple(rows)


@dataclass(frozen=True)
class TreeSummaryState:
    """Structured summary chrome for a tree browser navigator."""

    visible_count: int
    total_count: int | None = None
    branch_count: int | None = None
    current_path_length: int | None = None
    current_entry_short_id: str | None = None
    extra_rows: tuple[tuple[str, str], ...] = ()

    @property
    def rows(self) -> tuple[tuple[str, str], ...]:
        rows: list[tuple[str, str]] = [("Visible", str(self.visible_count))]
        if self.total_count is not None:
            rows.append(("Total", str(self.total_count)))
        if self.branch_count is not None:
            rows.append(("Branches", str(self.branch_count)))
        if self.current_path_length is not None:
            rows.append(("Current path", str(self.current_path_length)))
        if self.current_entry_short_id is not None:
            rows.append(("Current tip", self.current_entry_short_id))
        rows.extend(self.extra_rows)
        return tuple(rows)

    @property
    def summary_text(self) -> str:
        parts = [f"{self.visible_count} entries visible"]
        if self.total_count is not None:
            parts.append(f"total: {self.total_count}")
        if self.current_entry_short_id is not None:
            parts.append(f"current tip: {self.current_entry_short_id}")
        return " | ".join(parts)


@dataclass(frozen=True)
class SelectionEditResult:
    """Result of a combined selector/editor container flow."""

    option: SelectOption | None
    edited_value: str | None


@dataclass(frozen=True)
class SelectionActionResult:
    """Result of a combined selector/action container flow."""

    option: SelectOption | None
    action: SelectOption | None


@dataclass(frozen=True)
class TreeBrowserResult:
    """Result of a combined tree browser and action flow."""

    entry: TreeOption | None
    action: SelectOption | None


@dataclass(frozen=True)
class TreeBrowserState:
    """Runtime-level state contract for tree/history browser chrome."""

    scope: str = "all"
    current_entry_id: str | None = None
    selected_entry_id: str | None = None
    anchor_entry_id: str | None = None
    breadcrumbs: Sequence[str] | str | None = None
    anchor_label: str | None = None
    summary: str | None = None
    path_state: TreePathState | None = None
    summary_state: TreeSummaryState | None = None

    def __post_init__(self) -> None:
        if self.scope not in {"all", "children", "siblings"}:
            raise ValueError("TreeBrowserState.scope must be one of: all, children, siblings")
        if self.selected_entry_id is None and self.current_entry_id is not None:
            object.__setattr__(self, "selected_entry_id", self.current_entry_id)
        if (
            self.scope != "all"
            and self.anchor_entry_id is None
            and self.selected_entry_id is not None
        ):
            object.__setattr__(self, "anchor_entry_id", self.selected_entry_id)
        if (
            self.scope != "all"
            and self.selected_entry_id is None
            and self.anchor_entry_id is not None
        ):
            object.__setattr__(self, "selected_entry_id", self.anchor_entry_id)
        if self.scope != "all" and self.anchor_entry_id is None:
            raise ValueError("TreeBrowserState.anchor_entry_id is required when scope != 'all'")
        if self.path_state is not None and self.breadcrumbs is None:
            object.__setattr__(self, "breadcrumbs", self.path_state.parts)
        object.__setattr__(self, "breadcrumbs", self._normalize_breadcrumbs(self.breadcrumbs))
        if self.path_state is not None and self.anchor_label is None:
            object.__setattr__(self, "anchor_label", self.path_state.anchor_label)
        if self.summary_state is not None and self.summary is None:
            object.__setattr__(self, "summary", self.summary_state.summary_text)

    @staticmethod
    def _normalize_breadcrumbs(value: Sequence[str] | str | None) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(">") if part.strip())
        return tuple(part.strip() for part in value if part.strip())

    @property
    def chrome_rows(self) -> tuple[tuple[str, str], ...]:
        rows: list[tuple[str, str]] = []
        if self.path_state is not None:
            rows.extend(self.path_state.rows)
        else:
            if self.breadcrumbs:
                rows.append(("Path", " > ".join(self.breadcrumbs)))
            if self.anchor_label:
                rows.append(("Anchor", self.anchor_label))
        if self.summary_state is not None:
            rows.extend(self.summary_state.rows)
        elif self.summary:
            rows.append(("Summary", self.summary))
        return tuple(rows)

    def with_selected_entry(self, entry: TreeOption | None) -> TreeBrowserState:
        if entry is None:
            return self

        detail_state = entry.detail_state
        parts = (
            detail_state.path_labels
            if detail_state is not None and detail_state.path_labels
            else self.path_state.parts
            if self.path_state is not None
            else self.breadcrumbs
        )
        selected_label = (
            detail_state.path_labels[-1]
            if detail_state is not None and detail_state.path_labels
            else entry.label
        )
        next_path_state = TreePathState(
            parts=tuple(parts),
            selected_label=selected_label,
            anchor_label=(
                self.path_state.anchor_label if self.path_state is not None else self.anchor_label
            ),
            extra_rows=self.path_state.extra_rows if self.path_state is not None else (),
        )
        return replace(
            self,
            selected_entry_id=entry.value,
            breadcrumbs=next_path_state.parts,
            path_state=next_path_state,
        )


@dataclass
class TextEditorState:
    """A small runtime-managed editable text state."""

    title: str
    value: str
    note: str | None = None
