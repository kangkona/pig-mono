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

| Metric | Definition | Target |
|--------|-----------|--------|
| **Task Success Rate** | % of user tasks completed without manual retry | > 90% |
| **Recovery Rate** | % of transient failures (rate limit, timeout, overflow) auto-recovered | > 95% |
| **Time-to-First-Useful-Output** | Time from user message to first meaningful streamed content | < 3s (P95) |
| **Tool Efficiency** | Average tool calls per completed task | Minimize; track per task type |
| **Context Utilization** | % of context window used before compression triggers | 70-80% sweet spot |

---

## 5. User Stories — pig-agent-core

### Phase 1: Core Framework (P0)

#### US-001: Core Agent Framework — Master Loop
**Status: PARTIAL** — basic respond/respond_stream exist but critical integrations missing

**What's done:**
- [x] `respond()` and `respond_stream()` async methods exist
- [x] `_master_loop()` with streaming LLM calls using `pig-llm`
- [x] Tool calling rounds with automatic execution
- [x] Cancellation via `asyncio.Event`
- [x] Backward compatible `run()` / `arun()` still work

**What's missing:**
- [ ] Agent uses **old** `ToolRegistry` (from `registry.py`), not the enhanced one (from `tools/registry.py`) with timeout/retry/lazy-loading
- [ ] `_master_loop()` calls `self.llm.achat_stream` directly — never uses `resilient_streaming_call()` (profile rotation, compression, fallback are dead code)
- [ ] Accept `SystemPromptBuilder` protocol (currently takes raw `system_prompt: str`)
- [ ] Accept `MemoryProvider` protocol (no memory abstraction)
- [ ] Configurable `max_rounds` (has `max_iterations=10`) and `max_rounds_with_plan` (missing)
- [ ] Plan nag every N rounds after plan tool is used
- [ ] 3-level context compression (has single `compress_fn` callback, not the 3-level strategy)

---

#### US-002: Tool System — Base Types and Result Envelope
**Status: PARTIAL** — ToolResult and truncation exist, URL validation missing

**What's done:**
- [x] `tools/base.py` with `ToolResult` dataclass (`ok`, `data`, `error`, `meta`)
- [x] `serialize(max_chars)` with structure-aware truncation
- [x] `_try_shrink()` and multi-strategy data shrinking (S0–S3)
- [x] `CancelledError` exception

**What's missing:**
- [ ] `validate_url()` — blocks private IPs, localhost, metadata endpoints, non-HTTP schemes, DNS rebinding
- [ ] `_fn()` helper exists but lives in `schemas.py`, not in `base.py` (minor placement issue)

---

#### US-003: Tool System — Registry and Execution
**Status: PARTIAL** — enhanced registry exists but missing key features and not wired to Agent

**What's done:**
- [x] `tools/registry.py` with enhanced `ToolRegistry` class
- [x] `register(name, handler, schema)` with timeout/retry config
- [x] `execute(tool_call, user_id, meta, cancel)` with `asyncio.wait_for`
- [x] Lazy loading via `activate_tools()`
- [x] Thread-safe with `threading.RLock`

**What's missing:**
- [ ] **Not wired to Agent** — Agent still uses old `registry.py` ToolRegistry
- [ ] Tool fallback mapping (e.g., `search_x` fails → try `search_web`)
- [ ] Write-tool confirmation gate (`confirmed` flag for write tools)
- [ ] Parallel execution for read-only tools, sequential for write tools
- [ ] Schema/handler/budget consistency validation at registration time

---

#### US-004: Tool System — Core Tool Schemas
**Status: PARTIAL** — 3 core tools exist, missing extras

**What's done:**
- [x] `tools/schemas.py` with `_fn()` builder
- [x] `think`, `plan`, `discover_tools` schemas (OpenAI format, strict mode)
- [x] `CORE_TOOL_NAMES`, `TOOL_PERMISSIONS`, `TOOL_BUDGETS` constants
- [x] `strip_internal_fields()` helper

**What's missing:**
- [ ] `get_current_time` tool schema
- [ ] `DEFERRED_TOOL_INDEX` for keyword-based tool discovery
- [ ] `PARALLEL_SAFE_TOOLS` set for execution strategy

---

#### US-005: Tool System — Core Tool Handlers
**Status: PARTIAL** — 3 handlers exist, missing extras

