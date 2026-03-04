"""Tavily search provider.

Requires: pip install pig-agent-tools[tavily]
API key:  TAVILY_API_KEY environment variable
Strengths: News, current events, fast Q&A
"""

import os

from .base import SearchResult


class TavilyProvider:
    """Search provider backed by the Tavily API.

    Tavily is optimised for AI agents — it returns clean, deduplicated
    summaries and filters out low-quality pages automatically.

    Docs: https://docs.tavily.com
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("TAVILY_API_KEY")

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Search via Tavily API.

        Args:
            query: Search query.
            max_results: Number of results (Tavily default max is 10).

        Returns:
            List of SearchResult objects.

        Raises:
            RuntimeError: If TAVILY_API_KEY is not set or the API call fails.
        """
        if not self._api_key:
            raise RuntimeError(
                "TAVILY_API_KEY environment variable not set. Get a key at https://app.tavily.com"
            )

        try:
            from tavily import TavilyClient
        except ImportError as e:
            raise RuntimeError(
                "Tavily package not installed. Install with: pip install pig-agent-tools[tavily]"
            ) from e

        client = TavilyClient(api_key=self._api_key)
        response = client.search(query=query, max_results=max_results)

        results = []
        for item in response.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    score=item.get("score", 0.0),
                )
            )
        return results
