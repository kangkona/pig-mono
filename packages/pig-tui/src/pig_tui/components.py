"""Reusable framework-level terminal components for pig-tui."""

from __future__ import annotations

from dataclasses import dataclass, field

from .core import (
    Component,
    Container,
    Focusable,
    RenderableView,
    SelectOption,
    TextEditorState,
    TreeBrowserState,
    TreeDetailState,
    TreeOption,
    is_focusable,
)
from .rendering import truncate_visible


@dataclass
class TextBlock(RenderableView, Component):
    """Simple multi-line text block."""

    text: str

    def render_lines(self, width: int) -> list[str]:
        del width  # reserved for future wrapping logic
        return self.text.splitlines() or [""]

    def render(self, width: int) -> list[str]:
        return self.render_lines(width)

    def invalidate(self) -> None:
        return None


@dataclass
class KeyValueList(RenderableView, Component):
    """Render a compact key/value listing."""

    items: list[tuple[str, str]]
    key_width: int = 12

    def render_lines(self, width: int) -> list[str]:
        key_width = max(self.key_width, max((len(key) for key, _ in self.items), default=0))
        max_value_width = max(1, width - key_width - 3)
        return [
            f"{key:<{key_width}} : {truncate_visible(value, max_value_width)}"
            for key, value in self.items
        ]

    def render(self, width: int) -> list[str]:
        return self.render_lines(width)

    def invalidate(self) -> None:
        return None


@dataclass
class SelectListView(RenderableView, Component, Focusable):
    """Minimal selectable list view for higher-level application selectors."""

    items: list[tuple[str, str | None]]
    selected_index: int = 0
    focused: bool = False
    invalidated: bool = field(default=False, init=False)

    def move(self, delta: int) -> None:
        if not self.items:
            self.selected_index = 0
            return
        self.selected_index = max(0, min(self.selected_index + delta, len(self.items) - 1))

    def selected_value(self) -> str | None:
        if not self.items:
            return None
        return self.items[self.selected_index][0]

    def render_lines(self, width: int) -> list[str]:
        if not self.items:
            return ["  (empty)"]
        lines: list[str] = []
        for index, (label, description) in enumerate(self.items):
            if self.focused and index == self.selected_index:
                prefix = "=> "
            elif index == self.selected_index:
                prefix = "-> "
            else:
                prefix = "  "
            body = truncate_visible(label, max(1, width - len(prefix)))
            line = f"{prefix}{body}"
            if description:
                desc_width = max(1, width - len(prefix) - len(body) - 3)
                line += f" - {truncate_visible(description, desc_width)}"
            lines.append(line)
        return lines

    def render(self, width: int) -> list[str]:
        self.invalidated = False
        return self.render_lines(width)

    def invalidate(self) -> None:
        self.invalidated = True


@dataclass(init=False)
class TreeListView(RenderableView, Component, Focusable):
    """Tree-aware selectable list view for history/browser interactions."""

    items: list[TreeOption]
    focused: bool = False
    invalidated: bool = field(default=False, init=False)
    _selected_index: int = field(default=0, init=False, repr=False)

    def __init__(
        self,
        items: list[TreeOption],
        selected_index: int = 0,
        focused: bool = False,
    ) -> None:
        self.items = items
        self.focused = focused
        self.invalidated = False
        self._selected_index = 0
        self.select_index(selected_index)

    @property
    def selected_index(self) -> int:
        return self._selected_index

    def move(self, delta: int) -> None:
        self.select_index(self.selected_index + delta)

    def select_index(self, index: int) -> TreeOption | None:
        if not self.items:
            self._selected_index = 0
            return None
        self._selected_index = max(0, min(index, len(self.items) - 1))
        return self.selected_item()

    def selected_item(self) -> TreeOption | None:
        if not self.items:
            return None
        return self.items[self.selected_index]

    def selected_value(self) -> str | None:
        selected_item = self.selected_item()
        return selected_item.value if selected_item is not None else None

    def render_lines(self, width: int) -> list[str]:
        if not self.items:
            return ["  (empty)"]
        lines: list[str] = []
        for index, item in enumerate(self.items):
            if self.focused and index == self.selected_index:
                prefix = "=> "
            elif index == self.selected_index:
                prefix = "-> "
            else:
                prefix = "  "
            indent = "  " * min(item.depth, 5)
            suffixes: list[str] = []
            if item.is_current:
                suffixes.append("current")
            if item.is_anchor:
                suffixes.append("anchor")
            if item.is_branch_point:
                suffixes.append("branch")
            suffix = f" [{' '.join(suffixes)}]" if suffixes else ""
            body = truncate_visible(f"{indent}{item.label}{suffix}", max(1, width - len(prefix)))
            line = f"{prefix}{body}"
            if item.description:
                desc_width = max(1, width - len(prefix) - len(body) - 3)
                line += f" - {truncate_visible(item.description, desc_width)}"
            lines.append(line)
        return lines

    def render(self, width: int) -> list[str]:
        self.invalidated = False
        return self.render_lines(width)

    def invalidate(self) -> None:
        self.invalidated = True


