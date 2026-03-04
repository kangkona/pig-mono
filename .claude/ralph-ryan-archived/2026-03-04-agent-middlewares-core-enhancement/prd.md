# PRD: Agent Middlewares (Agentwares) — pig-agent-core & pig-messenger Enhancement

## 1. Introduction

**Agent Middlewares (Agentwares)** is a comprehensive enhancement to the existing `pig-agent-core` and `pig-messenger` packages, transforming them into production-ready infrastructure for building AI agents and multi-platform messaging bots. This project extracts and modularizes the battle-tested LiteAgent and Messenger implementations from sophia-pro, creating reusable foundations that sophia-pro and other projects depend on as thin product layers.

**Problem Statement:**
- `pig-agent-core` v0.0.x provides basic agent capabilities but lacks production features (streaming, resilience, context compression, tool budgets, observability)
- `pig-messenger` has basic adapter abstractions but lacks distributed state, agent locking, follow-up queues, streaming, and dead letter management
- sophia-pro's LiteAgent (~4,300 lines) and Messenger (~3,100 lines) have proven capabilities but are tightly coupled to sophia-pro's DB models, Redis, billing, and brand logic
- No standardized middleware exists for building agents across different use cases (coding, social media, research)

**Solution:**
Extract all generic, hardcoded-logic-free capabilities from sophia-pro into `pig-agent-core` and `pig-messenger`. sophia-pro retains only business-specific configuration (brand, billing, DB models) and injects them via extension protocols. The result: sophia-pro shrinks by ~80%, and all hardcore infrastructure becomes shared.

---

## 2. Design Principles

### P1: Extension-First Architecture
sophia-pro's differentiation is achieved through pluggable extensions, never through modifying `pig-*` source code.

**Four extension points:**
- **Tool Extension** — new tool packages (`pig-agent-tools-*`), tool combinations, budget/permission policies
- **Policy Extension** — model routing, retry strategies, fallback preferences, risk control rules
- **Prompt/Context Extension** — system prompt templates, brand voice, task templates, context injectors
- **Workflow Extension** — task orchestration (plan/execute/review), domain-specific agent profiles

**Do:**
- New generic logic defaults to `pig-*` packages first
- sophia-pro depends only on `pig-*` public APIs
- Any "temporary hotfix" with reuse value must be upstreamed within one iteration

**Don't:**
- Fork or monkey-patch `pig-*` core for product differentiation
- Add sophia-pro-specific imports or models inside `pig-*` packages
- Hardcode brand names, user-facing copy, or secret paths in `pig-*`

### P2: Thin Product Layer
sophia-pro becomes a strategy shell over `pig-*` infrastructure.

**Target state:**
- sophia-pro agent layer: ~400 lines (down from ~4,300) — brand prompt, skill config, billing hook, agent factory
- sophia-pro messenger layer: ~500 lines (down from ~3,100) — credential store impl, connection store impl, conversation factory, secret provider

**Verification:**
- Critical paths (task execution, streaming, failure recovery) run 100% through `pig-*` public APIs
- `pig-*` upgrades require zero sophia-pro source code changes (only config/extension updates)
- Core metrics (success rate, latency, recovery rate) do not regress after migration

### P3: Protocol-Driven Extensibility
`pig-agent-core` defines `Protocol` interfaces; products provide implementations.

**Required protocols:**
- `MemoryProvider` — history retrieval and storage
- `ContextLoader` — user/brand context hydration
- `BillingHook` — token/tool usage metering
- `ToolPolicy` — permission, budget, fallback rules
- `SystemPromptBuilder` — system prompt construction

Each protocol ships with a built-in default (in-memory, no-op, or env-based) so `pig-agent-core` works standalone without any product-specific code.

---

## 3. Goals

- **G1:** Enhance `pig-agent-core` with production-ready agent framework (master loop, context compression, resilience, observability, extension protocols)
- **G2:** Extract and modularize tool system from sophia-pro LiteAgent (registry, execution, permissions, budgets, fallback, audit, metrics)
- **G3:** Create `pig-agent-tools` package for extensible tool ecosystem (web tools first, browser/sandbox/social in future)
- **G4:** Absorb sophia-pro's messenger stack into `pig-messenger` (base abstractions, adapters, distributed state, manager routing, streaming)
- **G5:** Enable sophia-pro to replace both its internal LiteAgent and Messenger with `pig-agent-core` v0.1.0 + `pig-messenger` v0.1.0
- **G6:** Maintain backward compatibility with existing `pig-agent-core` v0.0.x API (existing `run()`/`arun()` continue to work)
- **G7:** Achieve measurable competitive advantage: task success rate, recovery rate, time-to-first-output, tool efficiency

---

## 4. Competitive Advantage Metrics

These metrics define what "better than alternatives" means for sophia-pro built on this infrastructure:

| Metric | Definition | Target |
|--------|-----------|--------|
| **Task Success Rate** | % of user tasks completed without manual retry | > 90% |
| **Recovery Rate** | % of transient failures (rate limit, timeout, overflow) auto-recovered | > 95% |
| **Time-to-First-Useful-Output** | Time from user message to first meaningful streamed content | < 3s (P95) |
| **Tool Efficiency** | Average tool calls per completed task | Minimize; track per task type |
| **Context Utilization** | % of context window used before compression triggers | 70-80% sweet spot |

These metrics must be tracked via the observability event system (US-009) and reportable through billing/analytics hooks.

---

## 5. User Stories — pig-agent-core

### Phase 1: Core Framework (P0)

#### US-001: Core Agent Framework — Master Loop
**Description:** As a developer, I want a production-ready agent master loop so that I can build reliable streaming agents with tool calling support.