**What's done:**
- [x] `handlers_core.py` with `handle_think`, `handle_plan`, `handle_discover_tools`
- [x] `HANDLERS` dict with `@_register` decorator pattern
- [x] All handlers async with cancellation support

**What's missing:**
- [ ] `handle_get_current_time` handler

---

#### US-006: Context Management and Compression
**Status: PARTIAL** — basic context exists, no protocols or 3-level compression

**What's done:**
- [x] `CachedContext` dataclass
- [x] `hydrate()` function (simplified stub)
- [x] `build_messages()` function
- [x] `ContextManager` class (file-based AGENTS.md/SYSTEM.md)

**What's missing:**
- [ ] `ContextLoader` protocol (currently concrete class only)
- [ ] `SystemPromptBuilder` protocol
- [ ] 3-level context compression (Level 1: truncate tool results, Level 2: replace I/O with summaries, Level 3: LLM-summarize middle messages)
- [ ] Configurable compression thresholds

---

#### US-007: Token Counter
**Status: TODO** — does not exist

- [ ] Create `pig_agent_core/token_counter.py` with `count_tokens(text, model)`
- [ ] Use `tiktoken` when available, fall back to character-based estimation
- [ ] Cache tokenizer instances per model
- [ ] Unit tests

---

#### US-008: Resilience System — Profile Manager
**Status: PARTIAL** — core rotation works, missing structured error classification

**What's done:**
- [x] `resilience/profile.py` with `APIProfile` dataclass and `ProfileManager` class
- [x] `get_next_profile()` key rotation with cooldown
- [x] `from_env()` environment variable loading
- [x] Fallback models configuration

**What's missing:**
- [ ] `FailoverReason` enum (auth, rate_limit, billing, timeout, context_overflow)
- [ ] `classify_failure()` function (error classification exists as helpers in retry.py but not structured)
- [ ] Per-failure-type cooldown periods (currently single cooldown)
- [ ] Env var naming: currently no `PIG_AGENT_*` aliases with `LITE_AGENT_*` compat

---

#### US-009: Resilience System — Resilient LLM Calls
**Status: PARTIAL** — 3-layer logic exists but missing error types and event integration

**What's done:**
- [x] `resilient_streaming_call()` and `resilient_call()` functions
- [x] Layer 1: Profile rotation on rate_limit/auth/timeout
- [x] Layer 2: Context overflow recovery with `compress_fn`
- [x] Layer 3: Fallback to alternative models
- [x] Error classifiers (`_is_error_type`, `_should_rotate_profile`, `_is_context_overflow`)

**What's missing:**
- [ ] `ResilienceExhaustedError` custom exception (currently raises generic errors)
- [ ] Resilience events emission (`resilience_compact`, `resilience_retry`, `resilience_fallback`) — currently uses `logging` only
- [ ] **Not called by Agent** — `_master_loop()` calls `self.llm.achat_stream` directly

---

#### US-010: Observability — Event System
**Status: PARTIAL** — event system works, missing billing and resilience events

**What's done:**
- [x] `observability/events.py` with `AgentEventType` enum (8 types)
- [x] `AgentEvent` dataclass with `to_dict()`
- [x] `emit()`, `span()` context manager
- [x] `AgentEventCallback` type alias
- [x] Helper functions (emit_agent_start/end, emit_turn_start/end, emit_tool_start/end)

**What's missing:**
- [ ] `BillingHook` protocol (no billing/cost tracking interface)
- [ ] Resilience event types (`PROFILE_ROTATED`, `CONTEXT_COMPRESSED`, `MODEL_FALLBACK`)
- [ ] Agent doesn't actually call emit at execution points (event_callback stored but unused in loop)

---

#### US-011: Tool Audit and Metrics
**Status: TODO** — does not exist

- [ ] Create `pig_agent_core/tools/audit.py`
- [ ] Create `pig_agent_core/tools/metrics.py`
- [ ] Unit tests

---

#### US-012: Memory Protocol and Default Implementation
**Status: TODO** — does not exist

- [ ] Create `pig_agent_core/memory.py` with `MemoryProvider` protocol
- [ ] Implement `InMemoryProvider` default
- [ ] Wire into Agent constructor
- [ ] Unit tests

---

#### US-013: Extension Protocols — Wire Together
**Status: PARTIAL** — subsystem params accepted but not actually used in execution

