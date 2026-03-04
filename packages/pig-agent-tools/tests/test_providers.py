"""Unit tests for search and reader provider implementations."""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pig_agent_tools.web.providers.base import (
    PageContent,
    ReaderProvider,
    SearchProvider,
    SearchResult,
)

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_search_result_defaults():
    r = SearchResult(title="T", url="http://x.com", snippet="S")
    assert r.score == 0.0
    assert r.extra == {}


def test_page_content_defaults():
    p = PageContent(url="http://x.com", content="hello")
    assert p.title == ""
    assert p.format == "text"


def test_search_provider_is_protocol():
    """Any object with a matching search() is a valid SearchProvider."""

    class MyProvider:
        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            return []

    assert isinstance(MyProvider(), SearchProvider)


def test_reader_provider_is_protocol():
    """Any object with a matching read() is a valid ReaderProvider."""

    class MyReader:
        async def read(self, url: str) -> PageContent:
            return PageContent(url=url, content="")

    assert isinstance(MyReader(), ReaderProvider)


# ---------------------------------------------------------------------------
# TavilyProvider
# ---------------------------------------------------------------------------


def _fake_tavily_module(search_response: dict):
    """Build a fake `tavily` sys.modules entry."""
    fake = ModuleType("tavily")
    client_instance = Mock()
    client_instance.search.return_value = search_response
    fake.TavilyClient = Mock(return_value=client_instance)
    return fake, client_instance


@pytest.mark.asyncio
async def test_tavily_provider_success():
    from pig_agent_tools.web.providers.tavily import TavilyProvider

    response = {
        "results": [
            {"title": "Result 1", "url": "https://a.com", "content": "Snippet 1", "score": 0.9},
            {"title": "Result 2", "url": "https://b.com", "content": "Snippet 2", "score": 0.7},
        ]
    }
    fake_tavily, client = _fake_tavily_module(response)
    sys.modules["tavily"] = fake_tavily
    try:
        provider = TavilyProvider(api_key="test-key")
        results = await provider.search("python", max_results=2)

        assert len(results) == 2
        assert results[0].title == "Result 1"
        assert results[0].url == "https://a.com"
        assert results[0].snippet == "Snippet 1"
        assert results[0].score == 0.9
        client.search.assert_called_once_with(query="python", max_results=2)
    finally:
        sys.modules.pop("tavily", None)


@pytest.mark.asyncio
async def test_tavily_provider_no_api_key():
    from pig_agent_tools.web.providers.tavily import TavilyProvider

    with patch.dict("os.environ", {}, clear=True):
        provider = TavilyProvider()
        with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
            await provider.search("test")


@pytest.mark.asyncio
async def test_tavily_provider_not_installed():
    from pig_agent_tools.web.providers.tavily import TavilyProvider

    sys.modules.pop("tavily", None)
    with patch.dict("sys.modules", {"tavily": None}):  # type: ignore[dict-item]
        provider = TavilyProvider(api_key="key")
        with pytest.raises(RuntimeError, match="pip install pig-agent-tools\\[tavily\\]"):
            await provider.search("test")


@pytest.mark.asyncio
async def test_tavily_provider_empty_results():
    from pig_agent_tools.web.providers.tavily import TavilyProvider

    fake_tavily, _ = _fake_tavily_module({"results": []})
    sys.modules["tavily"] = fake_tavily
    try:
        provider = TavilyProvider(api_key="key")
        results = await provider.search("test")
        assert results == []
    finally:
        sys.modules.pop("tavily", None)


# ---------------------------------------------------------------------------
# ExaProvider
# ---------------------------------------------------------------------------


def _fake_exa_module():
    """Build a fake `exa_py` sys.modules entry."""
    fake = ModuleType("exa_py")

    result1 = MagicMock()
    result1.title = "Exa Result 1"
    result1.url = "https://c.com"
    result1.highlights = ["highlight one", "highlight two"]
    result1.score = 0.85
    result1.published_date = "2025-01-01"

    result2 = MagicMock()
    result2.title = "Exa Result 2"
    result2.url = "https://d.com"
    result2.highlights = []
    result2.text = "Fallback text content"
    result2.score = 0.70
    result2.published_date = None

    response = MagicMock()
    response.results = [result1, result2]

    client_instance = MagicMock()
    client_instance.search_and_contents.return_value = response
    fake.Exa = Mock(return_value=client_instance)
    return fake, client_instance


