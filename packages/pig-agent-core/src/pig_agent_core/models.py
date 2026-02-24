"""Data models for agent runtime."""

from typing import Any, Optional
from pydantic import BaseModel, Field


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
    error: Optional[str] = None
    success: bool = True


class AgentState(BaseModel):
    """State of an agent."""

    name: str
    system_prompt: Optional[str] = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True
