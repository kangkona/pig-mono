"""Unit tests for search provider implementations."""

import sys
from types import ModuleType
from unittest.mock import MagicMock, Mock, patch

import pytest
from pig_agent_tools.web.providers.base import SearchProvider, SearchResult

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_search_result_defaults():
    r = SearchResult(title="T", url="http://x.com", snippet="S")
    assert r.score == 0.0
    assert r.extra == {}


def test_search_provider_is_protocol():
    """Any object with a matching search() is a valid SearchProvider."""

    class MyProvider:
        async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
            return []

    assert isinstance(MyProvider(), SearchProvider)


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