@pytest.mark.asyncio
async def test_exa_provider_success():
    from pig_agent_tools.web.providers.exa import ExaProvider

    fake_exa, client = _fake_exa_module()
    sys.modules["exa_py"] = fake_exa
    try:
        provider = ExaProvider(api_key="test-key")
        results = await provider.search("semantic search", max_results=2)

        assert len(results) == 2
        assert results[0].title == "Exa Result 1"
        assert results[0].url == "https://c.com"
        assert "highlight one" in results[0].snippet
        assert results[0].score == 0.85
        # fallback to text when highlights is empty
        assert "Fallback text content" in results[1].snippet
        client.search_and_contents.assert_called_once_with(
            "semantic search", num_results=2, type="auto", highlights=True
        )
    finally:
        sys.modules.pop("exa_py", None)


@pytest.mark.asyncio
async def test_exa_provider_no_api_key():
    from pig_agent_tools.web.providers.exa import ExaProvider

    with patch.dict("os.environ", {}, clear=True):
        provider = ExaProvider()
        with pytest.raises(RuntimeError, match="EXA_API_KEY"):
            await provider.search("test")


@pytest.mark.asyncio
async def test_exa_provider_not_installed():
    from pig_agent_tools.web.providers.exa import ExaProvider

    sys.modules.pop("exa_py", None)
    with patch.dict("sys.modules", {"exa_py": None}):  # type: ignore[dict-item]
        provider = ExaProvider(api_key="key")
        with pytest.raises(RuntimeError, match="pip install pig-agent-tools\\[exa\\]"):
            await provider.search("test")


# ---------------------------------------------------------------------------
# get_default_provider
# ---------------------------------------------------------------------------


def test_get_default_provider_tavily(monkeypatch):
    from pig_agent_tools.web.providers import TavilyProvider, get_default_provider

    monkeypatch.setenv("TAVILY_API_KEY", "tav-key")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    provider = get_default_provider()
    assert isinstance(provider, TavilyProvider)


def test_get_default_provider_exa(monkeypatch):
    from pig_agent_tools.web.providers import ExaProvider, get_default_provider

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("EXA_API_KEY", "exa-key")
    provider = get_default_provider()
    assert isinstance(provider, ExaProvider)


def test_get_default_provider_tavily_takes_priority(monkeypatch):
    from pig_agent_tools.web.providers import TavilyProvider, get_default_provider

    monkeypatch.setenv("TAVILY_API_KEY", "tav-key")
    monkeypatch.setenv("EXA_API_KEY", "exa-key")
    provider = get_default_provider()
    assert isinstance(provider, TavilyProvider)


def test_get_default_provider_no_key(monkeypatch):
    from pig_agent_tools.web.providers import get_default_provider

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="No search provider configured"):
        get_default_provider()


# ---------------------------------------------------------------------------
# JinaReaderProvider
# ---------------------------------------------------------------------------


def _make_jina_httpx_mock(json_response: dict | None = None, text: str = ""):
    """Return a patched httpx.AsyncClient for Jina tests."""
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    if json_response is not None:
        mock_response.json.return_value = json_response
        mock_response.text = text
    else:
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = text

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.return_value = mock_response
    return mock_client


@pytest.mark.asyncio
async def test_jina_reader_success_json():
    from pig_agent_tools.web.providers.jina import JinaReaderProvider

    jina_json = {"data": {"title": "My Page", "content": "# Hello\nWorld"}}

    with patch("httpx.AsyncClient", return_value=_make_jina_httpx_mock(json_response=jina_json)):
        provider = JinaReaderProvider(api_key="test-key")
        page = await provider.read("https://example.com")

    assert page.content == "# Hello\nWorld"
    assert page.title == "My Page"
    assert page.format == "markdown"
    assert page.url == "https://example.com"