**Acceptance Criteria:**
- [ ] Add `Agent` class to `pig_agent_core/agent.py` with `respond()` and `respond_stream()` methods
- [ ] Existing `run()` / `arun()` methods continue to work (backward compatibility)
- [ ] Implement `_master_loop()` with streaming LLM calls using `pig-llm`
- [ ] Support tool calling rounds with automatic tool execution
- [ ] Support configurable `max_rounds` (default 7) and `max_rounds_with_plan` (default 12)
- [ ] Plan nag every N rounds after plan tool is used (configurable, default 3)
- [ ] Support cancellation via `asyncio.Event`
- [ ] Accept `SystemPromptBuilder` protocol for system prompt construction
- [ ] Accept `MemoryProvider` protocol for conversation history
- [ ] Typecheck passes
- [ ] Unit tests for master loop with mocked LLM and tools

**Technical Notes:**
- Based on sophia-pro's `lite/agent.py` (664 lines, ~70% generic)
- System prompt, skills config, thresholds must be injected, not hardcoded
- Default `SystemPromptBuilder` returns empty system prompt
- Default `MemoryProvider` uses in-memory list

---

#### US-002: Tool System — Base Types and Result Envelope
**Description:** As a developer, I want a standardized tool result format so that tools can return structured data with error handling.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/tools/base.py` with `ToolResult` dataclass
- [ ] `ToolResult` has `ok: bool`, `data: Any`, `error: str | None`, `meta: dict`
- [ ] Implement `serialize(max_chars)` method with structure-aware truncation
- [ ] Implement `_try_shrink()` and `_compact_items_text()` for intelligent content reduction
- [ ] Add `CancelledError` exception for tool cancellation
- [ ] Add `validate_url()` — blocks private IPs, localhost, metadata endpoints, non-HTTP schemes
- [ ] Add `_fn()` helper for building OpenAI function-calling schemas
- [ ] Typecheck passes
- [ ] Unit tests for ToolResult serialization, URL validation, schema builder

**Technical Notes:**
- Port from sophia-pro's `lite/tools/base.py` (281 lines, ~95% generic)
- Truncation logic preserves list/dict structure when possible
- URL validation must also check resolved IPs after DNS (prevent DNS rebinding)

---

#### US-003: Tool System — Registry and Execution
**Description:** As a developer, I want a tool registry that can dynamically load and execute tools with budgets, fallback, and safety gates.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/tools/registry.py` with `ToolRegistry` class
- [ ] Support `register(name, handler, schema)` for tool registration
- [ ] Support `execute(tool_call, user_id, meta, cancel)` with per-tool timeout and retry
- [ ] Implement lazy loading (core tools always loaded, others on-demand via `activate_tools()`)
- [ ] Implement tool fallback mapping (e.g., `search_x` fails → try `search_web`)
- [ ] Implement write-tool confirmation gate (`confirmed` flag required for write tools)
- [ ] Implement parallel execution for read-only tools, sequential for write tools
- [ ] Validate schema/handler/budget consistency at registration time
- [ ] Support cancel event checking during execution
- [ ] Typecheck passes
- [ ] Unit tests for registry with mock tools covering all paths

**Technical Notes:**
- Port from sophia-pro's `lite/tools/registry.py` (302 lines, ~90% generic)
- Use `asyncio.wait_for` for timeout
- Fallback mapping is configurable via `ToolPolicy` protocol

---

#### US-004: Tool System — Core Tool Schemas
**Description:** As a developer, I want core agent tools (think, plan, discover_tools, get_current_time) so that agents have basic reasoning capabilities.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/tools/schemas.py` with tool schema definitions
- [ ] Define `think` tool schema (permission: none)
- [ ] Define `plan` tool schema (permission: none)
- [ ] Define `discover_tools` tool schema (permission: none)
- [ ] Define `get_current_time` tool schema (permission: none)
- [ ] Add `CORE_TOOL_NAMES`, `TOOL_BUDGETS`, `TOOL_PERMISSIONS` constants
- [ ] Add `DEFERRED_TOOL_INDEX` for keyword-based tool discovery
- [ ] Add `PARALLEL_SAFE_TOOLS` set for execution strategy
- [ ] Typecheck passes
- [ ] Schemas validate against OpenAI function calling format

**Technical Notes:**
- Port from sophia-pro's `lite/tools/schemas.py` (455 lines, ~30% generic — only core tool schemas)
- Permission levels: none, read, storage, write
- Product-specific tool schemas (brand, email, schedule) stay in sophia-pro

---

#### US-005: Tool System — Core Tool Handlers
**Description:** As a developer, I want implementations for core tools so that agents can reason and plan.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/tools/handlers_core.py` with core tool handlers
- [ ] Implement `handle_think(args, user_id, meta)` — returns thinking content
- [ ] Implement `handle_plan(args, user_id, meta)` — validates and stores plan
- [ ] Implement `handle_discover_tools(args, user_id, meta)` — returns matching tool schemas from deferred index
- [ ] Implement `handle_get_current_time(args, user_id, meta)` — returns current time with timezone
- [ ] Add `HANDLERS` dict mapping tool names to handlers
- [ ] Typecheck passes
- [ ] Unit tests for each handler

**Technical Notes:**
- Port from sophia-pro's `lite/tools/handlers_agent.py` (385 lines, only ~20% is generic core tools)
- Product-specific handlers (brand, email, schedule, skills, memory) stay in sophia-pro

---

#### US-006: Context Management and Compression
**Description:** As a developer, I want context management with multi-level compression so that agents handle long conversations without overflow.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/context.py` with `ContextLoader` protocol and `SimpleContext` default
- [ ] Implement 3-level context compression in Agent:
  - Level 1 (70% capacity): truncate old tool results
  - Level 2 (80% capacity): replace old tool I/O with summaries
  - Level 3 (90% capacity): LLM-summarize middle messages
- [ ] Add `_build_messages(ctx, history, user_text)` method to Agent class
- [ ] Support `SystemPromptBuilder` protocol for system prompt injection with context variables
- [ ] Typecheck passes
- [ ] Unit tests for message building and each compression level

**Technical Notes:**
- Port compression from sophia-pro's `agent.py` L559-664
- Port context pattern from sophia-pro's `lite/context.py` (145 lines, ~40% generic)
- Compression thresholds must be configurable (not hardcoded 70/80/90)
- Default `ContextLoader` returns empty context; sophia-pro injects brand/user/memory

---

#### US-007: Token Counter
**Description:** As a developer, I want accurate token counting so that context compression triggers at the right time.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/token_counter.py` with `count_tokens(text, model)` function
- [ ] Use `tiktoken` when available, fall back to character-based estimation
- [ ] Cache tokenizer instances per model
- [ ] Typecheck passes
- [ ] Unit tests for both tiktoken and fallback paths

