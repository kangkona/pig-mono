"""Core tool handlers for agent reasoning and planning."""

import asyncio
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .base import ToolResult
from .schemas import get_all_schemas

# Handler registry
HANDLERS: dict[str, Any] = {}


def _register(name: str):
    """Decorator to register a tool handler.

    Args:
        name: Tool name

    Returns:
        Decorator function
    """

    def decorator(fn):
        HANDLERS[name] = fn
        return fn

    return decorator


@_register("think")
async def handle_think(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle think tool - internal reasoning.

    Args:
        args: Tool arguments with 'thought' field
        user_id: User ID
        meta: Metadata
        cancel: Cancellation event

    Returns:
        ToolResult with thinking status
    """
    thought = args.get("thought", "").strip()

    if not thought:
        return ToolResult(ok=False, error="Thought is required")

    # Just acknowledge the thought - it's recorded in the conversation
    return ToolResult(ok=True, data={"status": "ok", "thought_length": len(thought)})


@_register("plan")
async def handle_plan(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle plan tool - multi-step task planning.

    Args:
        args: Tool arguments with 'goal' and 'steps' fields
        user_id: User ID
        meta: Metadata
        cancel: Cancellation event

    Returns:
        ToolResult with plan validation and summary
    """
    goal = args.get("goal", "").strip()
    steps = args.get("steps", [])

    # Validate inputs
    if not goal:
        return ToolResult(ok=False, error="Goal is required")

    if not steps or not isinstance(steps, list):
        return ToolResult(ok=False, error="Steps are required and must be a list")

    if len(steps) == 0:
        return ToolResult(ok=False, error="At least one step is required")

    # Validate each step
    for i, step in enumerate(steps):
        if not isinstance(step, str) or not step.strip():
            return ToolResult(ok=False, error=f"Step {i + 1} must be a non-empty string")

    # Return plan summary
    return ToolResult(
        ok=True,
        data={
            "status": "planned",
            "goal": goal,
            "steps": steps,
            "total_steps": len(steps),
        },
    )


@_register("discover_tools")
async def handle_discover_tools(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle discover_tools - find and activate tools by keyword.

    Args:
        args: Tool arguments with 'query' field
        user_id: User ID
        meta: Metadata
        cancel: Cancellation event

    Returns:
        ToolResult with matched tools and activation list
    """
    query = (args.get("query") or "").strip().lower()

    # Get all available schemas
    all_schemas = get_all_schemas()

    # Build deferred tool index (non-core tools)
    from .schemas import CORE_TOOL_NAMES

    deferred_tools = {
        name: schema["function"]["description"].split("\n")[0]
        for name, schema in all_schemas.items()
        if name not in CORE_TOOL_NAMES
    }

    # If no query, return available tools
    if not query:
        return ToolResult(
            ok=True,
            data={
                "loaded": [],
                "available": deferred_tools,
                "hint": "Provide a keyword to search for tools (e.g., 'web', 'search', 'api')",
            },
        )

    # Match tools by keyword
    matched = {
        name: desc
        for name, desc in deferred_tools.items()
        if query in name.lower() or query in desc.lower()
    }

    if not matched:
        return ToolResult(
            ok=True,
            data={
                "loaded": [],
                "message": f"No tools matched '{query}'.",
                "available_categories": "web, search, api",
            },
        )

    # Return matched tools with activation list
    return ToolResult(
        ok=True,
        data={
            "loaded": [{"name": n, "description": d} for n, d in matched.items()],
            "_activate": list(matched.keys()),  # Internal field for registry
        },
    )


@_register("get_current_time")
async def handle_get_current_time(
    args: dict, user_id: str, meta: dict, cancel: asyncio.Event | None = None
) -> ToolResult:
    """Handle get_current_time - get current date and time with timezone.

    Args:
        args: Tool arguments with optional 'timezone' field
        user_id: User ID
        meta: Metadata
        cancel: Cancellation event

    Returns:
        ToolResult with ISO 8601 formatted datetime
    """
    timezone_name = (args.get("timezone") or "UTC").strip()

    try:
        # Parse timezone
        if timezone_name.upper() == "UTC":
            tz = timezone.utc
            now = datetime.now(tz)
        else:
            tz_info = ZoneInfo(timezone_name)
            now = datetime.now(tz_info)

        # Format as ISO 8601
        iso_time = now.isoformat()

        return ToolResult(
            ok=True,
            data={
                "datetime": iso_time,
                "timezone": timezone_name,
                "timestamp": int(now.timestamp()),
            },
        )
    except Exception as e:
        return ToolResult(
            ok=False,
            error=f"Invalid timezone '{timezone_name}': {e}",
        )
