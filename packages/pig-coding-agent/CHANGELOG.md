# Changelog

All notable changes to pig-coding-agent will be documented in this file.

## [0.0.4] - 2026-03-04

### Added

- **Resilience Support**: Automatic API key rotation and fallback
  - Multi-key support via environment variables (OPENAI_API_KEY, OPENAI_API_KEY_2, etc.)
  - Automatic rotation on rate limits and failures
  - Per-failure-type cooldowns (AUTH=5min, RATE_LIMIT=1min, BILLING=1hr, etc.)
  - Model fallback on context overflow
  - `/resilience` command to view status

- **Cost Tracking**: Comprehensive usage and cost monitoring
  - Automatic tracking of LLM calls (tokens, cost)
  - Tool usage tracking
  - Per-model and per-tool statistics
  - Usage data persistence to `.agents/usage.json`
  - `/cost` and `/usage` commands to view summary

- **New Configuration Options**:
  - `enable_resilience` (default: True)
  - `enable_cost_tracking` (default: True)
  - `--no-resilience` CLI flag
  - `--no-cost-tracking` CLI flag

### Changed

- Updated dependency to `pig-agent-core>=0.0.4` for enhanced features
- Agent now passes `profile_manager` and `billing_hook` to core Agent

### Technical Details

**Resilience Implementation** (`resilience.py`):
- `create_profile_manager_from_env()`: Auto-discovers API keys from environment
- `get_profile_status()`: Returns status of all profiles (available/cooldown)
- Supports OpenAI, Anthropic, and Google providers
- Configurable fallback models

**Cost Tracking Implementation** (`billing.py`):
- `CostTracker`: Tracks LLM and tool usage
- Pricing data for major models (GPT-4, Claude, Gemini)
- Automatic cost calculation based on token usage
- Persistent storage with JSON format
- Summary formatting and filtering by user

**Integration**:
- `CodingAgent.__init__()` now accepts `enable_resilience` and `enable_cost_tracking`
- Automatic initialization from environment variables
- Seamless integration with pig-agent-core v0.0.4 protocols

### Tests

- Added `tests/test_resilience.py` (11 tests)
- Added `tests/test_billing.py` (14 tests)
- All tests cover core functionality and edge cases

## [0.0.3] - Previous Release

- Initial release with basic coding agent functionality
- File operations, code generation, shell integration
- Session management, extensions, skills support
