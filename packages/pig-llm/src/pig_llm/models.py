"""Data models for LLM interactions."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    """A message in a conversation."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    metadata: Optional[dict[str, Any]] = None


class Response(BaseModel):
    """Response from an LLM completion."""

    content: str
    model: str
    usage: Optional[dict[str, int]] = None
    finish_reason: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    metadata: Optional[dict[str, Any]] = None


class StreamChunk(BaseModel):
    """A chunk from a streaming response."""

    content: str
    finish_reason: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        """Add two usage objects together."""
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )
