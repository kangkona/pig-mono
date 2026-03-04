"""Test register_package convenience method."""

import pytest
from pig_agent_core.tools.base import ToolResult
from pig_agent_core.tools.registry import ToolRegistry


@pytest.fixture
def mock_schemas():
    """Create mock tool schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": "tool1",
                "description": "First tool",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tool2",
                "description": "Second tool",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tool3",
                "description": "Third tool",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


@pytest.fixture
def mock_handlers():
    """Create mock tool handlers."""

    async def handler1(args, user_id=None, meta=None, cancel=None):
        return ToolResult(ok=True, data="result1")

    async def handler2(args, user_id=None, meta=None, cancel=None):
        return ToolResult(ok=True, data="result2")

    async def handler3(args, user_id=None, meta=None, cancel=None):
        return ToolResult(ok=True, data="result3")

    return {
        "tool1": handler1,
        "tool2": handler2,
        "tool3": handler3,
    }


def test_register_package_basic(mock_schemas, mock_handlers):
    """Test basic register_package functionality."""
    registry = ToolRegistry()

    registered = registry.register_package(mock_schemas, mock_handlers)

    assert len(registered) == 3
    assert "tool1" in registered
    assert "tool2" in registered
    assert "tool3" in registered

    # Verify tools are registered
    with registry._lock:
        assert "tool1" in registry._handlers
        assert "tool2" in registry._handlers
        assert "tool3" in registry._handlers


def test_register_package_as_core(mock_schemas, mock_handlers):
    """Test register_package with is_core=True."""
    registry = ToolRegistry()

    registered = registry.register_package(mock_schemas, mock_handlers, is_core=True)

    assert len(registered) == 3

    # Verify tools are marked as core
    with registry._lock:
        assert "tool1" in registry._core_tools
        assert "tool2" in registry._core_tools
        assert "tool3" in registry._core_tools


def test_register_package_as_deferred(mock_schemas, mock_handlers):
    """Test register_package with is_core=False."""
    registry = ToolRegistry()

    registered = registry.register_package(mock_schemas, mock_handlers, is_core=False)

    assert len(registered) == 3

    # Verify tools are NOT marked as core
    with registry._lock:
        assert "tool1" not in registry._core_tools
        assert "tool2" not in registry._core_tools
        assert "tool3" not in registry._core_tools


def test_register_package_with_timeout(mock_schemas, mock_handlers):
    """Test register_package with custom timeout."""
    registry = ToolRegistry()

    registered = registry.register_package(mock_schemas, mock_handlers, timeout=60.0)

    assert len(registered) == 3

    # Verify timeout is set
    with registry._lock:
        assert registry._timeouts["tool1"] == 60.0
        assert registry._timeouts["tool2"] == 60.0
        assert registry._timeouts["tool3"] == 60.0


def test_register_package_with_retries(mock_schemas, mock_handlers):
    """Test register_package with custom max_retries."""
    registry = ToolRegistry()

    registered = registry.register_package(mock_schemas, mock_handlers, max_retries=3)

    assert len(registered) == 3

    # Verify retries are set
    with registry._lock:
        assert registry._retries["tool1"] == 3
        assert registry._retries["tool2"] == 3
        assert registry._retries["tool3"] == 3


def test_register_package_missing_handler(mock_schemas, mock_handlers):
    """Test register_package skips tools without handlers."""
    # Remove one handler
    handlers = mock_handlers.copy()
    del handlers["tool2"]

    registry = ToolRegistry()
    registered = registry.register_package(mock_schemas, handlers)

    # Should only register tool1 and tool3
    assert len(registered) == 2
    assert "tool1" in registered
    assert "tool3" in registered
    assert "tool2" not in registered

    with registry._lock:
        assert "tool1" in registry._handlers
        assert "tool2" not in registry._handlers
        assert "tool3" in registry._handlers


def test_register_package_invalid_schema(mock_handlers):
    """Test register_package skips invalid schemas."""
    invalid_schemas = [
        {"type": "function"},  # Missing function key
        {
            "type": "function",
            "function": {"description": "No name"},  # Missing name
        },
        {
            "type": "function",
            "function": {
                "name": "tool1",
                "description": "Valid",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    registry = ToolRegistry()
    registered = registry.register_package(invalid_schemas, mock_handlers)

    # Should only register tool1
    assert len(registered) == 1
    assert "tool1" in registered


def test_register_package_empty_lists():
    """Test register_package with empty lists."""
    registry = ToolRegistry()

    registered = registry.register_package([], {})

    assert len(registered) == 0


def test_register_package_returns_registered_names(mock_schemas, mock_handlers):
    """Test register_package returns list of registered tool names."""
    registry = ToolRegistry()

    registered = registry.register_package(mock_schemas, mock_handlers)

    assert isinstance(registered, list)
    assert all(isinstance(name, str) for name in registered)
    assert len(registered) == 3


@pytest.mark.asyncio
async def test_register_package_tools_are_executable(mock_schemas, mock_handlers):
    """Test that tools registered via register_package are executable."""
    registry = ToolRegistry()

    registered = registry.register_package(mock_schemas, mock_handlers, is_core=True)

    assert len(registered) == 3

    # Create mock tool_call
    from types import SimpleNamespace

    tool_call = SimpleNamespace(function=SimpleNamespace(name="tool1", arguments="{}"))

    # Execute tool
    result = await registry.execute(tool_call, user_id="test", meta={})

    assert result.ok is True
    assert result.data == "result1"


def test_register_package_with_real_schemas():
    """Test register_package with real TOOL_SCHEMAS and HANDLERS."""
    from pig_agent_core.tools import HANDLERS, TOOL_SCHEMAS

    registry = ToolRegistry()

    registered = registry.register_package(TOOL_SCHEMAS, HANDLERS, is_core=True)

    # Should register at least the core tools (think, plan, discover_tools, get_current_time)
    assert len(registered) >= 3
    assert "think" in registered or "plan" in registered

    # Verify schemas are available
    schemas = registry.get_schemas()
    assert len(schemas) >= 3
