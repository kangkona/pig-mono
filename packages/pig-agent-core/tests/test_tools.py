"""Tests for tool system."""

import pytest
from pig_agent_core.tools import Tool, tool


def test_tool_creation():
    """Test creating a tool from function."""
    def my_func(x: int, y: int = 10) -> int:
        """Add two numbers."""
        return x + y
    
    t = Tool(func=my_func, description="Add numbers")
    assert t.name == "my_func"
    assert t.description == "Add numbers"


def test_tool_execution():
    """Test tool execution."""
    def add(x: int, y: int) -> int:
        return x + y
    
    t = Tool(func=add)
    result = t.execute(x=5, y=3)
    assert result == 8


def test_tool_validation():
    """Test parameter validation."""
    def typed_func(x: int, y: str) -> str:
        return f"{x}: {y}"
    
    t = Tool(func=typed_func)
    result = t.execute(x=42, y="hello")
    assert result == "42: hello"


def test_tool_error_handling():
    """Test tool error handling."""
    def failing_func(x: int) -> int:
        raise ValueError("Test error")
    
    t = Tool(func=failing_func)
    with pytest.raises(RuntimeError, match="Tool failing_func failed"):
        t.execute(x=1)


def test_tool_decorator():
    """Test @tool decorator."""
    @tool(description="Get greeting")
    def greet(name: str) -> str:
        return f"Hello, {name}!"
    
    assert isinstance(greet, Tool)
    assert greet.name == "greet"
    assert greet.description == "Get greeting"
    result = greet.execute(name="Alice")
    assert result == "Hello, Alice!"


def test_tool_decorator_with_defaults():
    """Test @tool decorator with default arguments."""
    @tool
    def simple_func(x: int) -> int:
        """Double the number."""
        return x * 2
    
    assert isinstance(simple_func, Tool)
    assert simple_func.description == "Double the number."
    assert simple_func.execute(x=5) == 10


def test_tool_openai_schema():
    """Test OpenAI schema generation."""
    @tool(description="Calculate sum")
    def add(x: int, y: int = 0) -> int:
        return x + y
    
    schema = add.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "add"
    assert schema["function"]["description"] == "Calculate sum"
    assert "parameters" in schema["function"]


def test_tool_callable():
    """Test that tool is callable."""
    @tool
    def double(x: int) -> int:
        return x * 2
    
    # Can call as normal function
    result = double(5)
    assert result == 10
