"""httpx + BeautifulSoup webpage reader provider.

Self-contained: fetches the raw HTML and strips it locally.
Works without any external API — good for intranets or when you
prefer not to route page content through a third-party service.

Requires: pip install pig-agent-tools[web]  (httpx + beautifulsoup4)
"""

from .base import PageContent

_MAX_CONTENT = 10_000
_STRIP_TAGS = ["script", "style", "nav", "footer", "header"]


class HttpxBs4Provider:
    """Webpage reader that fetches raw HTML with httpx and parses it with BeautifulSoup.

    This is the original self-hosted implementation.  It does not handle
    JavaScript-rendered pages; use JinaReaderProvider for those.
    """

    def __init__(self, max_content: int = _MAX_CONTENT) -> None:
        self._max_content = max_content

    async def read(self, url: str) -> PageContent:
        """Fetch the URL, strip boilerplate, and return plain text.

        Args:
            url: Target URL (must start with http:// or https://).

        Returns:
            PageContent with plain-text content.

        Raises:
            RuntimeError: On HTTP errors, timeouts, or import failures.
        """
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise RuntimeError(
                "Required packages not installed. Install with: pip install httpx beautifulsoup4"
            ) from e

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"HTTP error {e.response.status_code}: {e.response.reason_phrase}"
            ) from e
        except httpx.TimeoutException as e:
            raise RuntimeError("Request timed out after 30 seconds") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error: {e}") from e

        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        for tag in soup(_STRIP_TAGS):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        content = "\n".join(lines)

        if not content:
            raise RuntimeError("No text content found on webpage")

        if len(content) > self._max_content:
            content = content[: self._max_content] + "\n\n[Content truncated...]"

        return PageContent(url=url, content=content, title=title, format="text")
