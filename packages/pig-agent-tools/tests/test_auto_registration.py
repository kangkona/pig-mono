"""Integration tests for tool auto-registration."""

import asyncio

import pytest
from pig_agent_core.tools import _global_registry
from pig_agent_tools.web import register_tools
from pig_agent_tools.web.providers.base import SearchResult


def test_register_tools_with_global_registry():
    """Test registering web tools with global registry."""
    with _global_registry._lock:
        _global_registry._handlers.clear()
        _global_registry._schemas.clear()
        _global_registry._core_tools.clear()
        _global_registry._discovered.clear()

    registered = register_tools()

    assert "search_web" in registered
    assert "read_webpage" in registered
    assert len(registered) == 2

    with _global_registry._lock:
        assert "search_web" in _global_registry._handlers
        assert "read_webpage" in _global_registry._handlers
        assert "search_web" in _global_registry._schemas
        assert "read_webpage" in _global_registry._schemas


def test_register_tools_with_new_registry():
    """Test registering web tools with new ToolRegistry."""
    from pig_agent_core.tools.registry import ToolRegistry

    new_registry = ToolRegistry()
    registered = register_tools(new_registry)

    assert "search_web" in registered
    assert "read_webpage" in registered

    with new_registry._lock:
        assert "search_web" in new_registry._handlers
        assert "read_webpage" in new_registry._handlers


def test_register_tools_with_old_registry_raises_error():
    """Test that registering with old ToolRegistry raises helpful error."""
    from pig_agent_core.registry import ToolRegistry as OldToolRegistry

    old_registry = OldToolRegistry()

    with pytest.raises(TypeError, match="old ToolRegistry API"):
        register_tools(old_registry)


def test_register_tools_idempotent():
    """Test that registering tools multiple times is safe."""
    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()

    registered1 = register_tools(registry)
    registered2 = register_tools(registry)

    assert registered1 == registered2

    with registry._lock:
        assert "search_web" in registry._handlers
        assert "read_webpage" in registry._handlers


def test_handlers_can_be_called_directly():
    """Test that handlers can be used without registration."""
    from pig_agent_tools.web import handle_search_web

    class _MockProvider:
        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            return [
                SearchResult(title="Test Result", url="https://example.com", snippet="Test content")
            ]

    result = asyncio.run(
        handle_search_web(
            {"query": "test", "max_results": 1},
            user_id="test_user",
            meta={},
            provider=_MockProvider(),
        )
    )

    assert result.ok
    assert "Test Result" in result.data
