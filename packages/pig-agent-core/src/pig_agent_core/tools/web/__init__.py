"""Web tools for agents."""

from .handlers import HANDLERS, handle_read_webpage, handle_search_web
from .providers import (
    ExaProvider,
    HttpxBs4Provider,
    JinaReaderProvider,
    PageContent,
    ReaderProvider,
    SearchProvider,
    SearchResult,
    TavilyProvider,
    get_default_provider,
    get_default_reader,
)
from .schemas import TOOL_SCHEMAS


def register_web_tools(registry=None) -> list[str]:
    """Register the web tools (``search_web``, ``read_webpage``) on a ToolRegistry.

    Args:
        registry: Target ``ToolRegistry``. Defaults to the global registry
            (``pig_agent_core.tools._global_registry``).

    Returns:
        The list of registered tool names.
    """
    if registry is None:
        from pig_agent_core.tools import _global_registry

        registry = _global_registry

    # Web tools are optional (not core) — load only when this is called.
    return registry.register_package(
        TOOL_SCHEMAS,
        HANDLERS,
        is_core=False,
        timeout=30.0,
    )


__all__ = [
    # Handlers
    "handle_search_web",
    "handle_read_webpage",
    "HANDLERS",
    "TOOL_SCHEMAS",
    "register_web_tools",
    # Search
    "SearchProvider",
    "SearchResult",
    "TavilyProvider",
    "ExaProvider",
    "get_default_provider",
    # Reader
    "ReaderProvider",
    "PageContent",
    "JinaReaderProvider",
    "HttpxBs4Provider",
    "get_default_reader",
]