**What's done:**
- [x] Agent accepts `profile_manager`, `event_callback`, `compress_fn` parameters
- [x] Backward compatible (all optional)

**What's missing:**
- [ ] Accept `MemoryProvider`, `ContextLoader`, `SystemPromptBuilder`, `BillingHook`, `ToolPolicy`
- [ ] Wire Agent to use **enhanced** `ToolRegistry` (from `tools/registry.py`)
- [ ] Wire `_master_loop()` to use `resilient_streaming_call()` instead of direct LLM calls
- [ ] Wire event emission at all execution points
- [ ] Wire `BillingHook` on token usage and tool execution
- [ ] Wire 3-level context compression
- [ ] Export all new subsystems from `__init__.py` (currently not exported)
- [ ] Fix version mismatch: `pyproject.toml` says 0.0.3, `__init__.py` says 0.0.1

---

### Phase 2: Tool Extensions (P1)

#### US-014: Package Structure — pig-agent-tools Foundation
**Status: DONE**

- [x] `packages/pig-agent-tools/` directory structure
- [x] `pyproject.toml` with dependency on pig-agent-core
- [x] `src/pig_agent_tools/__init__.py` with exports
- [x] Package builds with `uv build`

---

#### US-015: Web Tools — Search and Read Webpage
**Status: DONE**

- [x] `web/handlers.py` with `handle_search_web` (Tavily) and `handle_read_webpage` (httpx + BeautifulSoup)
- [x] `web/schemas.py` with OpenAI format schemas
- [x] `HANDLERS` dict
- [x] Unit tests (11 tests, mocked HTTP)