**Technical Notes:**
- Port from sophia-pro's `lite/token_counter.py` (47 lines, 100% generic)
- `tiktoken` should be an optional dependency

---

#### US-008: Resilience System — Profile Manager
**Description:** As a developer, I want API key rotation and fallback models so that agents are resilient to rate limits and failures.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/resilience/profile.py` with `ProfileManager` class
- [ ] Implement `FailoverReason` enum and `classify_failure()` for LLM error classification
- [ ] Support multiple API keys with per-failure-type cooldown tracking
- [ ] Implement `get_next_profile()` for key rotation
- [ ] Support fallback models configuration
- [ ] Add `from_env()` class method to load from environment variables
- [ ] Configurable cooldown periods: auth (default 300s), rate (default 120s), timeout (default 60s)
- [ ] Typecheck passes
- [ ] Unit tests for profile rotation logic and failure classification

**Technical Notes:**
- Port from sophia-pro's `lite/resilience.py` (347 lines, ~95% generic)
- Environment variables: `PIG_AGENT_BACKUP_KEYS` (with `LITE_AGENT_BACKUP_KEYS` as compat alias)
- LLM client creation must be provider-agnostic (no `shared.llm` dependency)

---

#### US-009: Resilience System — Resilient LLM Calls
**Description:** As a developer, I want automatic retry and fallback for LLM calls so that agents handle transient failures gracefully.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/resilience/retry.py` with `resilient_streaming_call()` function
- [ ] Implement Layer 1: Profile rotation on rate_limit/auth/billing/timeout errors
- [ ] Implement Layer 2: Context overflow recovery (call `compress_fn` and retry, up to `MAX_OVERFLOW_COMPACTIONS`)
- [ ] Implement Layer 3: Fallback to alternative models from `PIG_AGENT_FALLBACK_MODELS`
- [ ] Raise `ResilienceExhaustedError` when all layers fail
- [ ] Integrate with `pig-llm` error types
- [ ] Emit resilience events (`resilience_compact`, `resilience_retry`, `resilience_fallback`)
- [ ] Typecheck passes
- [ ] Unit tests with mocked LLM failures for each layer

**Technical Notes:**
- Port from sophia-pro's `lite/resilience.py`
- Use `pig-llm` exceptions for error detection
- `compress_fn` is injected by the Agent, not hardcoded

---

#### US-010: Observability — Event System
**Description:** As a developer, I want an event system for tracking agent execution so that I can monitor, debug, and meter agents.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/observability/events.py` with event types
- [ ] Define event types: `agent_start`, `agent_end`, `turn_start`, `turn_end`, `tool_call_start`, `tool_call_end`, `resilience_compact`, `resilience_retry`, `resilience_fallback`
- [ ] Implement `emit(callback, event)` function (fire-and-forget, handles sync/async callbacks)
- [ ] Implement `span(name, attrs)` context manager for OTel tracing
- [ ] Add `AgentEventCallback` type alias
- [ ] Add `BillingHook` protocol — receives token usage and tool execution events
- [ ] Default `BillingHook` is no-op
- [ ] Typecheck passes
- [ ] Unit tests for event emission (sync and async callbacks)

**Technical Notes:**
- Port from sophia-pro's `lite/observability.py` (53 lines, 100% generic)
- Port billing hook pattern from sophia-pro's `lite/billing.py` (67 lines)
- Events are dicts with `type` and data fields
- Callback is optional (for testing/monitoring)

---

#### US-011: Tool Audit and Metrics
**Description:** As a developer, I want tool usage auditing and metrics so that I can track, debug, and optimize tool usage.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/tools/audit.py` with audit logging for write tools
- [ ] Create `pig_agent_core/tools/metrics.py` with per-tool and per-user metrics tracking
- [ ] Audit log captures: tool name, user_id, args (sanitized), result summary, timestamp
- [ ] Metrics track: call count, success/failure rate, avg duration, per tool and per user
- [ ] Both are opt-in (disabled by default, enabled via config)
- [ ] Typecheck passes
- [ ] Unit tests for audit recording and metrics aggregation

**Technical Notes:**
- Port from sophia-pro's `lite/tools/audit.py` (67 lines, ~90% generic) and `metrics.py` (128 lines, ~90% generic)
- Audit storage is pluggable (default: logging, sophia-pro: DB)
- Metrics storage is pluggable (default: in-memory counters)

---

#### US-012: Memory Protocol and Default Implementation
**Description:** As a developer, I want a memory protocol so that agents can retrieve and store conversation history, with products providing their own storage backends.

**Acceptance Criteria:**
- [ ] Create `pig_agent_core/memory.py` with `MemoryProvider` protocol
- [ ] Protocol defines: `get_history(user_id, session_id) -> list[dict]`, `save_turn(user_id, session_id, messages)`, `clear(user_id, session_id)`
- [ ] Implement `InMemoryProvider` as default (list-based, no persistence)
- [ ] Agent class accepts `MemoryProvider` in constructor
- [ ] Typecheck passes
- [ ] Unit tests for `InMemoryProvider`

**Technical Notes:**
- sophia-pro's `lite/memory.py` (517 lines) has 3-layer Redis+compaction+PostgreSQL implementation
- Only the protocol interface goes into `pig-agent-core`; sophia-pro provides its own `RedisPostgresMemoryProvider`
- This unblocks the master loop without creating DB dependencies

