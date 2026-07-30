"""Data models for LLM interactions."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class TurnOutcome(str, Enum):
    """Provider-neutral reason why an LLM turn stopped producing work."""

    COMPLETED = "completed"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    ABORTED = "aborted"
    PROVIDER_ERROR = "provider_error"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"

    @property
    def successful(self) -> bool:
        """Return whether the outcome is a valid completed agent round."""
        return self in {TurnOutcome.COMPLETED, TurnOutcome.TOOL_CALLS}


_COMPLETED_REASONS = {
    "stop",
    "end_turn",
    "complete",
    "completed",
    "stop_sequence",
    "natural",
    "success",
    "done",
}
_TOOL_REASONS = {"tool_calls", "tool_use", "function_call", "function_calls"}
_LENGTH_REASONS = {
    "length",
    "max_tokens",
    "max_output_tokens",
    "model_length",
    "token_limit",
}
_FILTER_REASONS = {"content_filter", "safety", "blocked", "recitation", "prohibited"}
_ABORT_REASONS = {"aborted", "cancelled", "canceled", "interrupt", "interrupted"}
_ERROR_REASONS = {"error", "failed", "failure", "provider_error"}


def resolve_turn_outcome(
    finish_reason: str | None,
    tool_calls: list[dict[str, Any]] | None,
    candidate: TurnOutcome | None = None,
) -> TurnOutcome:
    """Resolve one full round, giving adverse terminal evidence precedence."""
    normalized = normalize_finish_reason(finish_reason)
    adverse = {
        TurnOutcome.LENGTH,
        TurnOutcome.CONTENT_FILTER,
        TurnOutcome.ABORTED,
        TurnOutcome.PROVIDER_ERROR,
        TurnOutcome.UNKNOWN,
    }
    if finish_reason is not None and normalized in adverse:
        return normalized
    if finish_reason is None and candidate in adverse:
        return candidate
    if tool_calls:
        return TurnOutcome.TOOL_CALLS
    if finish_reason is not None:
        return normalized
    return candidate or TurnOutcome.INCOMPLETE


def normalize_finish_reason(reason: str | None) -> TurnOutcome:
    """Normalize a provider finish reason while leaving its raw value available."""
    if reason is None:
        return TurnOutcome.INCOMPLETE
    normalized = reason.strip().lower().rsplit(".", maxsplit=1)[-1]
    if normalized in _COMPLETED_REASONS:
        return TurnOutcome.COMPLETED
    if normalized in _TOOL_REASONS:
        return TurnOutcome.TOOL_CALLS
    if normalized in _LENGTH_REASONS:
        return TurnOutcome.LENGTH
    if normalized in _FILTER_REASONS:
        return TurnOutcome.CONTENT_FILTER
    if normalized in _ABORT_REASONS:
        return TurnOutcome.ABORTED
    if normalized in _ERROR_REASONS:
        return TurnOutcome.PROVIDER_ERROR
    return TurnOutcome.UNKNOWN


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

    @property
    def raw_finish_reason(self) -> str | None:
        """Return the provider value without normalization."""
        return self.finish_reason

    @property
    def outcome(self) -> TurnOutcome:
        """Return the provider-neutral terminal outcome."""
        return resolve_turn_outcome(self.finish_reason, self.tool_calls)


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

    @property
    def raw_finish_reason(self) -> str | None:
        """Return the provider value without normalization."""
        return self.finish_reason

    @property
    def outcome(self) -> TurnOutcome | None:
        """Return an outcome only for terminal/tool-call chunks."""
        if self.finish_reason is None and not self.tool_calls:
            return None
        return resolve_turn_outcome(self.finish_reason, self.tool_calls)


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
