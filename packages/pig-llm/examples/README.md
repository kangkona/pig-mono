# Tool Calling Examples

This directory contains examples demonstrating how to use tool calling with pig-llm.

## Quick Start

### Basic Tool Calling

```python
from pig_llm import LLM
import json

# Define a tool
weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA"
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"]
                }
            },
            "required": ["location"]
        }
    }
}

# Initialize LLM
llm = LLM(provider="openai", api_key="your-api-key")

# Make a request with tools
response = llm.complete(
    "What's the weather in San Francisco?",
    tools=[weather_tool]
)

# Check if the model wants to use a tool
if response.tool_calls:
    for tool_call in response.tool_calls:
        function_name = tool_call['function']['name']
        arguments = json.loads(tool_call['function']['arguments'])

        print(f"Tool: {function_name}")
        print(f"Arguments: {arguments}")

        # Execute your function here
        result = get_weather(**arguments)
```

## Supported Providers

All of the following providers support tool calling:

- ✅ **OpenAI** - GPT-4, GPT-3.5
- ✅ **Anthropic** - Claude Opus, Sonnet, Haiku
- ✅ **Google** - Gemini Pro, Flash
- ✅ **Azure OpenAI** - Azure-hosted OpenAI models
- ✅ **OpenRouter** - Access to multiple models
- ✅ **DeepSeek** - DeepSeek models
- ✅ **Groq** - Ultra-fast inference
- ✅ **xAI** - Grok models
- ✅ **Cerebras** - Fastest inference speeds
- ✅ **Perplexity** - Search-augmented LLMs
- ✅ **Together AI** - Open-source models
- ✅ **Custom providers** - Any OpenAI-compatible API

## Examples

### 1. OpenAI

```python
llm = LLM(provider="openai", api_key="sk-...")
response = llm.complete("What's the weather?", tools=[weather_tool])
```

### 2. Anthropic (Claude)

```python
llm = LLM(provider="anthropic", api_key="sk-ant-...")
response = llm.complete("What's the weather?", tools=[weather_tool])
```

### 3. Google (Gemini)

```python
llm = LLM(provider="google", api_key="...")
response = llm.complete("What's the weather?", tools=[weather_tool])
```

### 4. Custom OpenAI-Compatible Provider

```python
llm = LLM(
    provider="my-custom-llm",
    api_key="...",
    base_url="https://api.custom.com/v1"
)
response = llm.complete("What's the weather?", tools=[weather_tool])
```

## Tool Call Format

All providers return tool calls in a unified format:

```python
{
    "id": "call_abc123",           # Unique identifier
    "type": "function",            # Always "function"
    "function": {
        "name": "get_weather",     # Function name
        "arguments": "{...}"       # JSON string of arguments
    }
}
```

## Running the Examples

1. Install pig-llm:
```bash
pip install pig-llm
```

2. Set your API keys:
```bash
export OPENAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
export GOOGLE_API_KEY="your-key"
```

3. Run the examples:
```bash
python examples/tool_calling_examples.py
```

4. Run validation tests:
```bash
python examples/validate_tool_calls.py
```

## Files

- `tool_calling_examples.py` - Complete examples for all providers
- `validate_tool_calls.py` - Validation tests for tool_calls functionality
- `README.md` - This file

## Learn More

- [pig-llm Documentation](https://github.com/kangkona/pig-mono/tree/main/packages/pig-llm)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Anthropic Tool Use](https://docs.anthropic.com/claude/docs/tool-use)
- [Google Function Calling](https://ai.google.dev/docs/function_calling)