---

#### US-013: Extension Protocols — Wire Together
**Description:** As a developer, I want the Agent class to integrate all subsystems via protocols so that I have a complete, extensible working agent.

**Acceptance Criteria:**
- [ ] Update `Agent.__init__()` to accept: `MemoryProvider`, `ContextLoader`, `SystemPromptBuilder`, `BillingHook`, `ToolPolicy`, `AgentEventCallback`
- [ ] All parameters have working defaults (in-memory, no-op, env-based)
- [ ] Implement `respond()` method using master loop + tools + resilience + compression
- [ ] Implement `respond_stream()` method for streaming responses
- [ ] Emit events at key execution points
- [ ] Call `BillingHook` on token usage and tool execution
- [ ] Backward compatible: existing `run()`/`arun()` still work via internal delegation
- [ ] Typecheck passes
- [ ] Integration test with mocked LLM (no real API calls in CI)
- [ ] Smoke test with real LLM (manual/nightly only, not in CI)

**Technical Notes:**
- Integrate all US-001 through US-012
- Use `resilient_streaming_call()` for all LLM calls
- Default model: from `PIG_AGENT_MODEL` env var (with `LITE_AGENT_MODEL` compat alias)
- Model-specific token budget resolved dynamically, not hardcoded to 200K

---

### Phase 2: Tool Extensions (P1)

#### US-014: Package Structure — pig-agent-tools Foundation
**Description:** As a developer, I want a separate package for tool extensions so that I can install tools on-demand.

**Acceptance Criteria:**
- [ ] Create `packages/pig-agent-tools/` directory structure
- [ ] Add `pyproject.toml` with dependency on `pig-agent-core>=0.1.0`
- [ ] Create `src/pig_agent_tools/__init__.py` with package exports
- [ ] Typecheck passes
- [ ] Package builds successfully with `uv build`

**Technical Notes:**
- Separate package for optional dependencies
- Will contain web, social, browser, sandbox tools

---

#### US-015: Web Tools — Search and Read Webpage
**Description:** As a developer, I want web search and webpage reading tools so that agents can access web information.

**Acceptance Criteria:**
- [ ] Create `pig_agent_tools/web/handlers.py` with web tool handlers
- [ ] Implement `handle_search_web(args, user_id, meta)` using Tavily API
- [ ] Implement `handle_read_webpage(args, user_id, meta)` with URL validation (uses `validate_url` from core)
- [ ] Add tool schemas to `pig_agent_tools/web/schemas.py`
- [ ] Add `HANDLERS` dict for web tools
- [ ] Typecheck passes
- [ ] Unit tests with mocked HTTP calls

**Technical Notes:**
- Port from sophia-pro's `lite/tools/handlers_web.py` (171 lines, ~95% generic)
- Tavily API key from environment: `TAVILY_API_KEY`
- URL validation delegates to `pig_agent_core.tools.base.validate_url()`
- Must validate resolved IP after redirect chains (SSRF defense-in-depth)

---

#### US-016: Tool Registration API
**Description:** As a developer, I want a clean tool registration API so that tool packages can register with explicit control.

**Acceptance Criteria:**
- [ ] Add `register_tools(registry)` function to `pig_agent_tools/web/__init__.py`
- [ ] Registration requires explicit `registry` parameter (no global singleton)
- [ ] Update `pig_agent_core.tools.ToolRegistry` to support external package registration
- [ ] Typecheck passes
- [ ] Integration test: create registry, register web tools, verify tools are available

**Technical Notes:**
- Avoid import side-effect registration (causes test isolation and concurrency issues)
- Provide convenience helper: `registry.register_package(pig_agent_tools.web)` that calls `register_tools(registry)`

---

## 6. User Stories — pig-messenger

### Phase 3: Messenger Absorption (P0, parallel with Phase 1)

#### US-017: Messenger Base Abstractions
**Description:** As a developer, I want production-grade messenger abstractions so that I can build multi-platform bots with streaming, threading, and file support.

**Acceptance Criteria:**
- [ ] Replace existing `pig_messenger/message.py` + `platform.py` with new `pig_messenger/base.py`
- [ ] Implement `MessengerType` enum (SLACK, DISCORD, TELEGRAM, WHATSAPP, WEBCHAT)
- [ ] Implement `MessengerUser` dataclass
- [ ] Implement `IncomingMessage` dataclass with `thread_key`, `reply_thread_id`, `owner_user_id`
- [ ] Implement `MessengerCapabilities` dataclass (feature flags + limits)
- [ ] Implement `MessengerThread` — bound context for adapter + coordinates, with:
  - `post()`, `update()`, `delete()`, `react()`, `typing()`
  - `post_file()`, `post_file_content()`, `post_blocks()`
  - `stream()` — edit-based streaming with fallback to batch
  - `_stream_via_draft()` — native draft streaming (Telegram-style)
- [ ] Implement `BaseMessengerAdapter` ABC with full method set
- [ ] Add `_split_text()` utility for message chunking
- [ ] Typecheck passes
- [ ] Unit tests for MessengerThread streaming logic

**Technical Notes:**
- Port from sophia-pro's `messenger/base.py` (487 lines, 99% generic)
- Replace `app.core.logging.get_logger` with `logging.getLogger`
- This replaces pig-messenger's existing simpler abstractions

---

