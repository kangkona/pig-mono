"""Data models for LLM interactions."""

from typing import Any, Literal

from pydantic import BaseModel


class Message(BaseModel):
    """A message in a conversation."""

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str
    metadata: dict[str, Any] | None = None


class Response(BaseModel):
    """Response from an LLM completion."""

    content: str
    model: str
    usage: dict[str, int] | None = None
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


class StreamChunk(BaseModel):
    """A chunk from a streaming response.

    Text deltas arrive as ``content``. When a streaming response includes tool
    calls, the provider emits a final chunk carrying the fully-assembled
    ``tool_calls`` (canonical OpenAI shape: ``{"id","type":"function",
    "function":{"name","arguments"}}``).
    """

    content: str
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] | None = None
    metadata: dict[str, Any] | None = None


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
