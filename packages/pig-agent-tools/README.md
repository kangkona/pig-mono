# pig-agent-tools

Tool extensions for pig-agent-core.

## Installation

```bash
# Install base package
pip install pig-agent-tools

# Install with web tools
pip install pig-agent-tools[web]
```

## Available Tools

### Web Tools

#### search_web

Search the web using Tavily API.

**Parameters:**
- `query` (string, required): Search query
- `max_results` (integer, optional): Maximum number of results (default: 5)

**Requirements:**
- `TAVILY_API_KEY` environment variable
- `tavily-python` package (installed with `[web]` extra)

**Example:**
```python
result = await handle_search_web(
    {"query": "Python tutorials", "max_results": 3},
    user_id="user123",
)
# Returns: ToolResult with formatted search results
```

#### read_webpage

Read and extract text content from a webpage.

**Parameters:**
- `url` (string, required): URL of the webpage to read

**Features:**
- Supports HTTP/HTTPS URLs
- Removes navigation, scripts, and styling for clean content
- Automatically truncates content at 10,000 characters
- 30-second timeout for requests

**Requirements:**
- `httpx` and `beautifulsoup4` packages (installed with `[web]` extra)

**Example:**
```python
result = await handle_read_webpage(
    {"url": "https://example.com/article"},
    user_id="user123",
)
# Returns: ToolResult with extracted text content
```

## Usage

### Simple Registration

Register tools with the global registry (recommended):

```python
from pig_agent_tools.web import register_tools

# Register web tools - they'll be available globally
register_tools()
```

### Direct Handler Usage

You can also use the handlers directly without registration:

```python
from pig_agent_tools.web import handle_search_web, handle_read_webpage

# Call handlers directly
result = await handle_search_web(
    {"query": "Python tutorials", "max_results": 5},
    user_id="user123",
    meta={},
)

print(result.data if result.ok else result.error)
```

### Using with Agent

Here's a complete example showing how to use web tools with an Agent:

```python
import asyncio
import os
from pig_agent_core import Agent
from pig_agent_core.tools.registry import ToolRegistry
from pig_llm import LLM
from pig_agent_tools.web import TOOL_SCHEMAS, HANDLERS

# Set up environment
os.environ["TAVILY_API_KEY"] = "your-api-key-here"

# Create registry and register web tools
registry = ToolRegistry()
for schema in TOOL_SCHEMAS:
    tool_name = schema["function"]["name"]
    handler = HANDLERS.get(tool_name)
    if handler:
        registry.register(
            name=tool_name,
            handler=handler,
            schema=schema,
            is_core=False,
            timeout=30.0,
        )

# Create agent with web tools
agent = Agent(
    name="WebAgent",
    llm=LLM(provider="openai"),
    system_prompt="You are a helpful assistant with web search capabilities.",
)
agent.registry = registry

# Use the agent
async def main():
    # Agent can now search the web and read webpages
    response = await agent.respond(
        "Search for recent Python news and summarize the top article"
    )
    print(response.content)

asyncio.run(main())
```

### Advanced: Custom Registry

For advanced use cases, you can register tools with a custom registry:

```python
from pig_agent_core.tools.registry import ToolRegistry
from pig_agent_tools.web import register_tools

# Create custom registry
custom_registry = ToolRegistry()

# Register web tools with custom registry
register_tools(custom_registry)
```

## Creating Custom Tools

You can create your own tools following the same pattern as the built-in web tools.

### Step 1: Define Tool Schema

Create an OpenAI function calling schema:

```python
CUSTOM_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "my_custom_tool",
        "description": "Description of what your tool does",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "Description of param1",
                },
                "param2": {
                    "type": "integer",
                    "description": "Description of param2",
                    "default": 10,
                },
            },
            "required": ["param1"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}
```

### Step 2: Implement Handler

Create an async handler function:

```python
from typing import Any
from pig_agent_core.tools.base import ToolResult

async def handle_my_custom_tool(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: Any = None,
) -> ToolResult:
    """Handle custom tool execution.

    Args:
        args: Tool arguments from LLM
        user_id: Optional user identifier
        meta: Optional metadata
        cancel: Optional cancellation event

    Returns:
        ToolResult with ok=True on success, ok=False on error
    """
    # Extract parameters
    param1 = args.get("param1", "")
    param2 = args.get("param2", 10)

    # Validate parameters
    if not param1:
        return ToolResult(
            ok=False,
            error="param1 is required",
        )

    try:
        # Perform tool operation
        result = f"Processed {param1} with {param2}"

        return ToolResult(
            ok=True,
            data=result,
        )
    except Exception as e:
        return ToolResult(
            ok=False,
            error=f"Tool execution failed: {str(e)}",
        )
```

### Step 3: Register Tool

Register your tool with a ToolRegistry:

```python
from pig_agent_core.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register(
    name="my_custom_tool",
    handler=handle_my_custom_tool,
    schema=CUSTOM_TOOL_SCHEMA,
    is_core=False,
    timeout=30.0,
    max_retries=2,
)
```

### Step 4: Create Package (Optional)

To distribute your tools as a package:

```python
# my_tools/__init__.py
from .handlers import HANDLERS
from .schemas import TOOL_SCHEMAS

def register_tools(registry=None):
    """Register custom tools with a ToolRegistry."""
    if registry is None:
        from pig_agent_core.tools import _global_registry
        registry = _global_registry

    registered = []
    for schema in TOOL_SCHEMAS:
        tool_name = schema["function"]["name"]
        handler = HANDLERS.get(tool_name)
        if handler:
            registry.register(
                name=tool_name,
                handler=handler,
                schema=schema,
                is_core=False,
                timeout=30.0,
            )
            registered.append(tool_name)

    return registered

__all__ = ["register_tools", "HANDLERS", "TOOL_SCHEMAS"]
```

## Best Practices

### Error Handling

Always return `ToolResult` with proper error information:

```python
try:
    result = perform_operation()
    return ToolResult(ok=True, data=result)
except ValueError as e:
    return ToolResult(ok=False, error=f"Invalid input: {e}")
except Exception as e:
    return ToolResult(ok=False, error=f"Unexpected error: {e}")
```

### Parameter Validation

Validate all required parameters before processing:

```python
# Check required parameters
if not args.get("required_param"):
    return ToolResult(ok=False, error="required_param is missing")

# Validate parameter types
try:
    count = int(args.get("count", 10))
except ValueError:
    return ToolResult(ok=False, error="count must be an integer")
```

### Cancellation Support

Check the cancel event for long-running operations:

```python
async def handle_long_operation(args, user_id, meta, cancel):
    for i in range(100):
        # Check if cancelled
        if cancel and cancel.is_set():
            return ToolResult(ok=False, error="Operation cancelled")

        # Do work
        await asyncio.sleep(0.1)

    return ToolResult(ok=True, data="Completed")
```

### Lazy Imports

Import heavy dependencies inside handlers to avoid loading them at package import time:

```python
async def handle_tool(args, user_id, meta, cancel):
    try:
        import heavy_library
    except ImportError:
        return ToolResult(
            ok=False,
            error="heavy_library not installed. Install with: pip install heavy_library",
        )

    # Use the library
    result = heavy_library.process(args)
    return ToolResult(ok=True, data=result)
```

## Development

```bash
# Install in development mode
uv pip install -e .

# Install with all optional dependencies
uv pip install -e ".[web,dev]"

# Run tests
pytest tests/

# Run tests with coverage
pytest tests/ --cov=pig_agent_tools --cov-report=html
```

## License

MIT