#### US-018: Messenger Adapter Registry
**Description:** As a developer, I want a decorator-based adapter registry so that platform adapters can self-register.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/registry.py` with `MessengerRegistry` class
- [ ] Support `@MessengerRegistry.register(MessengerType.SLACK)` decorator
- [ ] Support `get_class()`, `get_instance()`, `all_types()`, `is_registered()`, `clear_all()`
- [ ] Typecheck passes
- [ ] Unit tests for registry lifecycle

**Technical Notes:**
- Port from sophia-pro's `messenger/registry.py` (72 lines, 100% generic)

---

#### US-019: Messenger Distributed State
**Description:** As a developer, I want distributed state management so that messenger bots handle concurrency, deduplication, and failure recovery correctly.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/state.py` with `MessengerState` class
- [ ] Accept `redis_client` via constructor (no internal import of Redis factory)
- [ ] Implement event deduplication (`check_event_dedup`)
- [ ] Implement agent lock with Lua-based atomic acquire/release/renew (`acquire_agent_lock`, `release_agent_lock`, `renew_agent_lock`)
- [ ] Implement atomic lock-release-if-queue-empty (`release_lock_if_queue_empty`)
- [ ] Implement cancel flag management (`set/clear/watch_cancel_flag`)
- [ ] Implement follow-up queue with Lua-based atomic drain (`enqueue_followup`, `drain_followups`)
- [ ] Implement dead letter management (`record_dead_letter`, `list_dead_letters`, `replay_dead_letters`)
- [ ] Implement conversation creation lock (`acquire/release_conv_create_lock`)
- [ ] All TTLs and limits configurable via constructor (with sensible defaults)
- [ ] Typecheck passes
- [ ] Unit tests with mocked Redis

**Technical Notes:**
- Port from sophia-pro's `messenger/state.py` (253 lines, 95% generic)
- Default constants: `EVENT_DEDUP_TTL=60`, `AGENT_LOCK_TTL=300`, `FOLLOWUP_QUEUE_TTL=600`, `FOLLOWUP_MAX_PENDING=5`, `DEAD_LETTER_MAX=200`
- Redis key prefix: `"messenger:"` (configurable)

---

#### US-020: Messenger Manager
**Description:** As a developer, I want a message routing and processing manager so that incoming messages are routed to agents with proper concurrency control.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/manager.py` with `MessengerManager` class
- [ ] Implement `handle_event()` — parses event via adapter, routes to processing
- [ ] Implement `_process_message()` — agent lock → agent call → streaming → follow-up drain
- [ ] Accept `AgentFactory` callback for agent creation (not hardcoded LiteAgent)
- [ ] Accept `ConversationFactory` callback for conversation creation (not hardcoded ORM)
- [ ] Implement follow-up drain loop with configurable `max_rounds` (default 8)
- [ ] Implement background task spawning with error handling
- [ ] Implement dead letter management (list, replay)
- [ ] Implement Discord leader election via Redis (generic pattern)
- [ ] Extract `split_message()` as standalone utility
- [ ] All user-facing copy (e.g., "Got it — I'll handle this...") configurable via constructor/config
- [ ] Implement `shutdown()` for graceful cleanup
- [ ] Typecheck passes
- [ ] Unit tests for message routing and follow-up drain

**Technical Notes:**
- Port from sophia-pro's `messenger/manager.py` (469 lines, ~50% generic after extracting callbacks)
- sophia-pro injects: `LiteAgent` via `AgentFactory`, `Conversation` model via `ConversationFactory`, billing via `BillingHook`
- Stream interval: 250ms for Telegram, 500ms for others (configurable per platform)

---

#### US-021: Messenger Store Interfaces
**Description:** As a developer, I want abstract store interfaces for credentials and connections so that products can plug in their own storage backends.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/stores.py` with:
  - `CredentialStore` ABC — `get_bot_token(messenger_type, workspace_id)`, `store_credentials(...)`, `invalidate_cache()`
  - `ConnectionStore` ABC — `get_owner(messenger_type, channel_id)`, `create_connection(...)`, `revoke_connection(...)`, `list_connections(...)`
- [ ] Implement `_TTLCache` utility class (in-memory TTL cache)
- [ ] Implement `encrypt_value()` / `decrypt_value()` utilities (Fernet-based)
- [ ] Typecheck passes
- [ ] Unit tests for TTLCache and encryption utilities

**Technical Notes:**
- Port interfaces and utilities from sophia-pro's `messenger/stores.py` (352 lines, ~30% generic)
- SQLAlchemy implementations (`MessengerConnection` ORM queries) stay in sophia-pro
- Encryption key source is configurable (env var, not `app.core.config`)

---

#### US-022: Messenger Config Dataclasses
**Description:** As a developer, I want platform config dataclasses so that adapter configuration is structured and type-safe.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/config.py` with `SlackConfig`, `DiscordConfig`, `TelegramConfig`, `WhatsAppConfig` dataclasses
- [ ] Each config loadable from environment variables via `from_env()` class method
- [ ] Define `SecretProvider` protocol for pluggable secret fetching
- [ ] Default `SecretProvider` reads from env vars only
- [ ] Typecheck passes
- [ ] Unit tests for config loading from env

**Technical Notes:**
- Port dataclasses from sophia-pro's `messenger/config.py` (178 lines, ~40% generic)
- AWS Secrets Manager fallback stays in sophia-pro as `AWSSecretProvider` implementation
- Remove all `karis/...` path references

---

#### US-023: Platform Adapters — Telegram
**Description:** As a developer, I want a production-ready Telegram adapter with draft streaming, file upload, and signature verification.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/adapters/telegram.py` with `TelegramMessengerAdapter`
- [ ] Implement: `parse_event`, `send_message`, `update_message`, `send_typing`, `send_draft`, `send_file`, `send_file_content`, `verify_signature`
- [ ] Support Bot API draft streaming (API 9.5+)
- [ ] Typecheck passes
- [ ] Unit tests with mocked HTTP

**Technical Notes:**
- Port from sophia-pro's `adapters/telegram.py` (288 lines, 99% generic)
- Uses `httpx` for HTTP calls (no external Telegram library dependency)

---

