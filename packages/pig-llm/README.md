# pig-llm

[![PyPI version](https://badge.fury.io/py/pig-llm.svg)](https://badge.fury.io/py/pig-llm)
[![Python](https://img.shields.io/pypi/pyversions/pig-llm.svg)](https://pypi.org/project/pig-llm/)

Unified multi-provider LLM API for Python.

## Features

- 🔌 **Multi-provider support**: OpenAI, Anthropic, Google, and more
- 🎯 **Unified interface**: Same API across all providers
- 🔄 **Streaming support**: Real-time token streaming
- 🛡️ **Error handling**: Automatic retries and fallbacks
- 📊 **Usage tracking**: Token counting and cost estimation

## Installation

The base package contains the provider-neutral runtime only:

```bash
pip install pig-llm
```

Install the SDK for the provider family you use:

```bash
pip install "pig-llm[openai]"     # OpenAI and OpenAI-compatible providers
pip install "pig-llm[anthropic]"
pip install "pig-llm[google]"
pip install "pig-llm[groq]"
pip install "pig-llm[mistral]"
pip install "pig-llm[bedrock]"
pip install "pig-llm[cohere]"
pip install "pig-llm[all]"        # All provider SDKs
```

The `openai` extra also covers Azure OpenAI, OpenRouter, xAI, Cerebras,
Perplexity, DeepSeek, and Together because those adapters share the OpenAI SDK.
Selecting a provider without its extra fails with the exact installation command.

Set the provider credential in the host environment, such as
`OPENAI_API_KEY`. Credentials can also be supplied by an embedding host, but
examples avoid placing secret values in source code. Every `LLM` instance
requires an explicit model.

## Quick Start

```python
from pig_llm import LLM

# Reads OPENAI_API_KEY from the environment
llm = LLM(provider="openai", model="gpt-4o-mini")

# Simple completion
response = llm.complete("What is the meaning of life?")
print(response.content)

# Streaming
for chunk in llm.stream("Tell me a story"):
    print(chunk.content, end="", flush=True)

# With system message
response = llm.complete(
    "Translate to Spanish",
    system="You are a helpful translator",
)
```

## Supported Providers

### Core Providers
- **OpenAI** - GPT-4, GPT-3.5, etc.
- **Anthropic** - Claude 3, Claude 2
- **Google** - Gemini Pro, Gemini Ultra
- **Azure OpenAI** - Azure-hosted OpenAI models

### Additional Providers
- **Groq** - Ultra-fast LLM inference
- **Mistral** - Mistral AI models
- **OpenRouter** - Access to multiple models
- **Amazon Bedrock** - AWS-hosted foundation models
- **xAI (Grok)** - xAI's Grok models
- **Cerebras** - Fastest inference speeds
- **Cohere** - Command models for enterprise
- **Perplexity** - Search-augmented LLMs
- **DeepSeek** - Chinese LLM with strong coding
- **Together AI** - Open-source model hosting

## Configuration

```python
from pig_llm import LLM, Config

config = Config(
    provider="openai",
    model="gpt-4o-mini",
    temperature=0.7,
    max_tokens=1000,
    timeout=30,
)

llm = LLM(config=config)
```

## Provider-Specific Examples

Provider model IDs evolve independently of `pig-llm`. The examples below read
the host-selected model ID from environment variables while `pig-llm` resolves
the standard provider credential variable.

### Amazon Bedrock
```python
import os

# Uses AWS credentials from environment
llm = LLM(
    provider="bedrock",
    model=os.environ["BEDROCK_MODEL"],
    api_key=os.getenv("AWS_REGION", "us-east-1"),  # Legacy region field
)
response = llm.complete("Hello")
```

### xAI (Grok)
```python
import os

llm = LLM(provider="xai", model=os.environ["XAI_MODEL"])
response = llm.complete("What's happening?")
```

### Cerebras
```python
import os

llm = LLM(provider="cerebras", model=os.environ["CEREBRAS_MODEL"])
response = llm.complete("Fast inference!")
```

### Cohere
```python
import os

llm = LLM(provider="cohere", model=os.environ["COHERE_MODEL"])
response = llm.complete("Hello")
```

### Perplexity
```python
import os

llm = LLM(provider="perplexity", model=os.environ["PERPLEXITY_MODEL"])
response = llm.complete("What's the latest news?")
# Citations available in response.metadata["citations"]
```

### DeepSeek
```python
import os

llm = LLM(provider="deepseek", model=os.environ["DEEPSEEK_MODEL"])
response = llm.complete("写一段Python代码")
```

### Together AI
```python
import os

llm = LLM(provider="together", model=os.environ["TOGETHER_MODEL"])
response = llm.complete("Hello")
```

## License

MIT
