"""Base protocols and data types for web tool providers."""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A single search result returned by a search provider."""

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


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


@dataclass
class PageContent:
    """Extracted content from a webpage."""

    url: str
    content: str
    title: str = ""
    format: str = "text"


@runtime_checkable
class ReaderProvider(Protocol):
    """Protocol for webpage reader providers.

    Any class implementing ``read()`` with the correct signature is a valid
    ReaderProvider — no inheritance required.
    """

    async def read(self, url: str) -> PageContent:
        """Fetch a URL and return its text content.

        Args:
            url: The webpage URL (must start with http:// or https://).

        Returns:
            PageContent with extracted text.

        Raises:
            RuntimeError: If the fetch or parsing fails.
        """
        ...
