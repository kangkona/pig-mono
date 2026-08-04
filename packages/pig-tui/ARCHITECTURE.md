# pig-tui architecture

## Positioning

`pig-tui` is the terminal UI platform layer for agent-style Python
applications.

It is intentionally evolving away from a bag of helper utilities toward a more
explicit two-layer model:

1. Compatibility helpers for existing applications
2. Framework-level rendering and presentation abstractions for future work

## Layer 1: compatibility helpers

These keep current applications working while migration continues:

- `ChatUI`
- `Prompt`
- `InteractivePrompt`
- `LiveInputListener`
- `Progress`
- `Spinner`

They are still valid public API, but they are no longer the only intended way
to build on top of `pig-tui`.

## Layer 2: framework/platform abstractions

These are the forward-looking interfaces:

- `Component`
- `Focusable`
- `is_focusable()`
- `RenderableView`
- `PanelContent`
- `ContainerContent`
- `StatusMessage`
- `SelectOption`
- `TextEditorState`
- `ChatPresenter`
- `FocusContainer`
- `TextBlock`
- `KeyValueList`
- `SelectListView`
- `TextEditorView`
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
- `TerminalRuntime.open_container()`
- `TerminalRuntime.begin_overlay_session()`
- `TerminalRuntime.end_overlay_session()`
- `TerminalRuntime.run_prompt_step()`
- `TerminalRuntime.run_shell_loop()`
- `TerminalRuntime.run_tree_browser_session()`
- `TerminalRuntime.confirm()`
- `TerminalRuntime.select_option()`
- `TerminalRuntime.select()`
- `TerminalRuntime.edit_text()`
- `TerminalRuntime.choose_and_edit()`
- `TerminalRuntime.show_panel()`
- `TerminalRuntime.show_status()`
- `TerminalRuntime.show_error()`
- `TerminalRuntime.show_system()`
- `TerminalRuntime.show_user()`
- `TerminalRuntime.show_assistant()`
- `render_info_panel`
- `render_select_panel`
- `render_bullet_panel`
- `render_status_message`

The intent is:

- application packages define semantics and view-model data
- `pig-tui` turns that data into terminal-facing UI structures
- component focusability is now an explicit runtime-owned contract instead of an
  informal convention
- small focusable component groups can now be owned by runtime-managed containers
- container payloads can now be rendered through a runtime-managed open-container flow
- overlay/container lifecycle can now be entered through one runtime-owned overlay session path
- prompt collection inside overlay-driven flows can now be routed through one
  runtime-owned prompt-step entry point
- confirmation can now be routed through one runtime-owned confirmation entry point
- confirm/select flows can now share one runtime-owned selection-session primitive
- edit/select+edit flows can now share dedicated runtime-owned editor-session primitives
- select+action flows can now share a runtime-owned browser-style container
  primitive instead of being rebuilt ad hoc in each app
- tree/history browser flows can now carry tree-aware entry state instead of
  flattening everything to generic selector rows
- tree/history browser layout can now be specialized instead of always
  borrowing the generic selection-action container
- tree/history browser detail presentation can now be specialized instead of
  being inlined as ad hoc strings inside the container
- tree/history browser detail state can now be described through a dedicated
  contract with fixed rows plus optional extra rows
- tree/history browser path chrome can now be described through a dedicated
  `TreePathState` contract instead of relying on one preformatted breadcrumb string
- tree/history browser summary chrome can now be described through a dedicated
  `TreeSummaryState` contract instead of relying on one preformatted summary string
- tree/history browser chrome can now be driven by a dedicated composed state
  contract (`TreeBrowserState`) instead of passing separate scope/anchor/summary strings
- tree/history browser chrome can now follow the currently selected entry path
  and detail state instead of only mirroring the initial browser anchor
- tree/history browser execution now has a dedicated runtime session entry point
  instead of always reusing the generic selection-action runtime path
- selector choice parsing can now be routed through one runtime-owned structured
  option-selection entry point
- shell-loop mechanics can now be runtime-owned instead of being rebuilt inside
  each application
- panel/status/error/system/user/assistant output can now be routed through one
  runtime-owned display surface instead of forcing app packages to juggle
  `ChatPresenter` and raw `ChatUI` calls separately
- `TerminalRuntime.open_container()` now prefers container-owned rendered sections over ad hoc fallback content
- `TerminalRuntime.choose_and_edit()` is now a concrete multi-component container-driven interaction flow
- `SelectOption.initial_value` and `SelectionEditResult` now make selector/editor value flow more explicit than overloading description text
- helper-style calls like `select_option()`, `edit_text()`, and
  `choose_and_edit()` now sit on top of the structured session contracts instead
  of being the architectural center of the interaction model

## Relationship to pig-coding-agent

`pig-coding-agent` should own:

- command semantics
- session/runtime orchestration
- tool/auth/model/resilience/cost orchestration
- extension / skill / prompt lifecycle

`pig-tui` should own:

- reusable presentation contracts
- reusable selector/list/panel rendering
- runtime-owned focus / overlay discipline
- runtime-owned selector and editor flows
- prompt and streaming-turn orchestration entry points
- adapters from view data to terminal UI surfaces

This boundary is inspired by the application/platform split in `pi-mono`, but
it is not a requirement to reproduce `pi-tui` exactly. The priority is a strong
Python-native terminal platform with clean boundaries and good UX.
