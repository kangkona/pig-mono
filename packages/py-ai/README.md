# py-ai

Unified multi-provider LLM API for Python.

## Features

- 🔌 **Multi-provider support**: OpenAI, Anthropic, Google, and more
- 🎯 **Unified interface**: Same API across all providers
- 🔄 **Streaming support**: Real-time token streaming
- 🛡️ **Error handling**: Automatic retries and fallbacks
- 📊 **Usage tracking**: Token counting and cost estimation

## Installation

```bash
pip install py-ai
```

## Quick Start

```python
from py_ai import LLM

# Initialize with API key
llm = LLM(provider="openai", api_key="sk-...")

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
from py_ai import LLM, Config

config = Config(
    provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_tokens=1000,
    timeout=30,
)

llm = LLM(config=config)
```

## Provider-Specific Examples

### Amazon Bedrock
```python
# Uses AWS credentials from environment
llm = LLM(provider="bedrock", api_key="us-east-1")  # region as api_key
response = llm.complete("Hello", model="anthropic.claude-3-sonnet-20240229-v1:0")
```

### xAI (Grok)
```python
llm = LLM(provider="xai", api_key="xai-...")
response = llm.complete("What's happening?", model="grok-beta")
```

### Cerebras
```python
llm = LLM(provider="cerebras", api_key="csk-...")
response = llm.complete("Fast inference!", model="llama3.1-8b")
```

### Cohere
```python
llm = LLM(provider="cohere", api_key="...")
response = llm.complete("Hello", model="command-r-plus")
```

### Perplexity
```python
llm = LLM(provider="perplexity", api_key="pplx-...")
response = llm.complete("What's the latest news?", model="llama-3.1-sonar-large-128k-online")
# Citations available in response.metadata["citations"]
```

### DeepSeek
```python
llm = LLM(provider="deepseek", api_key="...")
response = llm.complete("写一段Python代码", model="deepseek-chat")
```

### Together AI
```python
llm = LLM(provider="together", api_key="...")
response = llm.complete("Hello", model="meta-llama/Llama-3-70b-chat-hf")
```

## License

MIT
