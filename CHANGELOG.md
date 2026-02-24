# Changelog

All notable changes to pig-mono will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
