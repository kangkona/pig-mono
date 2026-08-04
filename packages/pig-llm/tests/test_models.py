"""Tests for data models."""

import pytest
from pig_llm.models import (
    Message,
    Response,
    StreamChunk,
    TurnOutcome,
    Usage,
    normalize_finish_reason,
)


def test_message_creation() -> None:
    """Test message creation."""
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"
    assert msg.metadata is None


def test_message_with_metadata() -> None:
    """Test message with metadata."""
    msg = Message(role="assistant", content="Hi", metadata={"model": "gpt-4"})
    assert msg.metadata is not None
    assert msg.metadata["model"] == "gpt-4"


def test_response_creation() -> None:
    """Test response creation."""
    response = Response(
        content="Hello world",
        model="gpt-3.5-turbo",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    assert response.content == "Hello world"
    assert response.model == "gpt-3.5-turbo"
    assert response.usage is not None
    assert response.usage["total_tokens"] == 15


def test_stream_chunk() -> None:
    """Test stream chunk."""
    chunk = StreamChunk(content="Hello", finish_reason=None)
    assert chunk.content == "Hello"
    assert chunk.finish_reason is None
    assert chunk.outcome is None


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("stop", TurnOutcome.COMPLETED),
        ("end_turn", TurnOutcome.COMPLETED),
        ("FinishReason.STOP", TurnOutcome.COMPLETED),
        ("tool_calls", TurnOutcome.TOOL_CALLS),
        ("tool_use", TurnOutcome.TOOL_CALLS),
        ("length", TurnOutcome.LENGTH),
        ("MAX_TOKENS", TurnOutcome.LENGTH),
        ("content_filter", TurnOutcome.CONTENT_FILTER),
        ("SAFETY", TurnOutcome.CONTENT_FILTER),
        ("cancelled", TurnOutcome.ABORTED),
        ("error", TurnOutcome.PROVIDER_ERROR),
        ("vendor_specific_reason", TurnOutcome.UNKNOWN),
        (None, TurnOutcome.INCOMPLETE),
    ],
)
def test_finish_reason_normalization(reason: str | None, expected: TurnOutcome) -> None:
    assert normalize_finish_reason(reason) is expected


def test_response_and_stream_chunk_expose_provider_neutral_outcomes() -> None:
    response = Response(content="partial", model="m", finish_reason="length")
    terminal = StreamChunk(content="", finish_reason="content_filter")
    tool_chunk = StreamChunk(content="", tool_calls=[{"id": "call-1"}])

    assert response.outcome is TurnOutcome.LENGTH
    assert response.raw_finish_reason == "length"
    assert terminal.outcome is TurnOutcome.CONTENT_FILTER
    assert terminal.raw_finish_reason == "content_filter"
    assert tool_chunk.outcome is TurnOutcome.TOOL_CALLS


def test_adverse_terminal_reason_overrides_partial_tool_calls() -> None:
    tool_calls = [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "write_file", "arguments": '{"path":"part'},
        }
    ]
    response = Response(
        content="",
        model="m",
        finish_reason="length",
        tool_calls=tool_calls,
    )
    chunk = StreamChunk(
        content="",
        finish_reason="content_filter",
        tool_calls=tool_calls,
    )

    assert response.outcome is TurnOutcome.LENGTH
    assert chunk.outcome is TurnOutcome.CONTENT_FILTER


def test_usage_addition() -> None:
    """Test usage addition."""
    usage1 = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    usage2 = Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30)

    total = usage1 + usage2
    assert total.prompt_tokens == 30
    assert total.completion_tokens == 15
    assert total.total_tokens == 45


def test_invalid_message_role() -> None:
    """Test invalid message role."""
    with pytest.raises(ValueError):
        Message.model_validate({"role": "invalid", "content": "test"})
