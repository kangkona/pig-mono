# pig-agent-core

Production-ready agent framework with tool calling, resilience, and observability.

## Features

- 🤖 **Master Loop**: Async agent runtime with resilient LLM calls and automatic tool execution
- 🔧 **Enhanced Tool System**: Handler-based tools with fallback mapping, confirmation gates, and parallel/sequential execution
- 🛡️ **Resilience**: API key rotation with per-failure-type cooldowns, retry logic, and fallback models
- 📊 **Observability**: Event emission, billing hooks, tool audit logging, and performance metrics
- 💾 **Memory Protocols**: Pluggable conversation history storage (in-memory, Redis, database)
- 🔄 **Context Management**: 3-level compression strategy (truncate → summarize → LLM-compress)
- 🎯 **Extension Protocols**: MemoryProvider, SystemPromptBuilder, BillingHook, ContextLoader
- 🧮 **Token Counting**: Accurate token estimation with tiktoken and character-based fallback
- ⚡ **Async First**: Full async/await support with streaming and cancellation

## Installation

```bash
pip install pig-agent-core
```

## Quick Start

### Basic Agent

```python
from pig_agent_core import Agent
from pig_llm import LLM

# Create agent with enhanced features
agent = Agent(
    name="Assistant",
    llm=LLM(provider="openai"),
    system_prompt="You are a helpful assistant.",
    max_rounds=10,  # Maximum conversation rounds
    verbose=True,   # Enable logging
)

# Run agent (async)
response = await agent.arun("Hello, how are you?")
print(response.content)
```

### Agent with Resilience

```python
from pig_agent_core import Agent, ProfileManager
from pig_llm import LLM

# Create profile manager for API key rotation
profile_manager = ProfileManager.from_env(
    env_prefix="OPENAI_API_KEY",  # Looks for OPENAI_API_KEY_1, _2, etc.
    model="gpt-4",
    fallback_models=["gpt-3.5-turbo"],
)

# Create agent with resilience
agent = Agent(
    name="ResilientAgent",
    llm=LLM(provider="openai"),
    profile_manager=profile_manager,  # Automatic key rotation
    max_rounds=15,
)

# Agent automatically handles rate limits and failures
response = await agent.arun("Complex task requiring multiple API calls")
```

### Agent with Tools

```python
from pig_agent_core.tools import TOOL_SCHEMAS, HANDLERS
from pig_agent_core.tools.registry import ToolRegistry

# Create registry and register core tools (convenience method)
registry = ToolRegistry()
registry.register_package(TOOL_SCHEMAS, HANDLERS, is_core=True)

# Or register tools individually
# for schema in TOOL_SCHEMAS:
#     tool_name = schema["function"]["name"]
#     handler = HANDLERS.get(tool_name)
#     if handler:
#         registry.register(
#             name=tool_name,
#             handler=handler,
#             schema=schema,
#             is_core=True,
#         )

# Create agent with tools
agent = Agent(
    name="ThinkingAgent",
    llm=LLM(provider="openai"),
)
agent.registry = registry

# Agent can now use think, plan, and discover_tools
response = await agent.respond("Help me plan a project")
```

## Architecture

### Master Loop

The agent uses a streaming master loop that:
1. Receives user message
2. Calls LLM with streaming
3. Detects tool calls in stream
4. Executes tools automatically
5. Continues until no more tool calls
6. Returns final response

```
User Message → LLM Stream → Tool Calls? → Execute Tools → LLM Stream → Response
                    ↑                            ↓
                    └────────────────────────────┘
                         (Repeat until done)
```

### Tool System

Tools are async handlers registered with schemas:

```python
async def handle_search(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: asyncio.Event | None = None,
) -> ToolResult:
    query = args.get("query", "")
    # Perform search...
    return ToolResult(ok=True, data=results)

# Register tool
registry.register(
    name="search",
    handler=handle_search,
    schema={
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"],
            },
        },
    },
)
```

### Resilience System

#### API Key Rotation

