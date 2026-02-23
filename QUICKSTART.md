# Quick Start Guide

Get started with py-mono in 5 minutes!

## Prerequisites

- Python 3.10 or higher
- pip
- OpenRouter API key (recommended) or any LLM provider API key
- (Optional) virtualenv or conda

### Get OpenRouter API Key (Recommended)

OpenRouter gives you access to 100+ models with one API key:

1. Visit https://openrouter.ai
2. Sign up and get your API key
3. You can now use OpenAI, Anthropic, Google, Meta models and more!

**Why OpenRouter?**
- One API key for all models
- Often cheaper than direct APIs
- No rate limits
- Easy model switching

## Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd py-mono
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
# Install development dependencies
pip install -e ".[dev]"

# Install all packages in editable mode
./scripts/install-dev.sh
```

## First Steps

### Using py-ai

Create a file `test.py`:

```python
from py_ai import LLM
import os

# Initialize with OpenRouter (recommended)
llm = LLM(
    provider="openrouter",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model="openai/gpt-4o-mini"  # or any model on OpenRouter
)

# Or use OpenAI directly
# llm = LLM(
#     provider="openai",
#     api_key=os.getenv("OPENAI_API_KEY"),
#     model="gpt-3.5-turbo"
# )

# Simple completion
response = llm.complete("What is the capital of France?")
print(response.content)

# Streaming
print("\nStreaming example:")
for chunk in llm.stream("Tell me a short joke"):
    print(chunk.content, end="", flush=True)
print()
```

Run it:

```bash
export OPENROUTER_API_KEY="your-openrouter-key"
python test.py

# Available models on OpenRouter:
# - openai/gpt-4o
# - anthropic/claude-3.5-sonnet
# - google/gemini-pro
# - meta-llama/llama-3.1-70b
# - And 100+ more!
```

### Running Tests

```bash
# Run all tests
./scripts/test.sh

# Run specific test
pytest tests/test_py_ai.py -v

# Run with coverage
pytest --cov=packages --cov-report=html
open htmlcov/index.html
```

### Code Quality

```bash
# Format code
ruff format packages/

# Check linting
ruff check packages/

# Type check
mypy packages/
```

## Examples

Check the `examples/` directory for more:

- `basic_usage.py` - Basic LLM usage
- More examples coming soon!

## Project Structure

```
py-mono/
├── packages/
│   ├── py-ai/              # ✅ Ready to use
│   ├── py-agent-core/      # 🚧 Coming soon
│   ├── py-coding-agent/    # 🚧 Coming soon
│   ├── py-tui/             # 🚧 Coming soon
│   └── py-web-ui/          # 🚧 Coming soon
├── examples/               # Usage examples
├── tests/                  # Tests
└── scripts/                # Utility scripts
```

## Next Steps

1. **Read the docs**: Check out [ARCHITECTURE.md](ARCHITECTURE.md)
2. **Try examples**: Run examples in `examples/`
3. **Explore packages**: Look at individual package READMEs
4. **Contribute**: See [CONTRIBUTING.md](CONTRIBUTING.md)

## Common Issues

### Import Error

If you get import errors:
```bash
# Make sure packages are installed
./scripts/install-dev.sh
```

### API Key Not Found

Set your API keys as environment variables:
```bash
export OPENAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
```

Or use a `.env` file (not committed):
```bash
echo "OPENAI_API_KEY=your-key" > .env
# Then load it in your code
```

## Getting Help

- 📚 Read the [README](README.md)
- 🏗️ Check [ARCHITECTURE.md](ARCHITECTURE.md)
- 💬 Open an issue on GitHub
- 🤝 See [CONTRIBUTING.md](CONTRIBUTING.md)

Happy coding! 🚀
