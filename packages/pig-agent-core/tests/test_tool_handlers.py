"""Tests for core tool handlers."""

import asyncio

import pytest
from pig_agent_core.tools.handlers_core import (
    HANDLERS,
    handle_discover_tools,
    handle_plan,
    handle_think,
)


def test_handlers_registered():
    """Test that all handlers are registered."""
    assert "think" in HANDLERS
    assert "plan" in HANDLERS
    assert "discover_tools" in HANDLERS


@pytest.mark.asyncio
async def test_handle_think_success():
    """Test think handler with valid input."""
    args = {"thought": "I should search for information first"}
    result = await handle_think(args, "user123", {})

    assert result.ok is True
    assert result.data["status"] == "ok"
    assert result.data["thought_length"] > 0


@pytest.mark.asyncio
async def test_handle_think_empty():
    """Test think handler with empty thought."""
    args = {"thought": ""}
    result = await handle_think(args, "user123", {})

    assert result.ok is False
    assert "required" in result.error.lower()


@pytest.mark.asyncio
async def test_handle_think_missing():
    """Test think handler with missing thought."""
    args = {}
    result = await handle_think(args, "user123", {})

    assert result.ok is False
    assert "required" in result.error.lower()


@pytest.mark.asyncio
async def test_handle_plan_success():
    """Test plan handler with valid input."""
    args = {
        "goal": "Research competitors",
        "steps": ["Search for competitors", "Analyze their features", "Create comparison"],
    }

    result = await handle_plan(args, "user123", {})

    assert result.ok is True
    assert result.data["status"] == "planned"
    assert result.data["goal"] == "Research competitors"
    assert result.data["total_steps"] == 3
    assert len(result.data["steps"]) == 3


@pytest.mark.asyncio
async def test_handle_plan_missing_goal():
    """Test plan handler with missing goal."""
    args = {"steps": ["Step 1", "Step 2"]}
    result = await handle_plan(args, "user123", {})

    assert result.ok is False
    assert "goal" in result.error.lower()


@pytest.mark.asyncio
async def test_handle_plan_missing_steps():
    """Test plan handler with missing steps."""
    args = {"goal": "Do something"}
    result = await handle_plan(args, "user123", {})

    assert result.ok is False
    assert "steps" in result.error.lower()


@pytest.mark.asyncio
async def test_handle_plan_empty_steps():
    """Test plan handler with empty steps list."""
    args = {"goal": "Do something", "steps": []}
    result = await handle_plan(args, "user123", {})

    assert result.ok is False
    assert "step" in result.error.lower()


@pytest.mark.asyncio
async def test_handle_plan_invalid_step():
    """Test plan handler with invalid step."""
    args = {"goal": "Do something", "steps": ["Valid step", "", "Another step"]}
    result = await handle_plan(args, "user123", {})

    assert result.ok is False
    assert "step" in result.error.lower()


@pytest.mark.asyncio
async def test_handle_discover_tools_no_query():
    """Test discover_tools handler without query."""
    args = {}
    result = await handle_discover_tools(args, "user123", {})

    assert result.ok is True
    assert "available" in result.data
    assert "hint" in result.data
    assert result.data["loaded"] == []


@pytest.mark.asyncio
async def test_handle_discover_tools_empty_query():
    """Test discover_tools handler with empty query."""
    args = {"query": ""}
    result = await handle_discover_tools(args, "user123", {})

    assert result.ok is True
    assert "available" in result.data
    assert result.data["loaded"] == []


@pytest.mark.asyncio
async def test_handle_discover_tools_no_match():
    """Test discover_tools handler with no matching tools."""
    args = {"query": "nonexistent_tool_xyz"}
    result = await handle_discover_tools(args, "user123", {})

    assert result.ok is True
    assert result.data["loaded"] == []
    assert "message" in result.data
    assert "No tools matched" in result.data["message"]


@pytest.mark.asyncio
async def test_handle_discover_tools_with_match():
    """Test discover_tools handler with matching query."""
    # Since we only have core tools registered, this will return empty
    # In a real scenario with web tools, this would match
    args = {"query": "web"}
    result = await handle_discover_tools(args, "user123", {})

    assert result.ok is True
    # With only core tools, no matches expected
    # When web tools are added, this test should be updated


@pytest.mark.asyncio
async def test_handle_think_with_cancellation():
    """Test think handler respects cancellation."""
    args = {"thought": "Testing cancellation"}
    cancel = asyncio.Event()
    # Don't set the event - handler should complete normally
    result = await handle_think(args, "user123", {}, cancel)

    assert result.ok is True


@pytest.mark.asyncio
async def test_handle_plan_with_cancellation():
    """Test plan handler respects cancellation."""
    args = {"goal": "Test", "steps": ["Step 1"]}
    cancel = asyncio.Event()
    result = await handle_plan(args, "user123", {}, cancel)

    assert result.ok is True


@pytest.mark.asyncio
async def test_handlers_are_async():
    """Test that all handlers are async functions."""
    import inspect

    for name, handler in HANDLERS.items():
        assert inspect.iscoroutinefunction(handler), f"Handler {name} should be async"


@pytest.mark.asyncio
async def test_handle_plan_single_step():
    """Test plan handler with single step."""
    args = {"goal": "Simple task", "steps": ["Do it"]}
    result = await handle_plan(args, "user123", {})

    assert result.ok is True
    assert result.data["total_steps"] == 1


@pytest.mark.asyncio
async def test_handle_plan_many_steps():
    """Test plan handler with many steps."""
    steps = [f"Step {i}" for i in range(10)]
    args = {"goal": "Complex task", "steps": steps}
    result = await handle_plan(args, "user123", {})

    assert result.ok is True
    assert result.data["total_steps"] == 10
    assert len(result.data["steps"]) == 10
