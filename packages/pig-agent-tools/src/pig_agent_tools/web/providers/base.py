"""Base protocol and data types for search providers."""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class SearchResult:
    """A single search result returned by a provider."""

    title: str
    url: str
    snippet: str
    score: float = 0.0
    extra: dict = field(default_factory=dict)


@runtime_checkable
class SearchProvider(Protocol):
    """Protocol for web search providers.

    Any class implementing ``search()`` with the correct signature is a valid
    SearchProvider — no inheritance required.
    """

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Search the web and return a list of results.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of SearchResult objects, ordered by relevance.

        Raises:
            RuntimeError: If the underlying API call fails.
        """
        ...
