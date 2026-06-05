"""Web tool provider implementations."""

from .base import PageContent, ReaderProvider, SearchProvider, SearchResult
from .exa import ExaProvider
from .httpx_bs4 import HttpxBs4Provider
from .jina import JinaReaderProvider
from .tavily import TavilyProvider


def get_default_provider() -> "SearchProvider":
    """Auto-detect and return the best available search provider.

    Checks environment variables in priority order:
    1. TAVILY_API_KEY  → TavilyProvider
    2. EXA_API_KEY     → ExaProvider

    Raises:
        RuntimeError: If no provider API key is configured.
    """
    import os

    if os.getenv("TAVILY_API_KEY"):
        return TavilyProvider()
    if os.getenv("EXA_API_KEY"):
        return ExaProvider()
    raise RuntimeError(
        "No search provider configured. Set TAVILY_API_KEY or EXA_API_KEY environment variable."
    )


def get_default_reader() -> "ReaderProvider":
    """Return the default reader provider (JinaReaderProvider).

    JinaReaderProvider is always available — no API key required for the
    free tier.  Set JINA_API_KEY to increase rate limits.
    """
    return JinaReaderProvider()


__all__ = [
    # Protocols & data types
    "SearchProvider",
    "SearchResult",
    "ReaderProvider",
    "PageContent",
    # Search providers
    "TavilyProvider",
    "ExaProvider",
    # Reader providers
    "JinaReaderProvider",
    "HttpxBs4Provider",
    # Factory helpers
    "get_default_provider",
    "get_default_reader",
]