@pytest.mark.asyncio
async def test_jina_reader_success_text_fallback():
    """Falls back to response.text when JSON parsing fails."""
    from pig_agent_tools.web.providers.jina import JinaReaderProvider

    raw_text = "Plain text content from Jina"

    with patch("httpx.AsyncClient", return_value=_make_jina_httpx_mock(text=raw_text)):
        provider = JinaReaderProvider()
        page = await provider.read("https://example.com")

    assert page.content == raw_text


@pytest.mark.asyncio
async def test_jina_reader_with_api_key_sets_auth_header():
    """API key is sent as Authorization header."""
    from pig_agent_tools.web.providers.jina import JinaReaderProvider

    jina_json = {"data": {"title": "", "content": "content"}}
    mock_client = _make_jina_httpx_mock(json_response=jina_json)

    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = JinaReaderProvider(api_key="my-jina-key")
        await provider.read("https://example.com")

    _, call_kwargs = mock_client.get.call_args
    assert call_kwargs["headers"]["Authorization"] == "Bearer my-jina-key"


@pytest.mark.asyncio
async def test_jina_reader_http_error():
    import httpx
    from pig_agent_tools.web.providers.jina import JinaReaderProvider

    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.reason_phrase = "Too Many Requests"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "429", request=Mock(), response=mock_response
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = JinaReaderProvider()
        with pytest.raises(RuntimeError, match="429"):
            await provider.read("https://example.com")


@pytest.mark.asyncio
async def test_jina_reader_timeout():
    import httpx
    from pig_agent_tools.web.providers.jina import JinaReaderProvider

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.side_effect = httpx.TimeoutException("Timeout")

    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = JinaReaderProvider()
        with pytest.raises(RuntimeError, match="timed out"):
            await provider.read("https://example.com")


@pytest.mark.asyncio
async def test_jina_reader_content_truncation():
    from pig_agent_tools.web.providers.jina import JinaReaderProvider

    long_text = "A" * 15000
    jina_json = {"data": {"title": "", "content": long_text}}

    with patch("httpx.AsyncClient", return_value=_make_jina_httpx_mock(json_response=jina_json)):
        provider = JinaReaderProvider(max_content=10000)
        page = await provider.read("https://example.com")

    assert "[Content truncated...]" in page.content
    assert len(page.content) <= 10030


# ---------------------------------------------------------------------------
# HttpxBs4Provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_httpx_bs4_success():
    from pig_agent_tools.web.providers.httpx_bs4 import HttpxBs4Provider

    mock_html = """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <nav>Navigation</nav>
            <h1>Main Title</h1>
            <p>This is the main content.</p>
            <script>alert('x')</script>
            <footer>Footer</footer>
        </body>
    </html>
    """
    mock_response = Mock()
    mock_response.text = mock_html
    mock_response.raise_for_status = Mock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = HttpxBs4Provider()
        page = await provider.read("https://example.com")

    assert page.title == "Test Page"
    assert "Main Title" in page.content
    assert "main content" in page.content
    assert "Navigation" not in page.content
    assert "Footer" not in page.content
    assert "alert" not in page.content
    assert page.format == "text"


@pytest.mark.asyncio
async def test_httpx_bs4_http_error():
    import httpx
    from pig_agent_tools.web.providers.httpx_bs4 import HttpxBs4Provider

    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.reason_phrase = "Not Found"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "404", request=Mock(), response=mock_response
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = HttpxBs4Provider()
        with pytest.raises(RuntimeError, match="404"):
            await provider.read("https://example.com")


@pytest.mark.asyncio
async def test_httpx_bs4_content_truncation():
    from pig_agent_tools.web.providers.httpx_bs4 import HttpxBs4Provider

    long_text = "B" * 15000
    mock_html = f"<html><body><p>{long_text}</p></body></html>"
    mock_response = Mock()
    mock_response.text = mock_html
    mock_response.raise_for_status = Mock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        provider = HttpxBs4Provider(max_content=10000)
        page = await provider.read("https://example.com")

    assert "[Content truncated...]" in page.content
    assert len(page.content) <= 10030


# ---------------------------------------------------------------------------
# get_default_reader
# ---------------------------------------------------------------------------


def test_get_default_reader_returns_jina():
    from pig_agent_tools.web.providers import JinaReaderProvider, get_default_reader

    reader = get_default_reader()
    assert isinstance(reader, JinaReaderProvider)
