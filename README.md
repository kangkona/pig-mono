# Py-Mono

> Python monorepo toolkit for AI agents and LLM applications

Python equivalent of [pi-mono](https://github.com/badlogic/pi-mono), providing tools for building AI agents and managing LLM deployments.

## Packages

| Package | Status | Description |
|---------|--------|-------------|
| **[py-ai](packages/py-ai)** | ✅ Ready | Unified multi-provider LLM API (OpenAI, Anthropic, Google, etc.) |
| **[py-agent-core](packages/py-agent-core)** | ✅ Ready | Agent runtime with tool calling and state management |
| **[py-coding-agent](packages/py-coding-agent)** | ✅ Ready | Interactive coding agent CLI |
| **[py-tui](packages/py-tui)** | ✅ Ready | Terminal UI library with rich formatting |
| **[py-web-ui](packages/py-web-ui)** | ✅ Ready | Web UI components with FastAPI backend |

## Installation

```bash
# Install from source
git clone <repo-url>
cd py-mono
pip install -e .

# Or install specific package
pip install -e packages/py-ai
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Install all packages in editable mode
./scripts/install-dev.sh

# Run tests
pytest

# Run linting and formatting
ruff check .
ruff format .

# Type checking
mypy packages/
```

## Project Structure

```
py-mono/
├── packages/
│   ├── py-ai/              # LLM API wrapper
│   ├── py-agent-core/      # Agent runtime
│   ├── py-coding-agent/    # Coding agent CLI
│   ├── py-tui/             # Terminal UI
│   └── py-web-ui/          # Web UI components
├── scripts/                # Build and utility scripts
├── tests/                  # Integration tests
├── pyproject.toml          # Project configuration
└── README.md
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

MIT
