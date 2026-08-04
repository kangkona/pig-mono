"""Tests for tool registry."""

from typing import Any

import pytest
from pig_agent_core.registry import ToolRegistry
from pig_agent_core.tools import tool


def test_registry_creation() -> None:
    """Test creating a registry."""
    registry = ToolRegistry()
    assert len(registry) == 0


def test_registry_register() -> None:
    """Test registering a tool."""

    @tool
    def my_tool(x: int) -> int:
        return x * 2

    registry = ToolRegistry()
    registry.register(my_tool)

    assert len(registry) == 1
    assert "my_tool" in registry


def test_registry_get() -> None:
    """Test getting a tool."""

    @tool
    def my_tool(x: int) -> int:
        return x * 2

    registry = ToolRegistry()
    registry.register(my_tool)

    retrieved = registry.get("my_tool")
    assert retrieved is my_tool


def test_registry_get_missing() -> None:
    """Test getting non-existent tool."""
    registry = ToolRegistry()
    assert registry.get("missing") is None


def test_registry_unregister() -> None:
    """Test unregistering a tool."""

    @tool
    def my_tool(x: int) -> int:
        return x * 2

    registry = ToolRegistry()
    registry.register(my_tool)
    assert len(registry) == 1

    registry.unregister("my_tool")
    assert len(registry) == 0


def test_registry_list_tools() -> None:
    """Test listing all tools."""

    @tool
    def tool1(x: int) -> int:
        return x

    @tool
    def tool2(x: str) -> str:
        return x

    registry = ToolRegistry()
    registry.register(tool1)
    registry.register(tool2)

    tools = registry.list_tools()
    assert len(tools) == 2
    assert tool1 in tools
    assert tool2 in tools


def test_registry_execute() -> None:
    """Test executing a tool by name."""

    @tool
    def add(x: int, y: int) -> int:
        return x + y

    registry = ToolRegistry()
    registry.register(add)

    result = registry.execute("add", x=5, y=3)
    assert result == 8


def test_registry_execute_missing() -> None:
    """Test executing non-existent tool."""
    registry = ToolRegistry()

    with pytest.raises(KeyError, match="Tool 'missing' not found"):
        registry.execute("missing", x=1)


def test_registry_get_schemas() -> None:
    """Test getting OpenAI schemas."""

    @tool(description="Tool 1")
    def tool1(x: int) -> int:
        return x

    @tool(description="Tool 2")
    def tool2(y: str) -> str:
        return y

    registry = ToolRegistry()
    registry.register(tool1)
    registry.register(tool2)

    schemas = registry.get_schemas()
    assert len(schemas) == 2
    assert all(s["type"] == "function" for s in schemas)


def test_registry_iteration() -> None:
    """Test iterating over registry."""

    @tool
    def tool1(x: int) -> int:
        return x

    @tool
    def tool2(x: int) -> int:
        return x

    registry = ToolRegistry()
    registry.register(tool1)
    registry.register(tool2)

    tools = list(registry)
    assert len(tools) == 2


# ---------------------------------------------------------------------------
# Audit / metrics integration tests
# ---------------------------------------------------------------------------


def test_registry_records_audit_entry_after_execute() -> None:
    """ToolAuditLog passed to ToolRegistry is populated after execute()."""
    import asyncio
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.audit import ToolAuditLog
    from pig_agent_core.tools.base import ToolResult
    from pig_agent_core.tools.registry import ToolRegistry

    audit = ToolAuditLog()
    registry = ToolRegistry(audit_log=audit)

    def noop_handler(**kwargs: Any) -> Any:
        return ToolResult(ok=True, data="ok")

    registry.register(
        "noop",
        noop_handler,
        {
            "type": "function",
            "function": {"name": "noop", "parameters": {"type": "object", "properties": {}}},
        },
    )

    tool_call = SimpleNamespace(function=SimpleNamespace(name="noop", arguments=json.dumps({})))
    asyncio.run(registry.execute(tool_call, "user1", {}))

    entries = audit.get_entries()
    assert len(entries) == 1
    assert entries[0].tool_name == "noop"
    assert entries[0].user_id == "user1"
    assert entries[0].success is True


def test_registry_records_metrics_after_execute() -> None:
    """ToolMetricsCollector passed to ToolRegistry is populated after execute()."""
    import asyncio
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.base import ToolResult
    from pig_agent_core.tools.metrics import ToolMetricsCollector
    from pig_agent_core.tools.registry import ToolRegistry

    metrics = ToolMetricsCollector()
    registry = ToolRegistry(metrics=metrics)

    def noop_handler(**kwargs: Any) -> Any:
        return ToolResult(ok=True, data="ok")

    registry.register(
        "noop",
        noop_handler,
        {
            "type": "function",
            "function": {"name": "noop", "parameters": {"type": "object", "properties": {}}},
        },
    )

    tool_call = SimpleNamespace(function=SimpleNamespace(name="noop", arguments=json.dumps({})))
    asyncio.run(registry.execute(tool_call, "user1", {}))

    summary = metrics.get_metrics("noop")
    assert summary is not None
    assert summary.total_calls == 1
    assert summary.success_rate == 100.0


def test_registry_without_audit_metrics_unchanged() -> None:
    """Registry with no audit/metrics (default) runs unaffected."""
    import asyncio
    import json
    from types import SimpleNamespace

    from pig_agent_core.tools.base import ToolResult
    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()  # no audit_log, no metrics

    def noop_handler(**kwargs: Any) -> Any:
        return ToolResult(ok=True, data="ok")

    registry.register(
        "noop",
        noop_handler,
        {
            "type": "function",
            "function": {"name": "noop", "parameters": {"type": "object", "properties": {}}},
        },
    )

    tool_call = SimpleNamespace(function=SimpleNamespace(name="noop", arguments=json.dumps({})))
    result = asyncio.run(registry.execute(tool_call, "user1", {}))
    assert result.ok is True
