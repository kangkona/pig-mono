# pig-agent-core

Agent runtime with tool calling and state management.

## Features

- 🤖 **Agent Runtime**: Base agent class with lifecycle management
- 🔧 **Tool System**: Decorator-based tool registration
- 💾 **State Management**: Conversation history and context
- 🔄 **Async Support**: Full async/await support
- 📝 **Message History**: Automatic conversation tracking
- 🎯 **Tool Execution**: Safe tool calling with validation

## Installation

```bash
pip install pig-agent-core
```

## Quick Start

### Define Tools

```python
from pig_agent_core import Agent, tool

@tool(description="Get current weather for a location")
def get_weather(location: str) -> str:
    """Get weather information."""
    return f"Weather in {location}: Sunny, 72°F"

@tool(description="Calculate result of mathematical expression")
def calculate(expression: str) -> float:
    """Safely evaluate math expression."""
    return eval(expression)  # In production, use ast.literal_eval
```

### Create and Run Agent

```python
from pig_llm import LLM

# Create agent with tools
agent = Agent(
    name="WeatherBot",
    llm=LLM(provider="openai"),
    tools=[get_weather, calculate],
    system_prompt="You are a helpful weather assistant."
)

# Run agent
response = agent.run("What's the weather in Paris?")
print(response.content)

# Agent automatically:
# 1. Receives user message
# 2. Calls get_weather("Paris") if needed
# 3. Returns formatted response
```

### Conversation with History

```python
# Multi-turn conversation
agent.run("What's the weather in Tokyo?")
agent.run("What about New York?")
agent.run("Which one is warmer?")

# View history
for msg in agent.history:
    print(f"{msg.role}: {msg.content}")
```

### Async Usage

```python
import asyncio

async def main():
    response = await agent.arun("Check weather in London")
    print(response.content)

asyncio.run(main())
```

## Advanced Usage

### Custom Tool Parameters

```python
from pydantic import BaseModel, Field

class WeatherParams(BaseModel):
    location: str = Field(description="City name")
    units: str = Field(default="fahrenheit", description="Temperature units")

@tool(params_model=WeatherParams)
def get_weather_detailed(location: str, units: str = "fahrenheit") -> str:
    """Get detailed weather with custom units."""
    temp = 72 if units == "fahrenheit" else 22
    return f"Weather in {location}: Sunny, {temp}°{units[0].upper()}"
```

### State Management

```python
# Save and restore state
state = agent.get_state()
agent.save_state("conversation.json")

# Later...
agent = Agent.from_state("conversation.json")
agent.run("Continue our conversation")
```

### Tool Callbacks

```python
def on_tool_start(tool_name: str, args: dict):
    print(f"Starting {tool_name} with {args}")

def on_tool_end(tool_name: str, result: any):
    print(f"Finished {tool_name}: {result}")

agent = Agent(
    llm=llm,
    tools=[get_weather],
    on_tool_start=on_tool_start,
    on_tool_end=on_tool_end,
)
```

## Architecture

```
Agent
├── LLM Client (pig-llm)
├── Tool Registry
├── Message History
├── State Manager
└── Execution Loop
```

## Tool System

Tools are Python functions decorated with `@tool`:

```python
@tool(
    name="custom_name",           # Optional: defaults to function name
    description="What it does",   # Required for LLM understanding
    params_model=ParamsModel,     # Optional: Pydantic model for params
)
def my_tool(arg1: str, arg2: int = 10) -> str:
    """Function that the agent can call."""
    return f"Result: {arg1} * {arg2}"
```

The tool decorator:
- Validates parameters using type hints or Pydantic models
- Generates JSON schema for LLM function calling
- Handles execution and error catching
- Tracks usage statistics

## Examples

See `examples/` directory:
- `basic_agent.py` - Simple agent usage
- `tools_demo.py` - Tool system demonstration
- `async_agent.py` - Async agent example
- `stateful_agent.py` - State management

## License

MIT
