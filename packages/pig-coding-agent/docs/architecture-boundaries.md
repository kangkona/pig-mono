# pig-coding-agent / pig-tui architecture boundaries

## Goal

The goal of this refactor is not to mechanically clone `pi-tui`.
The goal is to build a better long-term Python terminal platform for
`pig-coding-agent`, while preserving the useful split that `pi-mono` has
between:

- application-layer orchestration
- UI/platform-layer rendering and interaction primitives

## Current boundary

`pig-coding-agent` owns:

- session/runtime orchestration
- tool/auth/model/resilience/cost orchestration
- command semantics such as `/tree`, `/fork`, `/resume`, `/compact`
- extension / skill / prompt lifecycle
- application-level decisions about which selector/editor flow a command should trigger
- application actions and state transitions through app-layer action objects

Inside `pig-coding-agent`, those concerns are now split more explicitly into:

- `CodingAgent`: top-level application assembly and orchestration
- `InteractionRuntime`: thin slash-command entry point and high-level runtime coordination
- `InteractionDispatcher`: slash-command matching and dispatch orchestration
- `InteractionRoutes`: declarative simple/prefix route construction for slash-command families
- `InteractionCommands`: imperative command handlers for model/auth/share/reload/prompt/skill actions
- `InteractionFlows`: selector/editor/session/tree/settings interactive flows
- `InteractionViews`: user-facing panels, status messages, and action-result reporting
- `InteractiveMode`: interactive shell loop, turn orchestration, file-reference
  expansion, queue steering/follow-up intake, and interactive telemetry/auto-compact
- `AppActions`: session/tree/settings/copy/export/compact application actions

The default terminal UI surface is now also owned by the interaction layer:

- `InteractionRuntime` owns the default `ChatUI` lifecycle and display fallback seam
- `CodingAgent` exposes `ui` as a compatibility property, but no longer directly
  constructs the terminal UI object itself

`pig-tui` now owns two layers:

1. Compatibility helpers:
   - `ChatUI`
   - `Prompt`
   - `InteractivePrompt`
   - `LiveInputListener`

2. Framework/platform abstractions:
   - `Component`
   - `Focusable`
   - `Container`
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
   - `TreeBrowserState`
   - `TreeOption`
   - `TreeBrowserContainer`
   - `TreeDetailView`
   - `TreeBrowserSession`
   - `OverlaySession`
   - `TerminalRuntime.begin_overlay_session()`
   - `TerminalRuntime.end_overlay_session()`
   - `TerminalRuntime.run_selection_session()`
   - `TerminalRuntime.run_editor_session()`
   - `TerminalRuntime.run_selection_editor_session()`
   - `TerminalRuntime.run_tree_browser_session()`
   - `TerminalRuntime.select()`
   - `TerminalRuntime.edit_text()`
   - `TerminalRuntime.choose_and_edit()`
   - `render_info_panel`
   - `render_select_panel`
   - `render_bullet_panel`
   - `render_status_message`

`pig-coding-agent` now routes some real interactive flows through the runtime,
not just static rendering. Today that includes:

- slash-command dispatch owned by `InteractionRuntime`
- session resume selection (`/resume` without an explicit target)
- session rename editing (`/name` without an explicit new name)
- session tree entry selection (`/tree` without an explicit target)
- session tree label editing (`/tree label` without explicit arguments)
- project-scoped auto-compaction settings selection/editing (`/settings`
  without explicit arguments)
- session/status/export/reload/model/auth/usage flows increasingly reported through runtime methods
- streaming turn orchestration
- runtime-owned shell-loop mechanics, with `InteractiveMode` delegating the
  common prompt/event-loop lifecycle into `TerminalRuntime.run_shell_loop()`
- `/tree` without explicit arguments is a prompt-based, two-stage entry/action
  browser instead of a one-shot selector
- `/tree` now rides on dedicated tree browser runtime primitives instead of
  generic selector/action plumbing alone
- `/tree` browser state is described through dedicated runtime
  contracts (`TreeBrowserState`, `TreeOption`, `TreeBrowserSession`) rather than
  scattered UI fields
