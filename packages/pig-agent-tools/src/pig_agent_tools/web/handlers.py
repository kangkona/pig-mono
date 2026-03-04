"""Web tool handlers."""

from typing import Any

from pig_agent_core.tools.base import ToolResult

from .providers.base import SearchProvider


async def handle_search_web(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: Any = None,
    provider: SearchProvider | None = None,
) -> ToolResult:
    """Search the web and return formatted results.

    The ``provider`` argument selects the search backend.  When omitted the
    best available provider is auto-detected from environment variables
    (TAVILY_API_KEY → Tavily, EXA_API_KEY → Exa).

    Args:
        args: Tool arguments — ``query`` (required), ``max_results`` (default 5).
        user_id: Optional user identifier passed by the agent runtime.
        meta: Optional metadata passed by the agent runtime.
        cancel: Optional cancellation token passed by the agent runtime.
        provider: Explicit search provider instance.  Useful for testing and
            for scenarios where the caller wants to control the backend.

    Returns:
        ToolResult with a formatted string of results on success.
    """
    query = args.get("query", "")
    max_results = args.get("max_results", 5)

    if not query:
        return ToolResult(ok=False, error="Query parameter is required")

    try:
        if provider is None:
            from .providers import get_default_provider

            provider = get_default_provider()

        results = await provider.search(query, max_results=max_results)

        if not results:
            return ToolResult(ok=True, data="No results found")

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.title}\n   URL: {r.url}\n   {r.snippet}\n")

        return ToolResult(ok=True, data="\n".join(lines))

    except RuntimeError as e:
        return ToolResult(ok=False, error=str(e))
    except Exception as e:
        return ToolResult(ok=False, error=f"Search failed: {e}")


async def handle_read_webpage(
    args: dict[str, Any],
    user_id: str | None = None,
    meta: dict[str, Any] | None = None,
    cancel: Any = None,
) -> ToolResult:
    """Read and extract text content from a webpage.

    Args:
        args: Tool arguments — ``url`` (required).
        user_id: Optional user identifier passed by the agent runtime.
        meta: Optional metadata passed by the agent runtime.
        cancel: Optional cancellation token passed by the agent runtime.

    Returns:
        ToolResult with extracted page text on success.
    """
    url = args.get("url", "")

    if not url:
        return ToolResult(ok=False, error="URL parameter is required")

    if not url.startswith(("http://", "https://")):
        return ToolResult(ok=False, error="URL must start with http:// or https://")

    try:
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError:
            return ToolResult(
                ok=False,
                error=(
                    "Required packages not installed. "
                    "Install with: pip install httpx beautifulsoup4"
                ),
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        content = "\n".join(lines)

        if not content:
            return ToolResult(ok=False, error="No text content found on webpage")

        max_length = 10000
        if len(content) > max_length:
            content = content[:max_length] + "\n\n[Content truncated...]"

        return ToolResult(ok=True, data=content)

    except httpx.HTTPStatusError as e:
        return ToolResult(
            ok=False,
            error=f"HTTP error {e.response.status_code}: {e.response.reason_phrase}",
        )
    except httpx.TimeoutException:
        return ToolResult(ok=False, error="Request timed out after 30 seconds")
    except Exception as e:
        return ToolResult(ok=False, error=f"Failed to read webpage: {e}")


HANDLERS = {
    "search_web": handle_search_web,
    "read_webpage": handle_read_webpage,
}