**Note:** URL validation currently inline (checks `http://`/`https://` prefix), does not use `validate_url()` from core (which doesn't exist yet).

---

#### US-016: Tool Registration API
**Status: PARTIAL** — works but uses global singleton pattern

**What's done:**
- [x] `register_tools()` function in `web/__init__.py`
- [x] Integration tests (5 tests)

**What's missing:**
- [ ] Currently defaults to global `_global_registry` singleton — should require explicit `registry` parameter
- [ ] No `registry.register_package()` convenience method

---

## 6. User Stories — pig-messenger

### Phase 3: Messenger Absorption (P0, parallel with Phase 1)

#### US-017: Messenger Base Abstractions
**Status: TODO** — current pig-messenger has simpler `MessagePlatform`/`UniversalMessage`, need to replace with sophia-pro's production abstractions

Current state: `message.py` (62 lines) + `platform.py` (163 lines) = basic models. Missing: `MessengerType` enum, `MessengerCapabilities`, `MessengerThread` with streaming, full `BaseMessengerAdapter` ABC.

- [ ] Replace `message.py` + `platform.py` with new `base.py` (port sophia-pro's 487-line version)
- [ ] Unit tests for MessengerThread streaming logic

---

#### US-018: Messenger Adapter Registry
**Status: TODO** — no registry exists (manual `add_platform()` dict)

- [ ] Create `pig_messenger/registry.py` (port sophia-pro's 72-line version)
- [ ] Unit tests

---

#### US-019: Messenger Distributed State
**Status: TODO** — current pig-messenger is file-based only, no Redis

- [ ] Create `pig_messenger/state.py` (port sophia-pro's 253-line version)
- [ ] Redis client via constructor injection
- [ ] Unit tests with mocked Redis

---

#### US-020: Messenger Manager
**Status: TODO** — current `bot.py` has basic routing only, no locking/queue/drain

- [ ] Create `pig_messenger/manager.py` (port sophia-pro's 469-line version with callback extraction)
- [ ] `AgentFactory` and `ConversationFactory` callbacks
- [ ] `split_message()` standalone utility
- [ ] Unit tests

---

#### US-021: Messenger Store Interfaces
**Status: TODO**

- [ ] Create `pig_messenger/stores.py` with ABCs + TTLCache + encryption utilities
- [ ] Unit tests

---

#### US-022: Messenger Config Dataclasses
**Status: TODO** — current `PlatformConfig` is a 5-line stub

- [ ] Create full config dataclasses with `from_env()` (port sophia-pro's 178-line version)
- [ ] `SecretProvider` protocol
- [ ] Unit tests

---

#### US-023: Platform Adapters — Telegram
**Status: TODO** — current adapter (139 lines, polling mode) needs replacement with sophia-pro's (288 lines, httpx + draft streaming)

- [ ] Replace with sophia-pro's production adapter
- [ ] Unit tests with mocked HTTP

---

#### US-024: Platform Adapters — Slack
**Status: TODO** — current adapter (259 lines, Socket Mode) needs enhancement with sophia-pro's features (318 lines, markdown→mrkdwn, blocks, per-workspace clients)

- [ ] Replace/enhance with sophia-pro's production adapter
- [ ] Unit tests with mocked Slack API

---

#### US-025: Platform Adapters — Discord
**Status: TODO** — current adapter (168 lines) needs replacement with sophia-pro's (436 lines, Gateway + embeds)

- [ ] Replace with sophia-pro's production adapter
- [ ] Unit tests with mocked Discord API

---

#### US-026: Platform Adapters — WhatsApp
**Status: TODO** — current adapter (288 lines) needs alignment with sophia-pro's Twilio-based version (174 lines, E.164, signature verification)

- [ ] Replace/merge with sophia-pro's production adapter
- [ ] Unit tests with mocked Twilio API

---

### Phase 4: Documentation, Examples, Testing (P1)

#### US-027: Documentation — Core Package README
**Status: PARTIAL** — README exists with v0.1.0 content, but needs update for extension protocols

**What's done:**
- [x] Quick Start, Architecture, API Reference, Migration Guide

**What's missing:**
- [ ] Extension Protocols section (MemoryProvider, ContextLoader, BillingHook, SystemPromptBuilder, ToolPolicy)
- [ ] Update to reflect actual wired-up features

---

#### US-028: Documentation — Messenger Package README
**Status: TODO** — existing README covers old simpler API

- [ ] Full rewrite for v0.1.0 features

---

#### US-029: Documentation — Tools Package README
**Status: DONE**

- [x] Installation, Available Tools, Creating Custom Tools, Best Practices sections

---

#### US-030: Examples
**Status: PARTIAL**

**What's done:**
- [x] `pig-agent-core/examples/basic_agent.py` with 4 examples
- [x] `pig-agent-tools/examples/web_agent.py` with 4 examples

**What's missing:**
- [ ] `pig-agent-core/examples/custom_extensions.py` — Agent with custom MemoryProvider and BillingHook
- [ ] `pig-messenger/examples/telegram_bot.py` — Telegram bot with streaming

---

#### US-031: Testing — Core Package
**Status: PARTIAL** — tests exist for implemented features, need tests for new features

**What's done:**
- [x] 95+ tests passing across agent, tools, resilience, observability, context
- [x] Sophia compat test (9 tests)

**What's missing:**
- [ ] Tests for 3-level context compression
- [ ] Tests for token counter
- [ ] Tests for audit and metrics
- [ ] Tests for extension protocols (MemoryProvider, BillingHook, etc.)
- [ ] Tests for tool fallback, confirmation gate, parallel/sequential execution

---

#### US-032: Testing — Messenger Package
**Status: TODO**

- [ ] All messenger tests need to be written

---

#### US-033: Testing — Tools Package
**Status: DONE**

- [x] 16/18 tests pass (91% coverage)

---

#### US-034: Integration — sophia-pro Migration Validation
**Status: PARTIAL**

**What's done:**
- [x] `test_sophia_compat.py` with 9 tests (agent patterns)

**What's missing:**
- [ ] `test_messenger_compat.py` (messenger patterns)
- [ ] Tests need update to validate wired-up integration (currently tests subsystems in isolation)

---

## 7. Implementation Status Summary

### pig-agent-core

| US | Title | Status | Key Blocker |
|----|-------|--------|-------------|
| 001 | Master Loop | **PARTIAL** | Agent doesn't use enhanced registry or resilient calls |
| 002 | ToolResult | **PARTIAL** | Missing `validate_url()` |
| 003 | Registry | **PARTIAL** | Not wired to Agent; missing fallback/gate/parallel |
| 004 | Schemas | **PARTIAL** | Missing `get_current_time`, `DEFERRED_TOOL_INDEX` |
| 005 | Handlers | **PARTIAL** | Missing `get_current_time` handler |
| 006 | Context | **PARTIAL** | No protocols, no 3-level compression |
| 007 | Token Counter | **TODO** | Does not exist |
| 008 | Profile Manager | **PARTIAL** | Missing `FailoverReason`, `classify_failure()` |
| 009 | Resilient Calls | **PARTIAL** | Missing `ResilienceExhaustedError`, events; not called by Agent |
| 010 | Observability | **PARTIAL** | Missing `BillingHook`, resilience events |
| 011 | Audit & Metrics | **TODO** | Does not exist |
| 012 | Memory Protocol | **TODO** | Does not exist |
| 013 | Wire Together | **PARTIAL** | Params accepted but not used in execution path |

### pig-agent-tools

| US | Title | Status |
|----|-------|--------|
| 014 | Package Structure | **DONE** |
| 015 | Web Tools | **DONE** |
| 016 | Registration API | **PARTIAL** (global singleton, needs explicit param) |

### pig-messenger

| US | Title | Status |
|----|-------|--------|
| 017 | Base Abstractions | **TODO** |
| 018 | Adapter Registry | **TODO** |
| 019 | Distributed State | **TODO** |
| 020 | Manager | **TODO** |
| 021 | Store Interfaces | **TODO** |
| 022 | Config Dataclasses | **TODO** |
| 023 | Telegram Adapter | **TODO** |
| 024 | Slack Adapter | **TODO** |
| 025 | Discord Adapter | **TODO** |
| 026 | WhatsApp Adapter | **TODO** |

### Documentation & Testing

| US | Title | Status |
|----|-------|--------|
| 027 | Core README | **PARTIAL** |
| 028 | Messenger README | **TODO** |
| 029 | Tools README | **DONE** |
| 030 | Examples | **PARTIAL** |
| 031 | Core Tests | **PARTIAL** |
| 032 | Messenger Tests | **TODO** |
| 033 | Tools Tests | **DONE** |
| 034 | Migration Validation | **PARTIAL** |

### Critical Wiring Gap

The single most important issue: **subsystems are built in isolation but never connected.** The enhanced `ToolRegistry`, `resilient_streaming_call`, event emission, and `compress_fn` all exist as standalone code, but the `Agent._master_loop()` never calls them. This means the entire resilience, observability, and enhanced tool execution path is dead code from the Agent's perspective. US-013 (Wire Together) is the critical path blocker.

---

## 8. Functional Requirements

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

## 9. Non-Goals

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

## 10. Technical Considerations

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

## 11. Success Metrics

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

## 12. Recommended Execution Order

Based on actual implementation state, the most impactful next steps are:

### Sprint 1: Fix the Wiring Gap (highest priority)
1. **US-007** Token Counter — prerequisite for compression
2. **US-012** Memory Protocol — prerequisite for proper agent loop
3. **US-006** Context Compression — implement 3-level strategy
4. **US-013** Wire Together — connect all subsystems into Agent's master loop

### Sprint 2: Complete Core Gaps
5. **US-002** Add `validate_url()` to tools/base.py
6. **US-003** Add fallback mapping, confirmation gate, parallel/sequential to registry
7. **US-004/005** Add `get_current_time`, `DEFERRED_TOOL_INDEX`, `PARALLEL_SAFE_TOOLS`
8. **US-008** Add `FailoverReason`, `classify_failure()`
9. **US-009** Add `ResilienceExhaustedError`, resilience events
10. **US-010** Add `BillingHook`, resilience event types
11. **US-011** Tool Audit & Metrics

### Sprint 3: Messenger Absorption (can start in parallel with Sprint 1)
12. **US-017** Base Abstractions
13. **US-018** Adapter Registry
14. **US-019** Distributed State
15. **US-020** Manager
16. **US-021–022** Stores + Config
17. **US-023–026** Adapters (Telegram, Slack, Discord, WhatsApp)

### Sprint 4: Polish
18. **US-016** Fix registration to explicit parameter
19. **US-027–034** Documentation, examples, tests, migration validation

---

## 13. Timeline Estimate

**Sprint 1: Fix Wiring (US-007, 012, 006, 013)** — 1.5 weeks
**Sprint 2: Complete Core (US-002–011 gaps)** — 1.5 weeks
**Sprint 3: Messenger Absorption (US-017–026)** — 3 weeks (parallel with Sprint 1+2)
**Sprint 4: Polish (US-016, 027–034)** — 1.5 weeks

**Total: 7.5 weeks** (Sprints 1+2 and Sprint 3 run in parallel → critical path is ~4.5 weeks + 1.5 weeks polish = **6 weeks**)

---

## 14. Future Iterations

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
