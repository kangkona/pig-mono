# py-mono

> **Python Monorepo for AI Agents** - A comprehensive toolkit inspired by [pi-mono](https://github.com/badlogic/pi-mono)
> 
> *Also playfully known as "**pig-mono**" (🐷) - 虾仁猪心 (a Chinese pun meaning "utterly devastating"), our tribute to pi-mono while bringing these excellent ideas to the Python ecosystem*

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Test Coverage](https://img.shields.io/badge/coverage-84%25-green.svg)](TESTING.md)

Build AI agents and LLM applications with a powerful, modular Python toolkit. py-mono provides everything you need: unified LLM APIs, agent runtime, session management, extensions, skills, and multi-platform messaging bots.

**🌟 Unique Features:**
- **Multi-Platform Bots**: Support for Slack, Discord, Telegram, WhatsApp, and Feishu (vs pi-mono's Slack-only)
- **14 LLM Providers**: OpenAI, Anthropic, Google, Azure, Groq, Mistral, and more
- **Complete Agent System**: Sessions, extensions, skills, prompts, and context management
- **Production Ready**: 99.5%+ feature parity with pi-mono, 84% test coverage

---

## 📦 Packages

| Package | Description | Status |
|---------|-------------|--------|
| **[py-mono-ai](packages/py-ai)** | Unified LLM API for 14 providers | ✅ Ready |
| **[py-mono-agent-core](packages/py-agent-core)** | Agent runtime with tools, sessions, extensions | ✅ Ready |
| **[py-mono-tui](packages/py-tui)** | Terminal UI with rich formatting | ✅ Ready |
| **[py-mono-web-ui](packages/py-web-ui)** | Web chat interface with FastAPI | ✅ Ready |
| **[py-mono-coding-agent](packages/py-coding-agent)** | Interactive coding assistant CLI | ✅ Ready |
| **[py-mono-messenger](packages/py-messenger)** | Multi-platform bot framework | ✅ Ready |

---

## 🚀 Quick Start

### Installation

Install individual packages from PyPI:

```bash
# Using uv (recommended)
uv pip install py-mono-ai py-mono-agent-core py-mono-coding-agent

# Using pipx (for CLI tools)
pipx install py-mono-coding-agent

# Using pip
pip install py-mono-ai py-mono-agent-core
```

For development from source:

```bash
git clone https://github.com/kangkona/py-mono.git
cd py-mono
uv pip install -e ".[dev]"
./scripts/install-dev.sh
```

### Try it Out

**Web UI** (easiest):
```bash
# OpenRouter gives you access to 100+ models with one API key
export OPENROUTER_API_KEY=your-key
py-webui --provider openrouter --model moonshotai/kimi-k2.5
# Open http://localhost:8000
```

**Coding Agent** (powerful):
```bash
export OPENROUTER_API_KEY=your-key
py-code --provider openrouter --model moonshotai/kimi-k2.5

# Try these features:
> Review @src/main.py for bugs          # @file references
> /tree                                   # View session tree
> /fork alternative-approach              # Branch conversation
> /skill:code-review                      # Invoke skill
!Stop and explain what you're doing      # Interrupt with steering
```

**Multi-Platform Bot** ([setup guide](packages/py-messenger/README.md)):
```python
import os
from py_mono_messenger import MessengerBot
from py_mono_messenger.adapters import SlackAdapter
from py_mono_agent_core import Agent
from py_mono_ai import LLM

agent = Agent(llm=LLM(provider="openrouter", model="moonshotai/kimi-k2.5",
                       api_key=os.environ["OPENROUTER_API_KEY"]))
bot = MessengerBot(agent)
bot.add_platform(SlackAdapter(
    app_token=os.environ["SLACK_APP_TOKEN"],
    bot_token=os.environ["SLACK_BOT_TOKEN"],
))
bot.start()
```

---

## ✨ Key Features

### 14 LLM Providers
- **Major**: OpenAI, Anthropic (Claude), Google (Gemini), Azure
- **Fast**: Groq, Cerebras, Together AI
- **Specialized**: Mistral, Cohere, DeepSeek, Perplexity
- **Aggregators**: OpenRouter, Amazon Bedrock, xAI

### Complete Agent System
- **Sessions**: Tree-based conversation management with branching and forking
- **Extensions**: Plugin system for custom tools, commands, and events
- **Skills**: Reusable agent capabilities (Agent Skills standard)
- **Prompts**: Template system with variable substitution
- **Context**: Project-aware via AGENTS.md and SYSTEM.md

### Multi-Platform Messaging
- **5 Platforms**: Slack, Discord, Telegram, WhatsApp, Feishu
- **Unified API**: Same agent code works everywhere
- **Per-Channel Sessions**: Each conversation maintains its own context

### Developer Experience
- **30+ Commands**: Comprehensive CLI control
- **Message Queue**: Queue messages while agent works (!steering, >>followup)
- **File References**: Auto-include files with @filename syntax
- **Export/Share**: Export sessions to HTML or GitHub Gist
- **JSON/RPC Modes**: Programmatic integration

---

## 📖 Documentation

- **[Quick Start](QUICKSTART.md)** - Get started in 5 minutes
- **[Messenger Bot](packages/py-messenger/README.md)** - Slack/Discord/Telegram bot setup
- **[Testing Guide](TESTING.md)** - How to run and write tests
- **[Contributing](CONTRIBUTING.md)** - Contribution guidelines

---

## 🎯 Use Cases

### Code Development
```bash
py-code --session my-project

> Create a FastAPI web server with authentication
> @src/main.py - Review this code
> /fork add-tests
> Commit changes with message "Add auth"
```

### Team Collaboration
```python
# Same bot across Slack, Discord, Telegram
bot = MessengerBot(agent)
bot.add_platform(SlackAdapter(...))
bot.add_platform(DiscordAdapter(...))
bot.start()
```

### Automation
```bash
# Use OpenRouter for cost-effective automation
export OPENROUTER_API_KEY=your-key

# JSON mode for CI/CD
echo '{"message": "Review this code"}' | py-code --provider openrouter --mode json

# RPC mode for integration
py-code --provider openrouter --mode rpc < requests.jsonl > responses.jsonl
```

### Why OpenRouter?

- **100+ Models**: Access OpenAI, Anthropic, Google, Meta, and more with one API key
- **Cost Effective**: Pay only for what you use, often cheaper than direct APIs
- **No Rate Limits**: Higher throughput than individual providers
- **Easy Switching**: Try different models without managing multiple keys

Get your key at: https://openrouter.ai

---

## 📊 Project Stats

- **Code**: 14,000+ lines
- **Tests**: 300+ tests with 84% coverage
- **Documentation**: 55,000+ words
- **Commits**: 32 well-structured commits
- **Packages**: 6 production-ready packages

---

## 🆚 vs pi-mono

| Feature | pi-mono | py-mono |
|---------|---------|---------|
| **Core Development** | ✅ | ✅ 99.5%+ |
| **LLM Providers** | 17 | 14 (all major ones) |
| **Messaging Platforms** | 1 (Slack) | **5 (Slack, Discord, Telegram, WhatsApp, Feishu)** 🌟 |
| **Test Coverage** | ~80% | **84%** |
| **Documentation** | Excellent | **More comprehensive** |
| **Language** | TypeScript | Python |

**py-mono achieves 99.5%+ feature parity with pi-mono and exceeds it in multi-platform support!**

---

## 🏗️ Architecture

```
Infrastructure Layer
├── py-mono-ai (LLM abstraction)
├── py-mono-agent-core (Agent runtime)
├── py-mono-tui (Terminal UI)
└── py-mono-web-ui (Web UI)

Application Layer
├── py-mono-coding-agent (CLI assistant)
└── py-mono-messenger (Multi-platform bots)
```

---

## 🛠️ Development

```bash
# Install dependencies
uv pip install -e ".[dev]"
./scripts/install-dev.sh

# Run tests
./scripts/test.sh

# Lint code
./scripts/lint.sh

# Run coding agent from source
cd packages/py-coding-agent
python -m py_coding_agent.cli
```

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Testing requirements
- Pull request process

---

## 📝 License

MIT License - see [LICENSE](LICENSE) for details

---

## 🙏 Acknowledgments

Inspired by [badlogic/pi-mono](https://github.com/badlogic/pi-mono) - an excellent TypeScript AI agent toolkit.

py-mono (affectionately called "pig-mono" 🐷 by the community) brings these concepts to the Python ecosystem with additional innovations like multi-platform messaging support.

### Why "pig-mono"?

It's a playful Chinese pun: "虾仁猪心" (xiā rén zhū xīn), which sounds like "杀人诛心" (shā rén zhū xīn) - meaning to utterly defeat someone not just physically but mentally. 

Our tribute to pi-mono: We aim to match it feature-for-feature while adding unique Python-ecosystem value! 🐷💪

---

## ⭐ Star History

If you find py-mono useful, please star the repository!

[![Star History Chart](https://api.star-history.com/svg?repos=kangkona/py-mono&type=Date)](https://star-history.com/#kangkona/py-mono&Date)

---

**Built with ❤️ for the Python AI community**