```python
from pig_agent_core.resilience.profile import ProfileManager

# Create profile manager with multiple API keys
profile_manager = ProfileManager.from_env(
    env_prefix="OPENAI_API_KEY",  # Looks for OPENAI_API_KEY_1, _2, etc.
    model="gpt-4",
    fallback_models=["gpt-3.5-turbo"],
)

# Create agent with resilience
agent = Agent(
    name="ResilientAgent",
    llm=LLM(provider="openai"),
    profile_manager=profile_manager,
)

# Agent automatically rotates keys on rate limits
```

#### Retry Logic

```python
from pig_agent_core.resilience.retry import resilient_streaming_call

# Resilient LLM call with automatic retry
async for chunk in resilient_streaming_call(
    llm=llm,
    messages=messages,
    profile_manager=profile_manager,
    max_retries=3,
):
    print(chunk.content, end="")
```

#### Context Compression

```python
def compress_messages(messages: list[Message]) -> list[Message]:
    """Compress messages when context is too long."""
    # Keep system prompt and recent messages
    if len(messages) <= 10:
        return messages
    return [messages[0]] + messages[-9:]

agent = Agent(
    name="Agent",
    llm=llm,
    compress_fn=compress_messages,
)

# Agent automatically compresses on context overflow
```

### Observability

```python
from pig_agent_core.observability.events import AgentEvent, AgentEventType

def event_callback(event: AgentEvent):
    """Handle agent events."""
    if event.type == AgentEventType.TOOL_START:
        print(f"Tool started: {event.data.get('tool_name')}")
    elif event.type == AgentEventType.TOOL_END:
        print(f"Tool finished: {event.data.get('result')}")

agent = Agent(
    name="ObservableAgent",
    llm=llm,
    event_callback=event_callback,
)

# Events are emitted automatically during execution
```

## Extension Protocols

pig-agent-core provides protocol-based extension points for customizing agent behavior. All protocols use Python's `Protocol` for structural typing, allowing products to provide custom implementations.

### MemoryProvider

Customize conversation history storage:

```python
from pig_agent_core import MemoryProvider, Message

class RedisMemoryProvider:
    """Store conversation history in Redis."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_messages(self, session_id: str) -> list[Message]:
        """Load messages from Redis."""
        data = await self.redis.get(f"session:{session_id}")
        if not data:
            return []
        return [Message(**msg) for msg in json.loads(data)]

    async def add_message(self, session_id: str, message: Message) -> None:
        """Save message to Redis."""
        messages = await self.get_messages(session_id)
        messages.append(message)
        await self.redis.set(
            f"session:{session_id}",
            json.dumps([msg.model_dump() for msg in messages])
        )

    async def clear_messages(self, session_id: str) -> None:
        """Clear session history."""
        await self.redis.delete(f"session:{session_id}")

# Use custom memory provider
agent = Agent(
    llm=llm,
    memory_provider=RedisMemoryProvider(redis_client),
)
```

### SystemPromptBuilder

Dynamically build system prompts with context:

```python
from pig_agent_core import SystemPromptBuilder

class BrandedPromptBuilder:
    """Build prompts with brand context."""

    def __init__(self, brand_db):
        self.brand_db = brand_db

    def build_prompt(self, base_prompt: str, context: dict) -> str:
        """Add brand voice and guidelines."""
        brand = self.brand_db.get(context.get("brand_id"))
        return f"""{base_prompt}

Brand Voice: {brand.voice}
Guidelines: {brand.guidelines}
Target Audience: {brand.audience}
"""

agent = Agent(
    llm=llm,
    system_prompt="You are a helpful assistant.",
    system_prompt_builder=BrandedPromptBuilder(brand_db),
)
```

### BillingHook

Track LLM and tool usage for cost monitoring:

