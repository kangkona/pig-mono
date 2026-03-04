"""Tool system for agents."""

from .base import CancelledError, ToolResult
from .handlers_core import HANDLERS
from .registry import ToolRegistry
from .schemas import CORE_TOOL_NAMES, TOOL_BUDGETS, TOOL_PERMISSIONS, TOOL_SCHEMAS

# Global registry for external tool registration
# External packages can import this and register their tools
_global_registry = ToolRegistry()

# Import old Tool class and tool decorator from parent tools.py for backward compatibility
import sys
from pathlib import Path

# Get the parent package directory
parent_dir = Path(__file__).parent.parent
tools_py = parent_dir / "tools.py"

# Import Tool and tool from tools.py
if tools_py.exists():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_tools_module", tools_py)
    if spec and spec.loader:
        _tools_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_tools_module)
        Tool = _tools_module.Tool
        tool = _tools_module.tool
    else:
        Tool = None
        tool = None
else:
    Tool = None
    tool = None

__all__ = [
    "Tool",  # Old Tool class for backward compatibility
    "tool",  # Old tool decorator for backward compatibility
    "ToolResult",
    "CancelledError",
    "ToolRegistry",
    "HANDLERS",
    "CORE_TOOL_NAMES",
    "TOOL_SCHEMAS",
    "TOOL_PERMISSIONS",
    "TOOL_BUDGETS",
]
