"""Tests for tool registry."""

import pytest
from pig_agent_core.tools import Tool, tool
from pig_agent_core.registry import ToolRegistry


def test_registry_creation():
    """Test creating a registry."""
    registry = ToolRegistry()
    assert len(registry) == 0


def test_registry_register():
    """Test registering a tool."""
    @tool
    def my_tool(x: int) -> int:
        return x * 2
    
    registry = ToolRegistry()
    registry.register(my_tool)
    
    assert len(registry) == 1
    assert "my_tool" in registry


def test_registry_get():
    """Test getting a tool."""
    @tool
    def my_tool(x: int) -> int:
        return x * 2
    
    registry = ToolRegistry()
    registry.register(my_tool)
    
    retrieved = registry.get("my_tool")
    assert retrieved is my_tool


def test_registry_get_missing():
    """Test getting non-existent tool."""
    registry = ToolRegistry()
    assert registry.get("missing") is None


def test_registry_unregister():
    """Test unregistering a tool."""
    @tool
    def my_tool(x: int) -> int:
        return x * 2
    
    registry = ToolRegistry()
    registry.register(my_tool)
    assert len(registry) == 1
    
    registry.unregister("my_tool")
    assert len(registry) == 0


def test_registry_list_tools():
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


def test_registry_execute():
    """Test executing a tool by name."""
    @tool
    def add(x: int, y: int) -> int:
        return x + y
    
    registry = ToolRegistry()
    registry.register(add)
    
    result = registry.execute("add", x=5, y=3)
    assert result == 8


def test_registry_execute_missing():
    """Test executing non-existent tool."""
    registry = ToolRegistry()
    
    with pytest.raises(KeyError, match="Tool 'missing' not found"):
        registry.execute("missing", x=1)


def test_registry_get_schemas():
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


def test_registry_iteration():
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
