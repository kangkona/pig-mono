"""Tests for data models."""

import pytest
from pig_llm.models import Message, Response, StreamChunk, Usage


def test_message_creation():
    """Test message creation."""
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"
    assert msg.metadata is None


def test_message_with_metadata():
    """Test message with metadata."""
    msg = Message(
        role="assistant",
        content="Hi",
        metadata={"model": "gpt-4"}
    )
    assert msg.metadata["model"] == "gpt-4"


def test_response_creation():
    """Test response creation."""
    response = Response(
        content="Hello world",
        model="gpt-3.5-turbo",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    )
    assert response.content == "Hello world"
    assert response.model == "gpt-3.5-turbo"
    assert response.usage["total_tokens"] == 15


def test_stream_chunk():
    """Test stream chunk."""
    chunk = StreamChunk(content="Hello", finish_reason=None)
    assert chunk.content == "Hello"
    assert chunk.finish_reason is None


def test_usage_addition():
    """Test usage addition."""
    usage1 = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    usage2 = Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
    
    total = usage1 + usage2
    assert total.prompt_tokens == 30
    assert total.completion_tokens == 15
    assert total.total_tokens == 45


def test_invalid_message_role():
    """Test invalid message role."""
    with pytest.raises(ValueError):
        Message(role="invalid", content="test")
