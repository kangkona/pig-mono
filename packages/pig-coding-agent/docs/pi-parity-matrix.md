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
| Tool permissions | In progress | Side-effectful tools must be gated by an explicit permission policy. |
| Session tree | Supported | Sessions are tree-backed. `/tree <entry-id>` switches the active branch; interactive `/tree` provides a persistent prompt-based entry/action browser with scope navigation, path/summary chrome, synced details, label/fork/switch actions, and an explicit close action. Switch/fork finish the browser; scope and label actions continue it. Non-terminal surfaces intentionally render a read-only tree summary. Full-screen key navigation is not part of this contract. |
| Settings | Supported | `/settings` shows project/global config locations and exposes the two project-scoped settings the running agent actually consumes: `auto_compact` and `auto_compact_threshold`. Interactive terminals provide a selector/editor; `/settings <key> <value>` validates, persists, and applies both immediately. Other config-model fields remain read-only here until startup/runtime consumption exists. |
| Extensions | Partial | Python extensions can register tools, commands, and event handlers. UI/widget parity is not present. |
| Authentication | Different | API key flows are supported. Browser or subscription login is intentionally not advertised until implemented. |
| SDK/runtime | In progress | `create_agent_session()` exposes a stable embeddable runtime for Python hosts. Inside the CLI/app surface, `InteractiveMode` now owns the interactive shell loop and turn orchestration, `InteractionRuntime` is a thin runtime shell, and dispatch/routes/commands/flows/views are split into dedicated modules. |
| Prompt templates | Partial | Prompt discovery and expansion are supported through `.agents/prompts`. |
| Skills | Partial | Skill discovery and invocation are supported through `.agents/skills`. |
| Compaction | Partial | Automatic compaction exists, but token-aware branch summarization parity is not complete. |
| Cost tracking | Supported | Tool and LLM usage are tracked through the billing hook. |
| Resilience | Supported | API key rotation and context-overflow fallback come from `pig-agent-core`. |

## Verification expectations

- Every row in this matrix should be backed by at least one targeted test.
- Documentation should only claim a capability after the behavior exists in code.
- New parity work should extend this file instead of relying on repository-to-repository comparison during tests.
