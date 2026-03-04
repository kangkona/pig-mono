#!/usr/bin/env python3
"""Standalone test for resilient retry system."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from pig_agent_core.resilience.retry import (
    _is_context_overflow,
    _is_error_type,
    _should_rotate_profile,
    resilient_call,
    resilient_streaming_call,
)


def test_is_error_type():
    """Test error type matching."""
    error = Exception("Rate limit exceeded")
    assert _is_error_type(error, ("rate limit", "quota"))

    error = Exception("Authentication failed")
    assert _is_error_type(error, ("auth", "authentication"))

    error = Exception("Something else")
    assert not _is_error_type(error, ("rate limit", "quota"))
    print("✓ test_is_error_type passed")


def test_should_rotate_profile():
    """Test profile rotation detection."""
    assert _should_rotate_profile(Exception("Rate limit exceeded"))
    assert _should_rotate_profile(Exception("429 Too Many Requests"))
    assert _should_rotate_profile(Exception("Invalid API key"))
    assert not _should_rotate_profile(Exception("Something else"))
    print("✓ test_should_rotate_profile passed")


def test_is_context_overflow():
    """Test context overflow detection."""
    assert _is_context_overflow(Exception("Context length exceeded"))
    assert _is_context_overflow(Exception("Maximum context length"))
    assert not _is_context_overflow(Exception("Something else"))
    print("✓ test_is_context_overflow passed")


async def test_resilient_streaming_call_success():
    """Test successful streaming call."""
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    async def mock_stream(*args, **kwargs):
        yield {"content": "Hello"}
        yield {"content": " world"}

    llm.astream = mock_stream

    messages = [{"role": "user", "content": "Hi"}]
    chunks = []
    async for chunk in resilient_streaming_call(llm, messages):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0]["content"] == "Hello"
    print("✓ test_resilient_streaming_call_success passed")


async def test_resilient_streaming_call_retry():
    """Test retry on transient error."""
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Network timeout")
        yield {"content": "Success"}

    llm.astream = mock_stream

    messages = [{"role": "user", "content": "Hi"}]
    chunks = []
    async for chunk in resilient_streaming_call(llm, messages, max_retries=3):
        chunks.append(chunk)

    assert call_count == 2
    assert len(chunks) == 1
    print("✓ test_resilient_streaming_call_retry passed")


async def test_resilient_streaming_call_context_compression():
    """Test context compression on overflow."""
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    def compress_fn(messages):
        return messages[1:]

    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        messages = kwargs.get("messages", [])
        if call_count == 1:
            raise Exception("Context length exceeded")
        assert len(messages) == 1
        yield {"content": "Success"}

    llm.astream = mock_stream

    messages = [
        {"role": "user", "content": "First"},
        {"role": "user", "content": "Second"},
    ]
    chunks = []
    async for chunk in resilient_streaming_call(
        llm, messages, compress_fn=compress_fn, max_retries=3
    ):
        chunks.append(chunk)

    assert call_count == 2
    print("✓ test_resilient_streaming_call_context_compression passed")


async def test_resilient_call_success():
    """Test successful non-streaming call."""
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    mock_response = Mock()
    mock_response.content = "Hello world"
    llm.achat = AsyncMock(return_value=mock_response)

    messages = [{"role": "user", "content": "Hi"}]
    response = await resilient_call(llm, messages)

    assert response == "Hello world"
    print("✓ test_resilient_call_success passed")


async def test_resilient_call_retry():
    """Test retry on transient error."""
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    call_count = 0

    async def mock_achat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Network timeout")
        mock_response = Mock()
        mock_response.content = "Success"
        return mock_response

    llm.achat = mock_achat

    messages = [{"role": "user", "content": "Hi"}]
    response = await resilient_call(llm, messages, max_retries=3)

    assert call_count == 2
    assert response == "Success"
    print("✓ test_resilient_call_retry passed")


async def main():
    """Run all tests."""
    print("Running resilient retry tests...")
    print()

    test_is_error_type()
    test_should_rotate_profile()
    test_is_context_overflow()
    await test_resilient_streaming_call_success()
    await test_resilient_streaming_call_retry()
    await test_resilient_streaming_call_context_compression()
    await test_resilient_call_success()
    await test_resilient_call_retry()

    print()
    print("All tests passed! ✓")


if __name__ == "__main__":
    asyncio.run(main())
