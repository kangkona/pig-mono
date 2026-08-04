"""Tool system for agents."""

from .base import CancelledError, ToolResult
from .contracts import GrammarType, StrictJsonMode, ToolCapabilityError, prepare_tool_schema
from .handlers_core import HANDLERS
from .legacy import Tool, tool
from .registry import ToolRegistry
from .schemas import CORE_TOOL_NAMES, TOOL_BUDGETS, TOOL_PERMISSIONS, TOOL_SCHEMAS

# Global registry for external tool registration
# External packages can import this and register their tools
_global_registry = ToolRegistry()

__all__ = [
    "Tool",  # Old Tool class for backward compatibility
    "tool",  # Old tool decorator for backward compatibility
    "ToolResult",
    "CancelledError",
    "ToolCapabilityError",
    "StrictJsonMode",
    "GrammarType",
    "prepare_tool_schema",
    "ToolRegistry",
    "HANDLERS",
    "CORE_TOOL_NAMES",
    "TOOL_SCHEMAS",
    "TOOL_PERMISSIONS",
    "TOOL_BUDGETS",
]
