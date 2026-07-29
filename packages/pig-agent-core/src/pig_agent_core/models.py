"""Data models for agent runtime."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolModelCapabilities(BaseModel):
    """Model/provider capabilities that affect tool definition rendering.

    This deliberately describes wire-level abilities rather than naming a
    provider.  Provider adapters can construct it from their own model catalog
    and ask the tool registry for definitions that are safe to send.
    """

    supports_strict_tools: bool = False
    supported_grammar_tools: set[Literal["regex", "lark"]] = Field(default_factory=set)
    supports_deferred_tools: bool = False


class ToolCall(BaseModel):
    """Represents a tool call request from LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """Result of a tool execution."""

    tool_call_id: str
    name: str
    result: Any
    error: str | None = None
    success: bool = True
    added_tool_names: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """State of an agent."""

    name: str
    system_prompt: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True