@dataclass
class TreeDetailView(RenderableView, Component):
    """Detail pane for the currently selected tree browser entry."""

    state: TreeDetailState | None = None

    def render_lines(self, width: int) -> list[str]:
        if self.state is None:
            return ["  (empty)"]
        return [
            f"{key}: {truncate_visible(value, max(1, width - len(key) - 2))}"
            for key, value in self.state.rows
        ]

    def render(self, width: int) -> list[str]:
        return self.render_lines(width)

    def invalidate(self) -> None:
        return None


@dataclass
class TreeChromeView(RenderableView, Component):
    """Structured chrome/header view for tree browser navigators."""

    state: TreeBrowserState
    title: str = "Tree"
    active: bool = False

    def render_lines(self, width: int) -> list[str]:
        header = f"{self.title} [{self.state.scope}]"
        if self.active:
            header += " [active]"
        lines = [header]
        for key, value in self.state.chrome_rows:
            lines.append(f"{key}: {truncate_visible(value, max(1, width - len(key) - 2))}")
        return lines

    def render(self, width: int) -> list[str]:
        return self.render_lines(width)

    def invalidate(self) -> None:
        return None


@dataclass
class TextEditorView(RenderableView, Component, Focusable):
    """Minimal runtime-owned editor view for short text input flows."""

    state: TextEditorState
    focused: bool = False
    invalidated: bool = field(default=False, init=False)

    def render_lines(self, width: int) -> list[str]:
        prefix = "=> " if self.focused else "   "
        body = truncate_visible(self.state.value or "(empty)", max(1, width - len(prefix)))
        lines = [f"{prefix}{body}"]
        if self.state.note:
            lines.extend(["", truncate_visible(self.state.note, max(1, width))])
        return lines

    def render(self, width: int) -> list[str]:
        self.invalidated = False
        return self.render_lines(width)

    def invalidate(self) -> None:
        self.invalidated = True


@dataclass
class ConfirmView(RenderableView, Component):
    """Minimal runtime-owned confirmation view."""

    question: str
    default: bool = False
    invalidated: bool = field(default=False, init=False)

    def render_lines(self, width: int) -> list[str]:
        prefix = "   "
        suffix = "[Y/n]" if self.default else "[y/N]"
        return [truncate_visible(f"{prefix}{self.question} {suffix}", max(1, width))]

    def render(self, width: int) -> list[str]:
        self.invalidated = False
        return self.render_lines(width)

    def invalidate(self) -> None:
        self.invalidated = True


@dataclass
class ChoiceEditorContainer(Container):
    """Container combining a selector and editor into one runtime-owned flow."""

    selector: SelectListView
    editor: TextEditorView
    selected_index: int = 0

    def __post_init__(self) -> None:
        self.selector.focused = True
        self.editor.focused = False

    def current(self) -> Component | None:
        return self.selector if self.selected_index == 0 else self.editor

    def sync_editor_initial_value(
        self,
        option: SelectOption | None,
        *,
        use_selected_description_as_initial: bool,
    ) -> None:
        if option is None:
            self.editor.state.value = ""
            return
        if use_selected_description_as_initial:
            self.editor.state.value = option.initial_value or option.description or ""
        else:
            self.editor.state.value = option.initial_value or ""

    def render_sections(self, width: int) -> list[str]:
        selector_header = "Selection [active]" if self.selected_index == 0 else "Selection"
        editor_header = (
            f"{self.editor.state.title} [active]"
            if self.selected_index == 1
            else self.editor.state.title
        )
        return [
            selector_header + "\n" + "\n".join(self.selector.render(width)),
            editor_header + "\n" + "\n".join(self.editor.render(width)),
        ]

    def render(self, width: int) -> list[str]:
        return ["\n\n".join(self.render_sections(width))]

    def invalidate(self) -> None:
        self.selector.invalidate()
        self.editor.invalidate()

    def focus_next(self) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = (self.selected_index + 1) % 2
        nxt = self.current()
        if is_focusable(nxt):
            nxt.focused = True
        return nxt

    def focus_previous(self) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = (self.selected_index - 1) % 2
        prev = self.current()
        if is_focusable(prev):
            prev.focused = True
        return prev

    def focus_index(self, index: int) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = 0 if index <= 0 else 1
        component = self.current()
        if is_focusable(component):
            component.focused = True
        return component