```python
from pig_agent_core import BillingHook

class CostTracker:
    """Track costs per user."""

    def __init__(self):
        self.costs = {}
        self.pricing = {
            "gpt-4": {"input": 0.03, "output": 0.06},  # per 1K tokens
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
        }

    def on_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Track LLM call costs."""
        if model in self.pricing:
            cost = (
                input_tokens / 1000 * self.pricing[model]["input"] +
                output_tokens / 1000 * self.pricing[model]["output"]
            )
            user_id = user_id or "default"
            self.costs[user_id] = self.costs.get(user_id, 0) + cost

    def on_tool_call(
        self,
        tool_name: str,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Track tool usage."""
        # Could add tool-specific costs here
        pass

    def get_usage_summary(self, user_id: str | None = None) -> dict:
        """Get cost summary."""
        if user_id:
            return {"user_id": user_id, "total_cost": self.costs.get(user_id, 0)}
        return {"total_cost": sum(self.costs.values()), "by_user": self.costs}

tracker = CostTracker()
agent = Agent(
    llm=llm,
    billing_hook=tracker,
)

# After execution
summary = tracker.get_usage_summary()
print(f"Total cost: ${summary['total_cost']:.4f}")
```

### ContextLoader

Load user/brand context dynamically:

```python
from pig_agent_core import ContextLoader

class DatabaseContextLoader:
    """Load context from database."""

    def __init__(self, db):
        self.db = db

    async def load_context(self, user_id: str) -> dict:
        """Load user preferences and history."""
        user = await self.db.users.find_one({"id": user_id})
        return {
            "user_name": user["name"],
            "preferences": user["preferences"],
            "recent_topics": user["recent_topics"],
            "language": user["language"],
        }

# Context is loaded and injected into system prompt
agent = Agent(
    llm=llm,
    context_loader=DatabaseContextLoader(db),
)
```

### Compression Functions

Provide custom context compression strategies:

```python
from pig_agent_core import compress_messages, CompressionConfig

# Use built-in 3-level compression
from pig_agent_core.context import compress_messages

agent = Agent(
    llm=llm,
    compress_fn=lambda msgs: compress_messages(
        msgs,
        max_tokens=8000,
        model="gpt-4",
        config=CompressionConfig(
            level1_threshold=0.7,  # Truncate tool results at 70%
            level2_threshold=0.8,  # Summarize at 80%
            level3_threshold=0.9,  # LLM-compress at 90%
        ),
    ),
)

# Or provide custom compression
def custom_compress(messages: list[Message]) -> list[Message]:
    """Keep only system prompt and last 5 messages."""
    if len(messages) <= 6:
        return messages
    return [messages[0]] + messages[-5:]

agent = Agent(llm=llm, compress_fn=custom_compress)
```

### Tool Audit and Metrics

Track tool usage patterns and performance:

```python
from pig_agent_core import ToolAuditLog, ToolMetricsCollector

# Audit logging
audit_log = ToolAuditLog(max_entries=10000)
audit_log.log(
    tool_name="search_web",
    user_id="user123",
    args={"query": "python"},
    success=True,
    duration=2.5,
    result_size=1024,
)

# Get failed executions
failed = audit_log.get_failed_entries(limit=10)

# Export to JSON
audit_log.export_json("audit.json")

# Metrics collection
metrics = ToolMetricsCollector()
metrics.record("search_web", success=True, duration=2.5, result_size=1024)

# Get statistics
summary = metrics.get_summary()
print(f"Success rate: {summary['success_rate']:.1f}%")
print(f"Calls per second: {summary['calls_per_second']:.2f}")

# Get top tools by usage
top_tools = metrics.get_top_tools(limit=5, by="calls")
for tool_metrics in top_tools:
    print(f"{tool_metrics.tool_name}: {tool_metrics.total_calls} calls")
```

## API Reference

### Agent

```python
class Agent:
    def __init__(
        self,
        name: str = "Agent",
        llm: LLM | None = None,
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
        max_iterations: int = 10,
        on_tool_start: Callable | None = None,
        on_tool_end: Callable | None = None,
        verbose: bool = False,
        profile_manager: ProfileManager | None = None,
        event_callback: AgentEventCallback | None = None,
        compress_fn: Callable[[list[Message]], list[Message]] | None = None,
    )

    async def respond(
        self,
        user_message: str,
        cancel: asyncio.Event | None = None,
    ) -> Response:
        """Get non-streaming response."""

    async def respond_stream(
        self,
        user_message: str,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Get streaming response."""
```

### ToolRegistry

