"""Web tool handlers."""

from typing import Any

from pig_agent_core.tools.base import ToolResult

from .providers.base import ReaderProvider, SearchProvider


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
    reader: ReaderProvider | None = None,
) -> ToolResult:
    """Fetch a webpage and return its text content.

    The ``reader`` argument selects the extraction backend:

    - ``JinaReaderProvider`` (default) — routes through Jina Reader API,
      returns clean Markdown, handles JS-rendered pages, free without a key.
    - ``HttpxBs4Provider`` — fetches raw HTML locally, strips boilerplate
      with BeautifulSoup.  No external API, but cannot run JS.

    Args:
        args: Tool arguments — ``url`` (required).
        user_id: Optional user identifier passed by the agent runtime.
        meta: Optional metadata passed by the agent runtime.
        cancel: Optional cancellation token passed by the agent runtime.
        reader: Explicit reader provider instance.

    Returns:
        ToolResult with extracted page text on success.
    """
    url = args.get("url", "")

    if not url:
        return ToolResult(ok=False, error="URL parameter is required")

    if not url.startswith(("http://", "https://")):
        return ToolResult(ok=False, error="URL must start with http:// or https://")

    try:
        if reader is None:
            from .providers.jina import JinaReaderProvider

            reader = JinaReaderProvider()

        page = await reader.read(url)
        return ToolResult(ok=True, data=page.content)

    except RuntimeError as e:
        return ToolResult(ok=False, error=str(e))
    except Exception as e:
        return ToolResult(ok=False, error=f"Failed to read webpage: {e}")


HANDLERS = {
    "search_web": handle_search_web,
    "read_webpage": handle_read_webpage,
}
