"""Tests for enhanced tool registry."""

import asyncio

import pytest
from pig_agent_core.tools import CancelledError, ToolRegistry, ToolResult


# Mock tool handlers
async def mock_async_tool(args, user_id, meta, cancel):
    """Mock async tool handler."""
    await asyncio.sleep(0.01)
    return ToolResult(ok=True, data=f"Result: {args.get('input', 'none')}")


def mock_sync_tool(args, user_id, meta, cancel):
    """Mock sync tool handler."""
    return ToolResult(ok=True, data=f"Sync result: {args.get('value', 0)}")


async def mock_slow_tool(args, user_id, meta, cancel):
    """Mock slow tool that times out."""
    await asyncio.sleep(10)
    return ToolResult(ok=True, data="Should not reach here")


async def mock_failing_tool(args, user_id, meta, cancel):
    """Mock tool that fails."""
    raise ValueError("Tool failed")


async def mock_cancellable_tool(args, user_id, meta, cancel):
    """Mock tool that checks cancellation."""
    for _i in range(10):
        if cancel and cancel.is_set():
            raise CancelledError("Cancelled")
        await asyncio.sleep(0.01)
    return ToolResult(ok=True, data="Completed")


def test_registry_creation():
    """Test creating a registry."""
    registry = ToolRegistry()
    assert len(registry) == 0


def test_registry_register_tool():
    """Test registering a tool."""
    registry = ToolRegistry()

    schema = {
        "type": "function",
        "function": {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }

    registry.register("test_tool", mock_sync_tool, schema)

    assert "test_tool" in registry
    assert len(registry) == 1


def test_registry_register_core_tool():
    """Test registering a core tool."""
    registry = ToolRegistry()

    schema = {
        "type": "function",
        "function": {
            "name": "core_tool",
            "description": "A core tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }

    registry.register("core_tool", mock_sync_tool, schema, is_core=True)

    # Core tools should appear in schemas immediately
    schemas = registry.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "core_tool"


def test_registry_lazy_loading():
    """Test lazy loading of non-core tools."""
    registry = ToolRegistry()

    # Register core tool
    core_schema = {
        "type": "function",
        "function": {
            "name": "core_tool",
            "description": "Core",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("core_tool", mock_sync_tool, core_schema, is_core=True)

    # Register deferred tool
    deferred_schema = {
        "type": "function",
        "function": {
            "name": "deferred_tool",
            "description": "Deferred",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("deferred_tool", mock_sync_tool, deferred_schema, is_core=False)

    # Only core tool should be in schemas initially
    schemas = registry.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "core_tool"

    # Activate deferred tool
    activated = registry.activate_tools(["deferred_tool"])
    assert activated == ["deferred_tool"]

    # Now both should be in schemas
    schemas = registry.get_schemas()
    assert len(schemas) == 2
    names = {s["function"]["name"] for s in schemas}
    assert names == {"core_tool", "deferred_tool"}


def test_registry_activate_tools_idempotent():
    """Test that activating tools multiple times is idempotent."""
    registry = ToolRegistry()

    schema = {
        "type": "function",
        "function": {
            "name": "tool1",
            "description": "Tool 1",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("tool1", mock_sync_tool, schema, is_core=False)

    # First activation
    activated = registry.activate_tools(["tool1"])
    assert activated == ["tool1"]

    # Second activation should return empty
    activated = registry.activate_tools(["tool1"])
    assert activated == []


@pytest.mark.asyncio
async def test_registry_execute_async_tool():
    """Test executing an async tool."""
    registry = ToolRegistry()

    schema = {
        "type": "function",
        "function": {
            "name": "async_tool",
            "description": "Async tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("async_tool", mock_async_tool, schema, is_core=True)

    # Create mock tool call
    class MockToolCall:
        class Function:
            name = "async_tool"
            arguments = '{"input": "test"}'

        function = Function()

    result = await registry.execute(MockToolCall(), "user123", {})

    assert result.ok is True
    assert result.data == "Result: test"


@pytest.mark.asyncio
async def test_registry_execute_with_timeout():
    """Test tool execution timeout."""
    registry = ToolRegistry()

    schema = {
        "type": "function",
        "function": {
            "name": "slow_tool",
            "description": "Slow tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("slow_tool", mock_slow_tool, schema, is_core=True, timeout=0.1)

    class MockToolCall:
        class Function:
            name = "slow_tool"
            arguments = "{}"

        function = Function()

    result = await registry.execute(MockToolCall(), "user123", {})

    assert result.ok is False
    assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_registry_execute_with_retry():
    """Test tool execution with retry."""
    registry = ToolRegistry()

    call_count = 0

    async def flaky_tool(args, user_id, meta, cancel):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Temporary failure")
        return ToolResult(ok=True, data="Success after retries")

    schema = {
        "type": "function",
        "function": {
            "name": "flaky_tool",
            "description": "Flaky tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("flaky_tool", flaky_tool, schema, is_core=True, max_retries=3)

    class MockToolCall:
        class Function:
            name = "flaky_tool"
            arguments = "{}"

        function = Function()

    result = await registry.execute(MockToolCall(), "user123", {})

    assert result.ok is True
    assert result.data == "Success after retries"
    assert call_count == 3


@pytest.mark.asyncio
async def test_registry_execute_with_cancellation():
    """Test tool execution cancellation."""
    registry = ToolRegistry()

    schema = {
        "type": "function",
        "function": {
            "name": "cancellable_tool",
            "description": "Cancellable tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("cancellable_tool", mock_cancellable_tool, schema, is_core=True)

    class MockToolCall:
        class Function:
            name = "cancellable_tool"
            arguments = "{}"

        function = Function()

    cancel = asyncio.Event()
    cancel.set()  # Cancel immediately

    result = await registry.execute(MockToolCall(), "user123", {}, cancel=cancel)

    assert result.ok is False
    assert "cancel" in result.error.lower()


def test_registry_unregister():
    """Test unregistering a tool."""
    registry = ToolRegistry()

    schema = {
        "type": "function",
        "function": {
            "name": "temp_tool",
            "description": "Temporary tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("temp_tool", mock_sync_tool, schema)

    assert "temp_tool" in registry

    registry.unregister("temp_tool")

    assert "temp_tool" not in registry
    assert len(registry) == 0


def test_registry_list_tools():
    """Test listing all tools."""
    registry = ToolRegistry()

    for i in range(3):
        schema = {
            "type": "function",
            "function": {
                "name": f"tool{i}",
                "description": f"Tool {i}",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        registry.register(f"tool{i}", mock_sync_tool, schema)

    tools = registry.list_tools()
    assert tools == ["tool0", "tool1", "tool2"]


def test_registry_list_active_tools():
    """Test listing active tools."""
    registry = ToolRegistry()

    # Register core tool
    core_schema = {
        "type": "function",
        "function": {
            "name": "core",
            "description": "Core",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("core", mock_sync_tool, core_schema, is_core=True)

    # Register deferred tool
    deferred_schema = {
        "type": "function",
        "function": {
            "name": "deferred",
            "description": "Deferred",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry.register("deferred", mock_sync_tool, deferred_schema, is_core=False)

    # Only core should be active
    active = registry.list_active_tools()
    assert active == ["core"]

    # Activate deferred
    registry.activate_tools(["deferred"])

    # Both should be active
    active = registry.list_active_tools()
    assert active == ["core", "deferred"]
