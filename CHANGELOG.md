# Changelog

All notable changes to pig-mono will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.4] - 2026-03-04

### Agent Middlewares Enhancement

Major upgrade adding production-ready resilience and observability features.

#### pig-agent-core v0.0.4

**Added:**
- **Resilience System**: API key rotation with per-failure-type cooldowns
  - ProfileManager for managing multiple API profiles
  - Per-failure-type cooldown periods (AUTH=5min, RATE_LIMIT=1min, BILLING=1hr, etc.)
  - resilient_call() and resilient_streaming_call() with automatic retry

- **Observability System**: Event emission and metrics collection
  - AgentEvent and AgentEventType for structured event tracking
  - BillingHook protocol for cost tracking
  - Tool audit logging with execution metrics

- **Context Management**: 3-level compression strategy
  - Token counting with tiktoken and character-based fallback
  - Automatic context overflow detection and handling

- **Memory Protocols**: Pluggable storage backends
  - MemoryProvider protocol for custom implementations

- **Enhanced Tool System**:
  - Tool fallback mapping, confirmation gates
  - Parallel vs sequential execution strategies
  - URL validation for SSRF protection

**Tests:** 330+ new tests covering all subsystems

#### pig-coding-agent v0.0.4

**Added:**
- **Resilience Support**: Automatic API key rotation
  - Multi-key support via environment variables
  - /resilience command to view status

- **Cost Tracking**: Usage and cost monitoring
  - Automatic LLM call tracking (tokens, cost)
  - Tool usage tracking with statistics
  - /cost and /usage commands

- **Documentation**: CHANGELOG.md, UPGRADE.md

**Tests:** 25 new tests (11 resilience + 14 billing)

#### pig-messenger v0.0.2

**Changed:**
- Updated to use pig-agent-core v0.0.4 features
- Now benefits from automatic API key rotation and cost tracking

### Added
- Initial release of pig-mono
- 6 core packages: pig-llm, pig-agent-core, pig-tui, pig-web-ui, pig-coding-agent, pig-messenger
- 14 LLM providers: OpenAI, Anthropic, Google, Azure, Groq, Mistral, OpenRouter, Bedrock, xAI, Cerebras, Cohere, Perplexity, DeepSeek, Together AI
- Multi-platform bot support: Slack, Discord, Telegram, WhatsApp, Feishu
- Session management with tree structure, branching, and forking
- Extension system for custom tools and commands
- Skills library (Agent Skills standard)
- Prompt templates with variable substitution
- Context management (AGENTS.md, SYSTEM.md)
- Message queue (steering and follow-up messages)
- File reference system (@filename auto-include)
- Export sessions to HTML
- Share sessions via GitHub Gist
- JSON and RPC output modes
- OAuth authentication framework
- 300+ tests with 84% coverage
- Comprehensive documentation (55,000+ words)

## [0.0.1] - 2026-02-23

### Initial Release

First public release of pig-mono - a comprehensive Python toolkit for building AI agents.

#### Features
- **pig-llm**: Unified LLM API supporting 14 providers
- **pig-agent-core**: Complete agent runtime with sessions, extensions, and skills
- **pig-tui**: Rich terminal UI components
- **pig-web-ui**: Modern web chat interface
- **pig-coding-agent**: Interactive coding assistant
- **pig-messenger**: Universal multi-platform bot framework

#### Highlights
- 99.5%+ feature parity with pi-mono
- Multi-platform messaging (5 platforms vs pi-mono's 1)
- Production-ready with extensive testing
- Well-documented with examples

#### Known Issues
- Some providers require API keys not included in tests
- OAuth login requires manual provider configuration
- Differential rendering not implemented in TUI

---

## Development

To see what's planned for future releases, check:
- GitHub Issues
- Project boards
- Community discussions
