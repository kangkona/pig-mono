"""Tests for web tool handlers."""

from unittest.mock import patch

import pytest
from pig_agent_tools.web.handlers import handle_read_webpage, handle_search_web
from pig_agent_tools.web.providers.base import SearchResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(*results: SearchResult):
    """Return a mock SearchProvider that yields the given results."""

    class _Provider:
        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            return list(results)

    return _Provider()


def _failing_provider(message: str):
    """Return a mock SearchProvider that raises RuntimeError."""

    class _Provider:
        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            raise RuntimeError(message)

    return _Provider()


# ---------------------------------------------------------------------------
# handle_search_web
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_web_success():
    """Successful search returns formatted results."""
    r1 = SearchResult(
        title="Python Tutorial", url="https://example.com/python", snippet="Learn Python"
    )  # noqa: E501
    r2 = SearchResult(title="Python Docs", url="https://docs.python.org", snippet="Official docs")
    provider = _make_provider(r1, r2)

    result = await handle_search_web(
        {"query": "Python tutorials", "max_results": 2}, provider=provider
    )

    assert result.ok
    assert "Python Tutorial" in result.data
    assert "https://example.com/python" in result.data
    assert "Learn Python" in result.data


@pytest.mark.asyncio
async def test_search_web_missing_query():
    """Missing query returns an error."""
    result = await handle_search_web({})

    assert not result.ok
    assert "Query parameter is required" in result.error


@pytest.mark.asyncio
async def test_search_web_no_results():
    """Empty result list returns a friendly message."""
    provider = _make_provider()

    result = await handle_search_web({"query": "nonexistent query"}, provider=provider)

    assert result.ok
    assert "No results found" in result.data


@pytest.mark.asyncio
async def test_search_web_provider_error():
    """Provider RuntimeError surfaces as ToolResult error."""
    provider = _failing_provider("TAVILY_API_KEY environment variable not set")

    result = await handle_search_web({"query": "test"}, provider=provider)

    assert not result.ok
    assert "TAVILY_API_KEY" in result.error


@pytest.mark.asyncio
async def test_search_web_provider_unexpected_exception():
    """Unexpected exceptions are wrapped as 'Search failed'."""

    class _BrokenProvider:
        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            raise ValueError("unexpected!")

    result = await handle_search_web({"query": "test"}, provider=_BrokenProvider())

    assert not result.ok
    assert "Search failed" in result.error


@pytest.mark.asyncio
async def test_search_web_auto_detects_provider_no_key():
    """Without any API key, auto-detection raises RuntimeError → ToolResult error."""
    with patch.dict("os.environ", {}, clear=True):
        result = await handle_search_web({"query": "test"})

    assert not result.ok
    assert "No search provider configured" in result.error


# ---------------------------------------------------------------------------
# handle_read_webpage — uses injected ReaderProvider for full isolation
# ---------------------------------------------------------------------------


def _make_reader(content: str, title: str = ""):
    """Return a mock ReaderProvider that yields the given content."""
    from pig_agent_tools.web.providers.base import PageContent

    class _Reader:
        async def read(self, url: str) -> PageContent:
            return PageContent(url=url, content=content, title=title)

    return _Reader()


def _failing_reader(message: str):
    """Return a mock ReaderProvider that raises RuntimeError."""

    class _Reader:
        async def read(self, url: str):
            raise RuntimeError(message)

    return _Reader()


@pytest.mark.asyncio
async def test_read_webpage_success():
    """Successful page read returns content from provider."""
    reader = _make_reader("Main Title\nThis is the main content.", title="Test Page")
    result = await handle_read_webpage({"url": "https://example.com"}, reader=reader)

    assert result.ok
    assert "Main Title" in result.data
    assert "main content" in result.data


@pytest.mark.asyncio
async def test_read_webpage_missing_url():
    result = await handle_read_webpage({})
    assert not result.ok
    assert "URL parameter is required" in result.error


@pytest.mark.asyncio
async def test_read_webpage_invalid_url():
    result = await handle_read_webpage({"url": "not-a-url"})
    assert not result.ok
    assert "must start with http" in result.error


@pytest.mark.asyncio
async def test_read_webpage_provider_error():
    """RuntimeError from provider surfaces as ToolResult error."""
    reader = _failing_reader("HTTP error 404: Not Found")
    result = await handle_read_webpage({"url": "https://example.com/notfound"}, reader=reader)

    assert not result.ok
    assert "404" in result.error


@pytest.mark.asyncio
async def test_read_webpage_timeout_error():
    reader = _failing_reader("Request timed out after 30 seconds")
    result = await handle_read_webpage({"url": "https://example.com"}, reader=reader)

    assert not result.ok
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_read_webpage_content_truncation():
    """Content truncation is handled inside the provider; handler passes through."""
    long_content = "A" * 9500 + "\n\n[Content truncated...]"
    reader = _make_reader(long_content)
    result = await handle_read_webpage({"url": "https://example.com"}, reader=reader)

    assert result.ok
    assert "[Content truncated...]" in result.data
