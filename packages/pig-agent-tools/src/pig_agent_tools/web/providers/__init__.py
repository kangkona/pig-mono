"""Search provider implementations."""

from .base import SearchProvider, SearchResult
from .exa import ExaProvider
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


__all__ = [
    "SearchProvider",
    "SearchResult",
    "TavilyProvider",
    "ExaProvider",
    "get_default_provider",
]
