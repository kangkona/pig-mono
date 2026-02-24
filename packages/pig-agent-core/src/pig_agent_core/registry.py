"""Tool registry for managing agent tools."""

from typing import Any, Optional
from .tools import Tool


class ToolRegistry:
    """Registry for managing agent tools."""

    def __init__(self):
        """Initialize tool registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool.

        Args:
            tool: Tool to register
        """
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name.

        Args:
            name: Tool name to unregister
        """
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool if found, None otherwise
        """
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools.

        Returns:
            List of tools
        """
        return list(self._tools.values())

    def get_schemas(self) -> list[dict[str, Any]]:
        """Get OpenAI schemas for all tools.

        Returns:
            List of tool schemas for LLM function calling
        """
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def execute(self, name: str, **kwargs) -> Any:
        """Execute a tool by name.

        Args:
            name: Tool name
            **kwargs: Tool arguments

        Returns:
            Tool execution result

        Raises:
            KeyError: If tool not found
        """
        tool = self.get(name)
        if not tool:
            raise KeyError(f"Tool '{name}' not found in registry")
        return tool.execute(**kwargs)

    async def aexecute(self, name: str, **kwargs) -> Any:
        """Async execute a tool by name.

        Args:
            name: Tool name
            **kwargs: Tool arguments

        Returns:
            Tool execution result

        Raises:
            KeyError: If tool not found
        """
        tool = self.get(name)
        if not tool:
            raise KeyError(f"Tool '{name}' not found in registry")
        return await tool.aexecute(**kwargs)

    def __len__(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools

    def __iter__(self):
        """Iterate over tools."""
        return iter(self._tools.values())
