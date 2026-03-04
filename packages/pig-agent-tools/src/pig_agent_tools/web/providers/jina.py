"""Jina Reader provider for webpage content extraction.

No package installation required — uses httpx (already a project dep).
API key optional: free tier available without registration.

Requires: httpx (already included in pig-agent-tools dev deps)
API key:  JINA_API_KEY environment variable (optional, increases rate limits)
Docs:     https://jina.ai/reader
"""

import os

from .base import PageContent

_JINA_BASE = "https://r.jina.ai/"
_MAX_CONTENT = 10_000


class JinaReaderProvider:
    """Webpage reader backed by Jina Reader API.

    Jina Reader fetches a URL and returns clean, LLM-ready Markdown.
    It handles JavaScript-rendered pages, paywalls, and complex layouts
    much better than a raw HTML parser.

    Free tier: no API key required, 500 RPM.
    Paid tier: set JINA_API_KEY for higher rate limits (10 000 RPM).

    Docs: https://jina.ai/reader
    """

    def __init__(self, api_key: str | None = None, max_content: int = _MAX_CONTENT) -> None:
        self._api_key = api_key or os.getenv("JINA_API_KEY")
        self._max_content = max_content

    async def read(self, url: str) -> PageContent:
        """Fetch and return the page content via Jina Reader.

        Args:
            url: The target URL (must start with http:// or https://).

        Returns:
            PageContent with Markdown-formatted text.

        Raises:
            RuntimeError: On HTTP errors or network failures.
        """
        try:
            import httpx
        except ImportError as e:
            raise RuntimeError("httpx is required. Install with: pip install httpx") from e

        jina_url = f"{_JINA_BASE}{url}"

        headers = {
            "Accept": "application/json",
            "X-Return-Format": "markdown",
            "X-Timeout": "30",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                response = await client.get(jina_url, headers=headers, follow_redirects=True)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"HTTP error {e.response.status_code}: {e.response.reason_phrase}"
            ) from e
        except httpx.TimeoutException as e:
            raise RuntimeError("Request timed out after 30 seconds") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error: {e}") from e

        # Jina returns JSON when Accept: application/json is set
        try:
            data = response.json()
            content = data.get("data", {}).get("content", "") or response.text
            title = data.get("data", {}).get("title", "")
        except Exception:
            content = response.text
            title = ""

        if not content or not content.strip():
            raise RuntimeError("No content returned by Jina Reader")

        if len(content) > self._max_content:
            content = content[: self._max_content] + "\n\n[Content truncated...]"

        return PageContent(url=url, content=content.strip(), title=title, format="markdown")