```python
class ToolRegistry:
    def register(
        self,
        name: str,
        handler: Callable,
        schema: dict[str, Any],
        *,
        is_core: bool = False,
        timeout: float = 30.0,
        max_retries: int = 0,
    ) -> None:
        """Register a tool."""

    async def execute(
        self,
        tool_call: Any,
        user_id: str,
        meta: dict[str, Any],
        cancel: asyncio.Event | None = None,
    ) -> ToolResult:
        """Execute a tool."""

    def activate_tools(self, names: list[str]) -> list[str]:
        """Activate deferred tools (lazy loading)."""
```

### ToolResult

```python
@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def serialize(self, max_chars: int = 4000) -> str:
        """Serialize with structure-aware truncation."""
```

### ProfileManager

```python
class ProfileManager:
    @classmethod
    def from_env(
        cls,
        env_prefix: str = "OPENAI_API_KEY",
        model: str = "gpt-4",
        fallback_models: list[str] | None = None,
    ) -> ProfileManager:
        """Load profiles from environment variables."""

    def get_next_profile(self) -> APIProfile | None:
        """Get next available profile (round-robin with cooldown)."""
```

## Migration Guide

### From v0.0.x to v0.1.0

#### Tool System Changes

**Before (v0.0.x):**
```python
from pig_agent_core import Agent, tool

@tool(description="Get weather")
def get_weather(location: str) -> str:
    return f"Weather in {location}"

agent = Agent(tools=[get_weather])
```

**After (v0.1.0):**
```python
from pig_agent_core import Agent
from pig_agent_core.tools.base import ToolResult
from pig_agent_core.tools.registry import ToolRegistry

async def handle_weather(args, user_id=None, meta=None, cancel=None):
    location = args.get("location", "")
    return ToolResult(ok=True, data=f"Weather in {location}")

registry = ToolRegistry()
registry.register(
    name="get_weather",
    handler=handle_weather,
    schema={...},  # OpenAI function calling schema
)

agent = Agent()
agent.registry = registry
```

#### Agent Methods

**Before (v0.0.x):**
```python
response = agent.run("Hello")  # Synchronous
```

**After (v0.1.0):**
```python
response = await agent.respond("Hello")  # Async
# or
async for chunk in agent.respond_stream("Hello"):  # Streaming
    print(chunk.content)
```

#### State Management

State management API remains compatible, but now supports new subsystems:

```python
# Save state (includes resilience and observability config)
state = agent.get_state()
agent.save_state("state.json")

# Restore state
agent = Agent.from_state("state.json")
```

## Core Tools

pig-agent-core includes three core tools:

- **think**: Internal reasoning tool for agent planning
- **plan**: Create and validate execution plans
- **discover_tools**: Find available tools by description

These tools are automatically available when using the new ToolRegistry.

## Examples

### Complete Agent with All Features

```python
import asyncio
from pig_agent_core import Agent
from pig_llm import LLM
from pig_agent_core.resilience.profile import ProfileManager
from pig_agent_core.observability.events import AgentEvent

# Setup resilience
profile_manager = ProfileManager.from_env(
    env_prefix="OPENAI_API_KEY",
    model="gpt-4",
    fallback_models=["gpt-3.5-turbo"],
)

# Setup observability
def log_events(event: AgentEvent):
    print(f"[{event.type}] {event.data}")

# Setup context compression
def compress(messages):
    return [messages[0]] + messages[-9:] if len(messages) > 10 else messages

# Create agent
agent = Agent(
    name="ProductionAgent",
    llm=LLM(provider="openai"),
    system_prompt="You are a helpful assistant.",
    profile_manager=profile_manager,
    event_callback=log_events,
    compress_fn=compress,
    max_iterations=10,
    verbose=True,
)

# Run agent
async def main():
    async for chunk in agent.respond_stream("Help me plan a project"):
        if chunk.type == "text":
            print(chunk.content, end="", flush=True)

asyncio.run(main())
```

## Development

```bash
# Install in development mode
uv pip install -e .

# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest tests/

# Run with coverage
pytest tests/ --cov=pig_agent_core --cov-report=html
```

## License

MIT
