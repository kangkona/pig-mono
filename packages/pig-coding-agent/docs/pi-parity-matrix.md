# pig-coding-agent parity matrix

This document tracks feature parity goals against the product shape of pig-coding-agent.
It is self-contained and does not require a local pi-mono checkout.

The goal is not byte-for-byte equivalence. The goal is to keep a clear map of:

- what `pig-coding-agent` already supports
- what is intentionally different
- what still needs work before we can claim parity on a user-facing capability

## Capability matrix

| Capability | Current status | Notes |
| --- | --- | --- |
| CLI modes | Partial | `interactive`, `json`, and `rpc` are implemented. `print` mode is not a separate surface today. |
| Tool permissions | Supported | Interactive `write_file`, extension-provided `edit_file`, and `run_command` routes require confirmation. JSON/RPC, non-TTY or piped stdin, `pig gen`, `pig analyze`, and the default SDK runtime fail closed with the stable `tool_permission_denied` code/message and do not perform the requested side effect. JSON events, RPC results, and SDK `prompt_result()` preserve the full machine-readable denial; plain CLI routes emit stable text and exit 2. SDK hosts may opt into an explicit confirm or allow policy. `edit_file` is reserved for extension safety but is not a built-in tool. |
| Project trust | Supported | Project settings, instructions, prompts, skills, package roots, and extensions are discovered without reading their contents, then loaded only after an allow decision for the canonical workspace. Interactive decisions can be persisted; JSON/RPC, piped stdin, and SDK hosts fail closed by default. `--approve`/`--no-approve` override a run. Global resources remain available independently. |
| Session tree | Supported | Sessions are tree-backed. `/tree <entry-id>` switches the active branch; interactive `/tree` provides a persistent prompt-based entry/action browser with scope navigation, path/summary chrome, synced details, label/fork/switch actions, and an explicit close action. Switch/fork finish the browser; scope and label actions continue it. Non-terminal surfaces intentionally render a read-only tree summary. Full-screen key navigation is not part of this contract. |
| Settings | Supported | `/settings` shows project/global config locations and exposes the two project-scoped settings the running agent actually consumes: `auto_compact` and `auto_compact_threshold`. Interactive terminals provide a selector/editor; `/settings <key> <value>` validates, persists, and applies both immediately. In an untrusted workspace it may create a new project config from the explicit edit, but it refuses to parse or merge an existing project config. Other config-model fields remain read-only here until startup/runtime consumption exists. |
| Extensions | Partial | Python extensions can register tools, commands, and event handlers. UI/widget parity is not present. |
| Authentication | Different | API key flows are supported. Browser or subscription login is intentionally not advertised until implemented. |
| Provider/model runtime | Supported | `pig-llm` owns provider registration, credential resolution, model metadata/capabilities, catalog storage/filtering, and explicit refresh. Refresh failures are provider-scoped and retain the last good snapshot; concurrent refreshes for one provider share a request. Existing `LLM(Config(...))` callers remain supported. Browser/subscription authentication is not implied. |
| SDK/runtime | In progress | `create_agent_session()` exposes a stable embeddable runtime for Python hosts and defaults side-effectful tools to deny unless the host supplies an explicit permission policy. `prompt()` returns stable denial text and `prompt_result()` exposes structured permission denials. Inside the CLI/app surface, `InteractiveMode` owns the interactive shell loop and turn orchestration, `InteractionRuntime` is a thin runtime shell, and dispatch/routes/commands/flows/views are split into dedicated modules. |
| Prompt templates | Partial | Prompt discovery and expansion are supported through `.agents/prompts`. |
| Skills | Partial | Skill discovery and invocation are supported through `.agents/skills`. |
| Dynamic/constrained tools | Supported contract | Tool-result activation anchors are branch-local, and branch switching/restoration recomputes the available set from transcript state. Providers with native deferred-tool support receive unavailable definitions marked for deferred loading; providers without it receive only transcript-available definitions. Strict JSON and regex/Lark grammar schemas are sent only when the selected model explicitly advertises the matching capability. Built-in provider adapters do not claim unsupported capabilities. |
| Compaction | Partial | Manual, threshold, and overflow compactions have distinct reasons and durable before/after checkpoints in session metadata. Tool-activation anchors survive compaction. Token-aware semantic branch summarization parity is still not complete. |
| Cost tracking | Supported | LLM, tool, compaction, and branch-summary usage are recorded as separate categories. Billing hooks receive compatible categorized metadata when supported; structural token reclamation is not misreported as provider spend. |
| Resilience | Supported | Both the primary interactive stream and synchronous one-shot path use `pig-agent-core` resilience. Retry events share a stable retry ID across failure, strategy, success, and exhaustion. Profile rotation rebuilds the provider client with the selected credential before emitting its strategy event. Successful overflow recovery commits a durable Session compaction checkpoint; a stream that has already yielded output is never retried automatically. |

## Verification expectations

- Every row in this matrix should be backed by at least one targeted test.
- Documentation should only claim a capability after the behavior exists in code.
- New parity work should extend this file instead of relying on repository-to-repository comparison during tests.