@dataclass
class SelectionActionContainer(Container):
    """Container combining a selector and action list into one browser-style flow."""

    selector: SelectListView
    actions: SelectListView
    action_title: str = "Actions"
    selected_index: int = 0

    def __post_init__(self) -> None:
        self.selector.focused = True
        self.actions.focused = False

    def current(self) -> Component | None:
        return self.selector if self.selected_index == 0 else self.actions

    def render_sections(self, width: int) -> list[str]:
        selector_header = "Selection [active]" if self.selected_index == 0 else "Selection"
        action_header = (
            f"{self.action_title} [active]" if self.selected_index == 1 else self.action_title
        )
        return [
            selector_header + "\n" + "\n".join(self.selector.render(width)),
            action_header + "\n" + "\n".join(self.actions.render(width)),
        ]

    def render(self, width: int) -> list[str]:
        return ["\n\n".join(self.render_sections(width))]

    def invalidate(self) -> None:
        self.selector.invalidate()
        self.actions.invalidate()

    def focus_next(self) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = (self.selected_index + 1) % 2
        nxt = self.current()
        if is_focusable(nxt):
            nxt.focused = True
        return nxt

    def focus_previous(self) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = (self.selected_index - 1) % 2
        prev = self.current()
        if is_focusable(prev):
            prev.focused = True
        return prev

    def focus_index(self, index: int) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = 0 if index <= 0 else 1
        component = self.current()
        if is_focusable(component):
            component.focused = True
        return component


@dataclass
class TreeBrowserContainer(SelectionActionContainer):
    """Container specialized for tree/history browser interactions."""

    selector: TreeListView
    actions: SelectListView
    detail: TreeDetailView = field(default_factory=TreeDetailView)
    action_title: str = "Actions"
    detail_title: str = "Details"
    state: TreeBrowserState = field(default_factory=TreeBrowserState)
    selected_index: int = 0

    def __post_init__(self) -> None:
        self.selector.focused = True
        self.actions.focused = False
        self._sync_detail()

    def _sync_detail(self) -> None:
        current_item = self.selector.selected_item()
        self.detail.state = current_item.detail_state if current_item is not None else None

    def selected_entry(self) -> TreeOption | None:
        return self.selector.selected_item()

    def current_browser_state(self) -> TreeBrowserState:
        return self.state.with_selected_entry(self.selected_entry())

    def select_index(self, index: int) -> TreeOption | None:
        selected_entry = self.selector.select_index(index)
        self._sync_detail()
        return selected_entry

    def render_sections(self, width: int) -> list[str]:
        self._sync_detail()
        chrome_view = TreeChromeView(
            state=self.current_browser_state(),
            title="Tree",
            active=self.selected_index == 0,
        )
        action_header = (
            f"{self.action_title} [active]" if self.selected_index == 1 else self.action_title
        )
        detail_header = (
            f"{self.detail_title} [active]" if self.selected_index == 2 else self.detail_title
        )
        return [
            "\n".join(chrome_view.render(width) + self.selector.render(width)),
            action_header + "\n" + "\n".join(self.actions.render(width)),
            detail_header + "\n" + "\n".join(self.detail.render(width)),
        ]

    def render(self, width: int) -> list[str]:
        return ["\n\n".join(self.render_sections(width))]

    def invalidate(self) -> None:
        self.selector.invalidate()
        self.actions.invalidate()
        self.detail.invalidate()

    def current(self) -> Component | None:
        if self.selected_index == 0:
            return self.selector
        if self.selected_index == 1:
            return self.actions
        return self.detail

    def focus_next(self) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = (self.selected_index + 1) % 3
        nxt = self.current()
        if is_focusable(nxt):
            nxt.focused = True
        return nxt

    def focus_previous(self) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = (self.selected_index - 1) % 3
        prev = self.current()
        if is_focusable(prev):
            prev.focused = True
        return prev

    def focus_index(self, index: int) -> Component | None:
        current = self.current()
        if is_focusable(current):
            current.focused = False
        self.selected_index = 0 if index <= 0 else 1 if index == 1 else 2
        self._sync_detail()
        component = self.current()
        if is_focusable(component):
            component.focused = True
        return component
