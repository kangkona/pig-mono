"""Web tools for agents."""

from .handlers import HANDLERS, handle_read_webpage, handle_search_web
from .providers import (
    ExaProvider,
    SearchProvider,
    SearchResult,
    TavilyProvider,
    get_default_provider,
)
from .schemas import TOOL_SCHEMAS


def register_tools(registry=None):
    """Register web tools with a ToolRegistry.

    Args:
        registry: Optional ToolRegistry instance. If None, registers with global registry.
                 Supports both old ToolRegistry (from pig_agent_core.registry) and
                 new ToolRegistry (from pig_agent_core.tools.registry).

    Returns:
        List of registered tool names
    """
    if registry is None:
        from pig_agent_core.tools import _global_registry

        registry = _global_registry

    registered = []

    # Check if this is the new ToolRegistry (has _handlers attribute)
    # or old ToolRegistry (has _tools attribute)
    if hasattr(registry, "_handlers"):
        # New ToolRegistry API
        for schema in TOOL_SCHEMAS:
            tool_name = schema["function"]["name"]
            handler = HANDLERS.get(tool_name)
            if handler:
                registry.register(
                    name=tool_name,
                    handler=handler,
                    schema=schema,
                    is_core=False,  # Web tools are not core tools
                    timeout=30.0,
                )
                registered.append(tool_name)
    elif hasattr(registry, "_tools"):
        # Old ToolRegistry API - needs Tool objects
        # We can't easily convert handlers to Tool objects without the old Tool class
        # So we'll raise an error with a helpful message
        raise TypeError(
            "The provided registry uses the old ToolRegistry API which requires Tool objects. "
            "Web tools use the new handler-based API. "
            "Please use the new ToolRegistry from pig_agent_core.tools.registry, "
            "or update your Agent to use the new registry system."
        )
    else:
        raise TypeError(f"Unknown registry type: {type(registry)}")

    return registered


__all__ = [
    "handle_search_web",
    "handle_read_webpage",
    "HANDLERS",
    "TOOL_SCHEMAS",
    "register_tools",
    "SearchProvider",
    "SearchResult",
    "TavilyProvider",
    "ExaProvider",
    "get_default_provider",
]
