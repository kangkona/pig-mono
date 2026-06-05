"""Integration tests for web-tool registration (``register_web_tools``)."""

import asyncio

from pig_agent_core.tools import _global_registry
from pig_agent_core.tools.web import register_web_tools
from pig_agent_core.tools.web.providers.base import SearchResult


def test_register_web_tools_with_global_registry():
    """Registering with no argument targets the global registry."""
    with _global_registry._lock:
        _global_registry._handlers.clear()
        _global_registry._schemas.clear()
        _global_registry._core_tools.clear()
        _global_registry._discovered.clear()

    registered = register_web_tools()

    assert "search_web" in registered
    assert "read_webpage" in registered
    assert len(registered) == 2

    with _global_registry._lock:
        assert "search_web" in _global_registry._handlers
        assert "read_webpage" in _global_registry._handlers
        assert "search_web" in _global_registry._schemas
        assert "read_webpage" in _global_registry._schemas


def test_register_web_tools_with_explicit_registry():
    """Registering with an explicit ToolRegistry populates it."""
    from pig_agent_core.tools.registry import ToolRegistry

    new_registry = ToolRegistry()
    registered = register_web_tools(new_registry)

    assert "search_web" in registered
    assert "read_webpage" in registered

    with new_registry._lock:
        assert "search_web" in new_registry._handlers
        assert "read_webpage" in new_registry._handlers


def test_register_web_tools_idempotent():
    """Registering twice is safe and returns the same names."""
    from pig_agent_core.tools.registry import ToolRegistry

    registry = ToolRegistry()

    registered1 = register_web_tools(registry)
    registered2 = register_web_tools(registry)

    assert registered1 == registered2

    with registry._lock:
        assert "search_web" in registry._handlers
        assert "read_webpage" in registry._handlers


def test_handlers_can_be_called_directly():
    """Handlers can be used without registration."""
    from pig_agent_core.tools.web import handle_search_web

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
