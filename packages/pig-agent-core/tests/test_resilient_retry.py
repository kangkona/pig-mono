"""Tests for resilient LLM calls."""

from unittest.mock import AsyncMock, Mock

import pytest
from pig_agent_core.resilience.profile import APIProfile, ProfileManager
from pig_agent_core.resilience.retry import (
    ResilienceExhaustedError,
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


def test_should_rotate_profile():
    """Test profile rotation detection."""
    # Rate limit error
    assert _should_rotate_profile(Exception("Rate limit exceeded"))
    assert _should_rotate_profile(Exception("429 Too Many Requests"))

    # Auth error
    assert _should_rotate_profile(Exception("Invalid API key"))
    assert _should_rotate_profile(Exception("401 Unauthorized"))

    # Timeout error
    assert _should_rotate_profile(Exception("Connection timeout"))
    assert _should_rotate_profile(Exception("Network error"))

    # Not a rotation error
    assert not _should_rotate_profile(Exception("Something else"))


def test_is_context_overflow():
    """Test context overflow detection."""
    assert _is_context_overflow(Exception("Context length exceeded"))
    assert _is_context_overflow(Exception("Maximum context length"))
    assert _is_context_overflow(Exception("Token limit reached"))

    assert not _is_context_overflow(Exception("Something else"))


@pytest.mark.asyncio
async def test_resilient_streaming_call_success():
    """Test successful streaming call."""
    # Mock LLM
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    # Mock successful stream
    async def mock_stream(*args, **kwargs):
        yield {"content": "Hello"}
        yield {"content": " world"}

    llm.astream = mock_stream

    # Call
    messages = [{"role": "user", "content": "Hi"}]
    chunks = []
    async for chunk in resilient_streaming_call(llm, messages):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0]["content"] == "Hello"
    assert chunks[1]["content"] == " world"


@pytest.mark.asyncio
async def test_resilient_streaming_call_retry():
    """Test retry on transient error."""
    # Mock LLM
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    # Mock stream that fails once then succeeds
    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Network timeout")
        yield {"content": "Success"}

    llm.astream = mock_stream

    # Call
    messages = [{"role": "user", "content": "Hi"}]
    chunks = []
    async for chunk in resilient_streaming_call(llm, messages, max_retries=3):
        chunks.append(chunk)

    assert call_count == 2
    assert len(chunks) == 1
    assert chunks[0]["content"] == "Success"


@pytest.mark.asyncio
async def test_resilient_streaming_call_profile_rotation():
    """Test profile rotation on rate limit."""
    # Mock LLM
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    # Mock profile manager
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
    ]
    profile_manager = ProfileManager(profiles=profiles)

    # Mock stream that fails with rate limit then succeeds
    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Rate limit exceeded")
        yield {"content": "Success"}

    llm.astream = mock_stream

    # Call
    messages = [{"role": "user", "content": "Hi"}]
    chunks = []
    async for chunk in resilient_streaming_call(
        llm, messages, profile_manager=profile_manager, max_retries=3
    ):
        chunks.append(chunk)

    assert call_count == 2
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_resilient_streaming_call_context_compression():
    """Test context compression on overflow."""
    # Mock LLM
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    # Mock compress function
    def compress_fn(messages):
        # Remove first message
        return messages[1:]

    # Mock stream that fails with context overflow then succeeds
    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        messages = kwargs.get("messages", [])
        if call_count == 1:
            raise Exception("Context length exceeded")
        # Should succeed with compressed messages
        assert len(messages) == 1
        yield {"content": "Success"}

    llm.astream = mock_stream

    # Call with 2 messages
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
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_resilient_streaming_call_fallback_model():
    """Test fallback to alternative model."""
    # Mock LLM
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    # Mock profile manager with fallback
    profile_manager = ProfileManager(
        profiles=[],
        fallback_models=["gpt-4", "gpt-3.5-turbo"],
    )

    # Mock stream that fails with context overflow then succeeds
    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        model = kwargs.get("model", "gpt-4")
        if call_count == 1:
            raise Exception("Context length exceeded")
        # Should succeed with fallback model
        assert model == "gpt-3.5-turbo"
        yield {"content": "Success"}

    llm.astream = mock_stream

    # Call
    messages = [{"role": "user", "content": "Hi"}]
    chunks = []
    async for chunk in resilient_streaming_call(
        llm, messages, profile_manager=profile_manager, max_retries=3, model="gpt-4"
    ):
        chunks.append(chunk)

    assert call_count == 2
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_resilient_streaming_call_max_retries():
    """Test max retries exhausted raises ResilienceExhaustedError."""
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    async def mock_stream(*args, **kwargs):
        # Yield makes this an async generator; raise happens on first iteration
        raise Exception("Permanent failure")
        yield  # unreachable — required to make this an async generator

    llm.astream = mock_stream

    messages = [{"role": "user", "content": "Hi"}]
    with pytest.raises(ResilienceExhaustedError) as exc_info:
        async for _chunk in resilient_streaming_call(llm, messages, max_retries=2):
            pass

    assert "Permanent failure" in str(exc_info.value.original_error)


@pytest.mark.asyncio
async def test_resilient_call_success():
    """Test successful non-streaming call."""
    # Mock LLM
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    # Mock successful response
    mock_response = Mock()
    mock_response.content = "Hello world"
    llm.achat = AsyncMock(return_value=mock_response)

    # Call
    messages = [{"role": "user", "content": "Hi"}]
    response = await resilient_call(llm, messages)

    assert response == "Hello world"


@pytest.mark.asyncio
async def test_resilient_call_retry():
    """Test retry on transient error."""
    # Mock LLM
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    # Mock response that fails once then succeeds
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

    # Call
    messages = [{"role": "user", "content": "Hi"}]
    response = await resilient_call(llm, messages, max_retries=3)

    assert call_count == 2
    assert response == "Success"


@pytest.mark.asyncio
async def test_resilient_call_max_retries():
    """Test max retries exhausted raises ResilienceExhaustedError."""
    llm = Mock()
    llm.config = Mock(model="gpt-4")

    llm.achat = AsyncMock(side_effect=Exception("Permanent failure"))

    messages = [{"role": "user", "content": "Hi"}]
    with pytest.raises(ResilienceExhaustedError) as exc_info:
        await resilient_call(llm, messages, max_retries=2)

    assert "Permanent failure" in str(exc_info.value.original_error)