#### US-024: Platform Adapters — Slack
**Description:** As a developer, I want a production-ready Slack adapter with blocks, reactions, files, and markdown conversion.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/adapters/slack.py` with `SlackMessengerAdapter`
- [ ] Implement: `parse_event`, `send_message`, `update_message`, `delete_message`, `send_reaction`, `send_blocks`, `send_file`, `send_file_content`, `verify_signature`, `open_dm`, `get_user_tz`
- [ ] Include `markdown_to_mrkdwn()` utility for Markdown-to-Slack conversion
- [ ] Per-workspace `AsyncWebClient` instances
- [ ] HMAC-SHA256 signature verification
- [ ] Typecheck passes
- [ ] Unit tests with mocked Slack API

**Technical Notes:**
- Port from sophia-pro's `adapters/slack.py` (318 lines, 99% generic)
- Requires `slack-sdk` as optional dependency

---

#### US-025: Platform Adapters — Discord
**Description:** As a developer, I want a production-ready Discord adapter with Gateway support, embeds, and shared client management.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/adapters/discord.py` with `DiscordMessengerAdapter`
- [ ] Implement: `parse_event`, `send_message`, `update_message`, `delete_message`, `send_typing`, `send_reaction`, `send_blocks` (Slack blocks → Discord embeds), `send_file`, `send_file_content`, `open_dm`
- [ ] Shared `discord.py` client with Gateway events
- [ ] Typecheck passes
- [ ] Unit tests with mocked Discord API

**Technical Notes:**
- Port from sophia-pro's `adapters/discord.py` (436 lines, 99% generic)
- Requires `discord.py` as optional dependency

---

#### US-026: Platform Adapters — WhatsApp
**Description:** As a developer, I want a production-ready WhatsApp adapter with Twilio integration and E.164 phone normalization.

**Acceptance Criteria:**
- [ ] Create `pig_messenger/adapters/whatsapp.py` with `WhatsAppMessengerAdapter`
- [ ] Implement: `parse_event`, `send_message`, `update_message`, `verify_signature`
- [ ] Include `normalize_phone_e164()` utility
- [ ] Twilio RequestValidator signature verification
- [ ] Typecheck passes
- [ ] Unit tests with mocked Twilio API

**Technical Notes:**
- Port from sophia-pro's `adapters/whatsapp.py` (174 lines, 99% generic)
- Requires `twilio` as optional dependency

---

### Phase 4: Documentation, Examples, Testing (P1)

#### US-027: Documentation — Core Package README
**Description:** As a developer, I want comprehensive documentation for pig-agent-core v0.1.0.

**Acceptance Criteria:**
- [ ] Update `packages/pig-agent-core/README.md` with v0.1.0 features
- [ ] Add "Quick Start" with basic agent example
- [ ] Add "Architecture" explaining master loop, tools, resilience, extension protocols
- [ ] Add "Extension Protocols" documenting each protocol with example implementation
- [ ] Add "Migration Guide" for v0.0.x users (`run()` → `respond()`)
- [ ] Include code examples for common use cases
- [ ] Verify all code examples run successfully

---

#### US-028: Documentation — Messenger Package README
**Description:** As a developer, I want comprehensive documentation for pig-messenger v0.1.0.

**Acceptance Criteria:**
- [ ] Update `packages/pig-messenger/README.md` with v0.1.0 features
- [ ] Add "Quick Start" with multi-platform bot example
- [ ] Add "Architecture" explaining adapter pattern, distributed state, manager routing
- [ ] Add "Platform Guides" for each supported platform (Telegram, Slack, Discord, WhatsApp)
- [ ] Add "Extension Points" documenting AgentFactory, ConversationFactory, SecretProvider
- [ ] Include code examples

---

#### US-029: Documentation — Tools Package README
**Description:** As a developer, I want documentation for pig-agent-tools.

**Acceptance Criteria:**
- [ ] Create `packages/pig-agent-tools/README.md`
- [ ] Add "Installation" with optional dependencies
- [ ] Add "Available Tools" listing web tools
- [ ] Add "Creating Custom Tools" guide
- [ ] Add example showing tool registration with Agent

---

#### US-030: Examples
**Description:** As a developer, I want working examples for all major features.

**Acceptance Criteria:**
- [ ] Create `packages/pig-agent-core/examples/basic_agent.py` — Agent with think/plan tools
- [ ] Create `packages/pig-agent-core/examples/custom_extensions.py` — Agent with custom MemoryProvider and BillingHook
- [ ] Create `packages/pig-agent-tools/examples/web_agent.py` — Agent with web tools
- [ ] Create `packages/pig-messenger/examples/telegram_bot.py` — Telegram bot with streaming
- [ ] All examples run successfully with appropriate API keys

---

#### US-031: Testing — Core Package
**Description:** As a developer, I want comprehensive tests for pig-agent-core.

**Acceptance Criteria:**
- [ ] Tests for Agent class (master loop, respond, respond_stream, backward compat)
- [ ] Tests for ToolRegistry (register, execute, lazy loading, fallback, confirmation gate)
- [ ] Tests for resilience (profile rotation, retry logic, each layer)
- [ ] Tests for observability (event emission, billing hook)
- [ ] Tests for context compression (3 levels)
- [ ] Tests for token counter (tiktoken + fallback)
- [ ] Tests for audit and metrics
- [ ] All tests pass with `pytest`, all use mocks (no real API calls)
- [ ] Test coverage > 80%

---

#### US-032: Testing — Messenger Package
**Description:** As a developer, I want comprehensive tests for pig-messenger.

**Acceptance Criteria:**
- [ ] Tests for MessengerThread (streaming, fallback)
- [ ] Tests for MessengerState (dedup, locks, queues, dead letters) with mocked Redis
- [ ] Tests for MessengerManager (routing, follow-up drain, shutdown)
- [ ] Tests for each adapter (parse_event, send_message, verify_signature) with mocked APIs
- [ ] Tests for split_message edge cases
- [ ] All tests pass with `pytest`
- [ ] Test coverage > 80%

---

#### US-033: Testing — Tools Package
**Description:** As a developer, I want tests for pig-agent-tools.

