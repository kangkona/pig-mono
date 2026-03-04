"""Exa search provider.

Requires: pip install pig-agent-tools[exa]
API key:  EXA_API_KEY environment variable
Strengths: Semantic / similarity search, academic papers, technical docs
"""

import os

from .base import SearchResult


class ExaProvider:
    """Search provider backed by the Exa API.

    Exa uses neural embeddings to find semantically similar pages rather than
    keyword matches.  Best suited for research, finding related articles, and
    discovering technical documentation.

    Docs: https://docs.exa.ai
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("EXA_API_KEY")

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Search via Exa API.

        Args:
            query: Search query (natural language works best).
            max_results: Number of results to return.

        Returns:
            List of SearchResult objects.

        Raises:
            RuntimeError: If EXA_API_KEY is not set or the API call fails.
        """
        if not self._api_key:
            raise RuntimeError(
                "EXA_API_KEY environment variable not set. Get a key at https://dashboard.exa.ai"
            )

        try:
            from exa_py import Exa
        except ImportError as e:
            raise RuntimeError(
                "Exa package not installed. Install with: pip install pig-agent-tools[exa]"
            ) from e

        client = Exa(api_key=self._api_key)

        # Use auto mode so Exa picks keyword vs. neural search based on the query
        response = client.search_and_contents(
            query,
            num_results=max_results,
            type="auto",
            highlights=True,
        )

        results = []
        for item in response.results:
            snippet = ""
            if hasattr(item, "highlights") and item.highlights:
                snippet = " … ".join(item.highlights)
            elif hasattr(item, "text") and item.text:
                snippet = item.text[:500]

            results.append(
                SearchResult(
                    title=item.title or "",
                    url=item.url or "",
                    snippet=snippet,
                    score=item.score or 0.0,
                    extra={"published_date": getattr(item, "published_date", None)},
                )
            )
        return results
