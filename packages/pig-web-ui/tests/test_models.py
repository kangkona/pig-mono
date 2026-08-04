"""Tests for web UI models."""

from typing import Literal, cast

import pytest
from pig_web_ui.models import ChatMessage, ChatRequest, ChatResponse, StreamChunk


def test_chat_message_creation() -> None:
    """Test creating a chat message."""
    msg = ChatMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"
    assert msg.timestamp is None


def test_chat_message_with_timestamp() -> None:
    """Test chat message with timestamp."""
    msg = ChatMessage(
        role="assistant",
        content="Hi",
        timestamp="2024-01-01T00:00:00",
    )
    assert msg.timestamp == "2024-01-01T00:00:00"


def test_chat_request() -> None:
    """Test chat request."""
    req = ChatRequest(message="Hello")
    assert req.message == "Hello"
    assert req.conversation_id is None


def test_chat_request_with_conversation() -> None:
    """Test chat request with conversation ID."""
    req = ChatRequest(message="Hello", conversation_id="conv-123")
    assert req.conversation_id == "conv-123"


def test_chat_response() -> None:
    """Test chat response."""
    resp = ChatResponse(content="Hi there")
    assert resp.content == "Hi there"
    assert resp.role == "assistant"


def test_stream_chunk_start() -> None:
    """Test stream chunk start."""
    chunk = StreamChunk(type="start")
    assert chunk.type == "start"
    assert chunk.content is None


def test_stream_chunk_token() -> None:
    """Test stream chunk token."""
    chunk = StreamChunk(type="token", content="Hello")
    assert chunk.type == "token"
    assert chunk.content == "Hello"


def test_stream_chunk_done() -> None:
    """Test stream chunk done."""
    chunk = StreamChunk(type="done")
    assert chunk.type == "done"


def test_stream_chunk_error() -> None:
    """Test stream chunk error."""
    chunk = StreamChunk(type="error", error="Something went wrong")
    assert chunk.type == "error"
    assert chunk.error == "Something went wrong"


def test_invalid_message_role() -> None:
    """Test invalid message role."""
    with pytest.raises(ValueError):
        ChatMessage(role=cast(Literal["user"], "invalid"), content="test")


def test_invalid_stream_chunk_type() -> None:
    """Test invalid stream chunk type."""
    with pytest.raises(ValueError):
        StreamChunk(type=cast(Literal["start"], "invalid"))
