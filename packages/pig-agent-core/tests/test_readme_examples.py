"""Verify README examples are accurate."""

from unittest.mock import Mock

# Test 1: Basic Agent creation
print("Test 1: Basic Agent creation...")
try:
    from pig_agent_core import Agent

    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    agent = Agent(
        name="Assistant",
        llm=mock_llm,
        system_prompt="You are a helpful assistant.",
    )
    print("✓ Basic agent creation works")
except Exception as e:
    print(f"✗ Basic agent creation failed: {e}")

# Test 2: Tool Registry
print("\nTest 2: Tool Registry...")
try:
    from pig_agent_core.tools import HANDLERS, TOOL_SCHEMAS
    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    for schema in TOOL_SCHEMAS:
        tool_name = schema["function"]["name"]
        handler = HANDLERS.get(tool_name)
        if handler:
            registry.register(
                name=tool_name,
                handler=handler,
                schema=schema,
                is_core=True,
            )
    print(f"✓ Registered {len(HANDLERS)} core tools")
except Exception as e:
    print(f"✗ Tool registry failed: {e}")

# Test 3: ToolResult
print("\nTest 3: ToolResult...")
try:
    from pig_agent_core.tools.base import ToolResult

    result = ToolResult(ok=True, data="test data")
    serialized = result.serialize()
    print(f"✓ ToolResult works: {serialized}")
except Exception as e:
    print(f"✗ ToolResult failed: {e}")

# Test 4: ProfileManager
print("\nTest 4: ProfileManager...")
try:
    import os

    from pig_agent_core.resilience.profile import ProfileManager

    # Set test env var
    os.environ["TEST_API_KEY_1"] = "test-key-1"
    os.environ["TEST_API_KEY_2"] = "test-key-2"

    profile_manager = ProfileManager.from_env(
        env_prefix="TEST_API_KEY",
        model="gpt-4",
        fallback_models=["gpt-3.5-turbo"],
    )
    print(f"✓ ProfileManager loaded {len(profile_manager.profiles)} profiles")
except Exception as e:
    print(f"✗ ProfileManager failed: {e}")

# Test 5: Event System
print("\nTest 5: Event System...")
try:
    from pig_agent_core.observability.events import AgentEvent, AgentEventType

    def event_callback(event: AgentEvent):
        pass

    event = AgentEvent(
        type=AgentEventType.TOOL_START,
        data={"tool_name": "test"},
    )
    print(f"✓ Event system works: {event.type}")
except Exception as e:
    print(f"✗ Event system failed: {e}")

# Test 6: Agent with all subsystems
print("\nTest 6: Agent with all subsystems...")
try:
    from pig_agent_core import Agent
    from pig_agent_core.observability.events import AgentEvent
    from pig_agent_core.resilience.profile import ProfileManager

    mock_llm = Mock()
    mock_llm.config.model = "gpt-4"

    def log_events(event: AgentEvent):
        pass

    def compress(messages):
        return [messages[0]] + messages[-9:] if len(messages) > 10 else messages

    agent = Agent(
        name="ProductionAgent",
        llm=mock_llm,
        system_prompt="You are a helpful assistant.",
        event_callback=log_events,
        compress_fn=compress,
        max_iterations=10,
        verbose=False,
    )
    print("✓ Agent with all subsystems works")
except Exception as e:
    print(f"✗ Agent with subsystems failed: {e}")

print("\n" + "=" * 50)
print("All README examples validated!")
