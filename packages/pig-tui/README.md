# pig-tui

[![PyPI version](https://badge.fury.io/py/pig-tui.svg)](https://badge.fury.io/py/pig-tui)
[![Python](https://img.shields.io/pypi/pyversions/pig-tui.svg)](https://pypi.org/project/pig-tui/)

`pig-tui` is the terminal UI platform layer for `pig-coding-agent` and other
agent-style Python applications. It combines:

- high-level terminal affordances such as `ChatUI`, `Prompt`, and streaming helpers
- framework-level rendering abstractions such as `RenderableView`, `PanelContent`,
  `StatusMessage`, `ChatPresenter`, and reusable selector / key-value components

The package is intentionally moving away from a pure helper-library role toward
a clearer app/platform split:

- application packages should provide business semantics and view-model data
- `pig-tui` should provide reusable terminal-facing presentation and interaction
  primitives

## Current public layers

### High-level compatibility helpers

These keep the current coding-agent UX working while the package evolves:

- `ChatUI`
- `Prompt`
- `InteractivePrompt`
- `LiveInputListener`
- `Progress`
- `Spinner`

### Framework-level core

These are the new platform abstractions that higher-level apps should start
targeting:

- `Component` - minimal runtime-managed component contract
- `Focusable` - explicit focus contract for components that can receive runtime focus
- `RenderableView` - minimal render contract for reusable terminal views
- `PanelContent` - platform-neutral panel payload
- `ContainerContent` - runtime-managed container payload
- `StatusMessage` - platform-neutral status payload
- `SelectOption` - runtime-facing selector option contract
- `TextEditorState` - runtime-facing short-text editor state
- `ChatPresenter` - adapter that binds `PanelContent` / `StatusMessage` to a
  chat-like UI surface
- `TextBlock`
- `KeyValueList`
- `SelectListView`
- `TextEditorView`
- `FocusContainer`
- `ChoiceEditorContainer`
- `ConfirmView`
- `OverlaySession`
- `PromptStep`
- `SelectionSession`
- `EditorSession`
- `SelectionEditorSession`
- `SelectionActionSession`
- `SelectionActionResult`
- `TreeBrowserState`
- `TreePathState`
- `TreeSummaryState`
- `TreeDetailState`
- `TreeOption`
- `TreeBrowserContainer`
- `TreeDetailView`
- `TreeBrowserSession`
- `TreeBrowserResult`
- `ShellLoopSession`
- `ShellLoopResult`
- `TerminalRuntime.begin_overlay_session()`
- `TerminalRuntime.end_overlay_session()`
- `TerminalRuntime.run_prompt_step()`
- `TerminalRuntime.run_shell_loop()`
- `TerminalRuntime.run_tree_browser_session()`
- `TerminalRuntime.confirm()`
- `TerminalRuntime.open_container()`
- `TerminalRuntime.select_option()`
- `TerminalRuntime.select()`
- `TerminalRuntime.edit_text()`
- `TerminalRuntime.choose_and_edit()`
- `render_info_panel()`
- `render_select_panel()`
- `render_bullet_panel()`
- `render_status_message()`

## Installation

```bash
pip install pig-tui
```

## Quick examples

### Platform-level panel rendering

```python
from pig_tui import ChatPresenter, ChatUI, render_info_panel, StatusMessage

ui = ChatUI(title="Demo")
presenter = ChatPresenter(lambda: ui)

presenter.show_panel(
    render_info_panel(
        "Session",
        [
            ("ID", "abc123"),
            ("Entries", "4"),
        ],
    )
)

presenter.show_status(StatusMessage("ok", "Ready"))
```

### Reusable list views

```python
from pig_tui import SelectListView

view = SelectListView(
    [
        ("session-a", "recent"),
        ("session-b", "older"),
    ]
)
view.move(1)

for line in view.render_lines(80):
    print(line)
```

### Compatibility chat surface

```python
from pig_tui import ChatUI

chat = ChatUI(title="Assistant")
chat.user("Hello")
chat.assistant("Hi there!")
```

## Design direction

`pig-tui` is not trying to be a direct Python clone of `pi-tui`.
Instead, it is converging on the same boundary:

- terminal runtime and reusable UI primitives live here
- business semantics stay in application packages such as `pig-coding-agent`

That means new work should prefer platform-layer abstractions over ad hoc string
assembly in application code.

More specifically, `TerminalRuntime` is now the intended home for runtime-owned
interaction flows such as:

- prompt collection
- streaming turns
- component/focus contracts and focus transitions
- focus transitions
- focus-container ownership and traversal
- overlay lifecycle
- overlay session lifecycle
- prompt-step lifecycle inside runtime-owned overlay sessions
- confirmation lifecycle inside runtime-owned prompt/overlay flows
- structured selection-session lifecycle for confirm/select flows
- structured editor-session lifecycle for text editing and selection+editor flows
- structured option resolution inside runtime-owned selector flows
- structured selection+action flows for browser-style interaction surfaces such
  as tree/history browsers
- structured tree browser flows with tree-aware entries instead of plain flat
  selector options
- specialized tree browser container/layout for scope, anchor, and action
  presentation
- specialized tree browser detail panes backed by explicit detail-row contracts
- dedicated tree browser detail-state contracts with fixed fields plus optional
  extra rows
- dedicated tree browser path-state contracts for breadcrumbs, selected-entry,
  and anchor chrome
- dedicated tree browser summary-state contracts for visible/total/path/tip
  navigator stats
- dedicated tree browser state contracts that compose scope plus structured path
  and summary chrome
- dedicated tree browser runtime entry points instead of reusing generic
  selection-action sessions for every tree/history workflow
- interactive shell-loop mechanics with one runtime-owned event loop and
  prompt/input lifecycle
- selector flows
- short-form editor flows
- container-driven multi-step flows such as selector-plus-editor interactions

The older helper-style APIs remain available, but they should now be understood
as convenience wrappers over the structured runtime session primitives
(`SelectionSession`, `EditorSession`, and `SelectionEditorSession`) rather than
as the primary architecture target for higher-level apps.

## License

MIT