**Acceptance Criteria:**
- [ ] Tests for web tools (search_web, read_webpage) with mocked HTTP
- [ ] Tests for URL validation (SSRF, redirects, private IPs)
- [ ] All tests pass with `pytest`
- [ ] Test coverage > 80%

---

#### US-034: Integration — sophia-pro Migration Validation
**Description:** As a sophia-pro maintainer, I want to validate that pig-agent-core + pig-messenger can replace LiteAgent + Messenger.

**Acceptance Criteria:**
- [ ] Create `test_sophia_compat.py` replicating sophia-pro's LiteAgent usage patterns
- [ ] Test validates: tool calling, memory (mocked), resilience, events, billing hook
- [ ] Create `test_messenger_compat.py` replicating sophia-pro's Messenger patterns
- [ ] Test validates: event routing, agent lock, follow-up queue, streaming, dead letters
- [ ] Document any API differences in migration guide
- [ ] All tests pass

---

## 7. Functional Requirements

**FR-1:** The system must maintain backward compatibility with pig-agent-core v0.0.x API — existing `run()`/`arun()` methods continue to work, existing `ToolResult`/`ToolRegistry` remain importable

**FR-2:** The Agent class must support both non-streaming (`respond()`) and streaming (`respond_stream()`) responses

**FR-3:** The tool system must support lazy loading of tools to minimize initial context size

**FR-4:** The resilience system must automatically rotate API keys on rate limit errors

**FR-5:** The resilience system must compress context and retry on context overflow errors (3-level compression)

**FR-6:** The tool registry must validate tool schemas at registration time

**FR-7:** The tool execution must respect per-tool timeout and retry budgets

**FR-8:** The event system must emit events for all major execution milestones

**FR-9:** Both packages must work with Python 3.10+

**FR-10:** pig-agent-core must integrate with pig-llm for all LLM calls

**FR-11:** pig-agent-tools must support optional installation of tool categories

**FR-12:** Web tools must validate URLs to prevent SSRF attacks (including post-redirect and DNS rebinding)

**FR-13:** Write tools must require explicit confirmation before execution

**FR-14:** Read-only tools may execute in parallel; write tools must execute sequentially

**FR-15:** pig-messenger must support Redis-backed distributed state (locking, dedup, queues)

**FR-16:** pig-messenger adapters must each be an optional dependency (slack-sdk, discord.py, twilio)

**FR-17:** All extension protocols must have working built-in defaults so packages function standalone

**FR-18:** Token budget must resolve dynamically based on the active model, not hardcoded

---

## 8. Non-Goals

**NG-1:** Full memory system implementation (sophia-pro provides `RedisPostgresMemoryProvider`; core only defines protocol + in-memory default)

**NG-2:** Social media tools — X, Reddit, YouTube (deferred to Iteration 2)