- `/tree` browser detail presentation now rides on dedicated runtime components
  (`TreeDetailView`, `TreeBrowserContainer`) instead of inline string assembly
- command-line argument parsing for flows like `/tree label ...` and `/settings ...`
- an increasing share of shell/status/panel/error output routed through
  `InteractionRuntime` instead of direct `ChatUI` / `ChatPresenter` calls

The runtime now also owns an increasing share of **result reporting**:

- application-layer methods in `CodingAgent` increasingly return structured results
- `InteractionViews` turns those results into user-facing status and panel output
- this now covers session actions, settings updates, and tree branch/label actions
- `InteractionCommands` now owns imperative command-side effects that are not
  session/tree/settings app actions
- `InteractiveMode` owns the shell lifecycle around those command/reporting flows
- `InteractiveMode` increasingly owns only app-specific shell semantics, while
  common loop mechanics move down into `pig-tui`
- `InteractionFlows` owns selector/editor-driven command flows that sit between
  slash-command dispatch and app actions
- `InteractionRuntime` is now also the main app-layer seam for display output:
  panel, status, error, system, user, and assistant messages increasingly go
  through it rather than bypassing the runtime
- `/tree` is an operation-oriented prompt browser with dedicated tree state,
  layout, and detail presentation. Scope and label actions keep the browser
  open; switch, fork, and explicit close finish it. Full-screen key navigation
  remains outside the supported contract.

The application layer is also becoming more explicit internally:

- `AppActions` owns session/tree/settings-style actions
- `AppActions` actions now prefer explicit typed arguments rather than raw slash-command strings
- `AppActions` also owns compact/export/copy-style application actions that
  should not live in the runtime/controller layer
- `ResultFactory` and typed result objects provide a more stable contract
  between app actions and interactive reporting

## Design choice

We are intentionally not treating `pig-tui` as a bag of ad hoc helpers anymore.

Instead:

- `pig-coding-agent` should provide view-model data
- `pig-tui` should provide reusable presentation contracts and adapters
- `InteractionFlows` should consume structured runtime session contracts, not
  treat helper-style selector/editor calls as the primary seam

This lets us improve or even replace the underlying terminal runtime later
without forcing `pig-coding-agent` to keep assembling raw panel text itself.

## Alignment with pi-mono

Aligned with `pi-mono`:

- UI/platform concerns belong in the TUI package
- business semantics and orchestration belong in the coding-agent package
- selectors, panels, and renderable abstractions should be reusable
- focus / overlay / container lifecycle is increasingly runtime-owned instead of
  helper-owned
- structured selection/editor sessions now sit below the helper-style runtime
  methods, and `pig-coding-agent` flows increasingly target those structured
  contracts directly
- display output is increasingly runtime-owned as well: application modules no
  longer need to coordinate raw `ChatUI` calls and presenter calls separately
- interactive shell orchestration is no longer forced to live inside the main
  agent class
- slash-command routing is increasingly declarative rather than hard-coded into
  one controller class
- dispatch, route declaration, flows, views, and imperative command actions are
  now separated instead of living in one monolithic runtime/controller

Intentionally not aligned one-to-one:

- `pig-tui` does not attempt to reproduce every `pi-tui` abstraction today
- the Python stack may evolve toward a different runtime substrate if that
  yields better UX
- compatibility helpers remain available while the framework layer grows
- terminal prompt/input still rides on Python-native compatibility surfaces
  (`Prompt`, `InteractivePrompt`, `LiveInputListener`) while runtime ownership
  grows around them
- `CodingAgent` no longer needs to directly wire prompt/listener compatibility
  types just to assemble the interactive runtime

## Migration rule

When a new UI feature is added, ask:

1. Is this business semantics?
   - Keep it in `pig-coding-agent`
2. Is this reusable terminal presentation or interaction?
   - Put it in `pig-tui`

If a feature is reusable and currently implemented as string assembly in
`pig-coding-agent`, it is a migration candidate.