**NG-3:** Browser automation tools (deferred to Iteration 2; sophia-pro's CDP code is ~90% generic)

**NG-4:** Code execution sandbox tools (deferred to Iteration 2; sandbox session pool is ~90% generic)

**NG-5:** Skill system — `use_skill` tool (deferred to Iteration 3)

**NG-6:** Database persistence for agent messages (core is storage-agnostic; products use protocols)

**NG-7:** HTTP API endpoints (pig-agent-core is a library, not a service)

**NG-8:** Frontend components (backend middleware only)

**NG-9:** Feishu adapter (not present in sophia-pro's generic messenger; pig-messenger's existing Feishu adapter can be maintained separately)

---

## 9. Technical Considerations

### Dependencies — pig-agent-core
- **pig-llm** (>=0.0.2): LLM unified interface with tool_calls support
- **pydantic** (>=2.6.0): Data validation
- **httpx** (>=0.26.0): HTTP client (for URL validation, web tools in pig-agent-tools)
- **tiktoken** (optional): Token counting (falls back to char estimation)

### Dependencies — pig-messenger
- **pydantic** (>=2.6.0): Data validation
- **httpx** (>=0.26.0): HTTP client (Telegram adapter)
- **redis** (>=5.0.0): Distributed state (optional; in-memory fallback for local dev)
- **cryptography** (>=42.0.0): Credential encryption
- **slack-sdk** (optional): Slack adapter
- **discord.py** (optional): Discord adapter
- **twilio** (optional): WhatsApp adapter

### Environment Variables
| Variable | Package | Default | Compat Alias |
|----------|---------|---------|--------------|
| `PIG_AGENT_MODEL` | core | `anthropic/claude-sonnet-4-20250514` | `LITE_AGENT_MODEL` |
| `PIG_AGENT_MAX_ROUNDS` | core | `7` | `LITE_AGENT_MAX_ROUNDS` |
| `PIG_AGENT_BACKUP_KEYS` | core | (none) | `LITE_AGENT_BACKUP_KEYS` |
| `PIG_AGENT_FALLBACK_MODELS` | core | (none) | `LITE_AGENT_FALLBACK_MODELS` |
| `PIG_AGENT_COOLDOWN_AUTH` | core | `300` | `LITE_AGENT_COOLDOWN_AUTH` |
| `PIG_AGENT_COOLDOWN_RATE` | core | `120` | `LITE_AGENT_COOLDOWN_RATE` |
| `PIG_AGENT_COOLDOWN_TIMEOUT` | core | `60` | `LITE_AGENT_COOLDOWN_TIMEOUT` |
| `TAVILY_API_KEY` | tools | (none) | — |

### Token Budget
- Token budget resolved dynamically from model metadata (via `pig-llm`)
- Context compression thresholds: configurable (default 70% / 80% / 90%)
- Tool result serialization: configurable max chars (default 5000)

### Error Handling
- All tool handlers must return `ToolResult` (never raise exceptions)
- LLM errors trigger resilience layers (rotation → compression → fallback)
- Network errors in tools should be caught and returned as `ToolResult(ok=False)`
- Messenger errors route to dead letter queue for later replay

### Security
- URL validation blocks private IPs, localhost, metadata endpoints, non-HTTP schemes
- Post-redirect IP re-validation to prevent SSRF via redirects
- Tool permissions enforce read/write separation
- Write tools require explicit confirmation flag
- No arbitrary code execution in core framework
- Credential encryption at rest (Fernet)

---

## 10. Success Metrics

**M-1:** sophia-pro successfully replaces internal LiteAgent with pig-agent-core v0.1.0

**M-2:** sophia-pro successfully replaces internal Messenger with pig-messenger v0.1.0

**M-3:** sophia-pro agent code shrinks by ≥ 80% (from ~4,300 to ~400 lines)

**M-4:** sophia-pro messenger code shrinks by ≥ 80% (from ~3,100 to ~500 lines)

**M-5:** All user stories completed with passing tests

**M-6:** Test coverage > 80% for all three packages

**M-7:** Core metrics do not regress after migration (success rate, latency, recovery rate)

**M-8:** Zero breaking changes to existing pig-agent-core v0.0.x API

**M-9:** Packages build and install on Python 3.10, 3.11, 3.12, 3.13

---

## 11. Timeline Estimate

**Phase 1: Core Framework — pig-agent-core (US-001 to US-013)** — 3 weeks
- Master loop, tool system, resilience, observability, compression, protocols, memory protocol

**Phase 2: Tool Extensions — pig-agent-tools (US-014 to US-016)** — 1 week
- Package structure, web tools, registration API

**Phase 3: Messenger Absorption — pig-messenger (US-017 to US-026)** — 3 weeks (parallel with Phase 1)
- Base abstractions, state, manager, stores, config, 4 adapters

**Phase 4: Docs, Examples, Testing (US-027 to US-034)** — 2 weeks
- READMEs, examples, test suites, sophia-pro compatibility validation

**Total: 6 weeks** (Phases 1+3 run in parallel → critical path is 5 weeks)

---

## 12. Future Iterations

**Iteration 2: Advanced Tools**
- Browser automation tools (port sophia-pro's CDP code, ~396 lines, ~80% generic)
- Code execution sandbox tools + warm pool (port sandbox_session.py, ~385 lines, ~90% generic)
- Social media tools: X/Twitter, Reddit, YouTube

**Iteration 3: Skill System**
- Skill file management and `use_skill` tool
- Skill lazy loading and discovery

**Iteration 4: Memory Enhancement**
- Reference `RedisPostgresMemoryProvider` implementation for other products
- Memory compaction strategies
- Summary + Facts dual-layer structure

**Iteration 5: Observability & Analytics**
- Dashboard for competitive metrics (success rate, recovery rate, TTFO, tool efficiency)
- A/B testing framework for model routing and prompt strategies

---

## Appendix A: Absorption Source Map

### pig-agent-core ← sophia-pro lite/

| Target Module | Source File | Lines | Generic % |
|---------------|-----------|-------|-----------|
| `agent.py` | `lite/agent.py` | 664 | ~70% |
| `tools/base.py` | `lite/tools/base.py` | 281 | ~95% |
| `tools/registry.py` | `lite/tools/registry.py` | 302 | ~90% |
| `tools/schemas.py` | `lite/tools/schemas.py` | 455 | ~30% (core only) |
| `tools/handlers_core.py` | `lite/tools/handlers_agent.py` | 385 | ~20% (core only) |
| `tools/audit.py` | `lite/tools/audit.py` | 67 | ~90% |
| `tools/metrics.py` | `lite/tools/metrics.py` | 128 | ~90% |
| `resilience/profile.py` | `lite/resilience.py` | 347 | ~95% |
| `resilience/retry.py` | `lite/resilience.py` | (same) | ~95% |
| `observability/events.py` | `lite/observability.py` | 53 | 100% |
| `token_counter.py` | `lite/token_counter.py` | 47 | 100% |
| `context.py` | `lite/context.py` | 145 | ~40% (protocol only) |
| `memory.py` | `lite/memory.py` | 517 | protocol only |

### pig-messenger ← sophia-pro messenger/

| Target Module | Source File | Lines | Generic % |
|---------------|-----------|-------|-----------|
| `base.py` | `messenger/base.py` | 487 | 99% |
| `registry.py` | `messenger/registry.py` | 72 | 100% |
| `state.py` | `messenger/state.py` | 253 | 95% |
| `manager.py` | `messenger/manager.py` | 469 | ~50% (after callback extraction) |
| `stores.py` | `messenger/stores.py` | 352 | ~30% (interfaces + utilities only) |
| `config.py` | `messenger/config.py` | 178 | ~40% (dataclasses + env) |
| `adapters/telegram.py` | `adapters/telegram.py` | 288 | 99% |
| `adapters/slack.py` | `adapters/slack.py` | 318 | 99% |
| `adapters/discord.py` | `adapters/discord.py` | 436 | 99% |
| `adapters/whatsapp.py` | `adapters/whatsapp.py` | 174 | 99% |

### Stays in sophia-pro (Thin Product Layer)

| sophia-pro Module | Responsibility | Est. Lines |
|-------------------|---------------|------------|
| `agent_factory.py` | LiteAgent creation + billing hook | ~80 |
| `prompt_builder.py` | Karis system prompt + skills index | ~150 |
| `memory_provider.py` | Redis + PostgreSQL memory impl | ~500 (existing) |
| `messenger/conversation_factory.py` | Conversation ORM creation | ~80 |
| `messenger/credential_store_impl.py` | MessengerConnection ORM queries | ~120 |
| `messenger/connection_store_impl.py` | MessengerConnection ORM queries | ~150 |
| `messenger/secret_provider.py` | AWS Secrets Manager impl | ~40 |
| `messenger/config_overrides.py` | Karis-specific config/copy | ~30 |
| Tool handlers (brand, email, schedule, social) | Product-specific tools | (existing) |
