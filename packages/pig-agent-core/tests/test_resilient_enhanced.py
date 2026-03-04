"""Tests for enhanced resilient calls with events and custom exceptions."""

from unittest.mock import AsyncMock, Mock

import pytest
from pig_agent_core.observability.events import AgentEvent
from pig_agent_core.resilience.profile import APIProfile, ProfileManager
from pig_agent_core.resilience.retry import (
    ResilienceExhaustedError,
    resilient_call,
    resilient_streaming_call,
)


class TestResilienceExhaustedError:
    """Test ResilienceExhaustedError custom exception."""

    def test_exception_attributes(self):
        """Test that exception has expected attributes."""
        original = ValueError("Original error")
        error = ResilienceExhaustedError(
            "All strategies exhausted",
            original_error=original,
            attempts=3,
            strategies_tried=["profile_rotation", "context_compression"],
        )

        assert str(error) == "All strategies exhausted"
        assert error.original_error is original
        assert error.attempts == 3
        assert error.strategies_tried == ["profile_rotation", "context_compression"]

    def test_exception_default_strategies(self):
        """Test that strategies_tried defaults to empty list."""
        original = ValueError("Original error")
        error = ResilienceExhaustedError(
            "Failed",
            original_error=original,
        )

        assert error.strategies_tried == []
        assert error.attempts == 0

    def test_exception_is_exception(self):
        """Test that ResilienceExhaustedError is an Exception."""
        error = ResilienceExhaustedError(
            "Failed",
            original_error=ValueError("test"),
        )

        assert isinstance(error, Exception)


class TestResilientCallWithEvents:
    """Test resilient_call with event emission."""

    @pytest.mark.asyncio
    async def test_successful_call_no_events(self):
        """Test successful call emits no resilience events."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        # Mock LLM that succeeds
        llm = Mock()
        response = Mock()
        response.content = "Success"
        llm.achat = AsyncMock(return_value=response)
        llm.config.model = "gpt-4"

        result = await resilient_call(
            llm,
            messages=[],
            event_callback=callback,
        )

        assert result == "Success"
        # No resilience events should be emitted on success
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_retry_emits_event(self):
        """Test that retry emits resilience_retry event."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        # Mock LLM that fails once then succeeds
        llm = Mock()
        response = Mock()
        response.content = "Success"
        llm.achat = AsyncMock(side_effect=[Exception("Temporary error"), response])
        llm.config.model = "gpt-4"

        result = await resilient_call(
            llm,
            messages=[],
            event_callback=callback,
            max_retries=2,
        )

        assert result == "Success"
        # Should have emitted retry event
        assert len(events) >= 1
        retry_events = [e for e in events if e.data.get("event_subtype") == "resilience_retry"]
        assert len(retry_events) == 1
        assert retry_events[0].data["attempt"] == 1

    @pytest.mark.asyncio
    async def test_compression_emits_event(self):
        """Test that context compression emits resilience_compact event."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        def compress_fn(messages):
            return messages[:1]  # Compress to first message

        # Mock LLM that fails with context overflow then succeeds
        llm = Mock()
        response = Mock()
        response.content = "Success"
        llm.achat = AsyncMock(side_effect=[Exception("Context length exceeded"), response])
        llm.config.model = "gpt-4"

        result = await resilient_call(
            llm,
            messages=[Mock(), Mock(), Mock()],
            compress_fn=compress_fn,
            event_callback=callback,
            max_retries=2,
        )

        assert result == "Success"
        # Should have emitted compression event
        compact_events = [e for e in events if e.data.get("event_subtype") == "resilience_compact"]
        assert len(compact_events) == 1
        assert compact_events[0].data["original_count"] == 3
        assert compact_events[0].data["compressed_count"] == 1

    @pytest.mark.asyncio
    async def test_fallback_emits_event(self):
        """Test that model fallback emits resilience_fallback event."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        # Mock profile manager with fallback model
        profile_manager = ProfileManager(
            profiles=[APIProfile(api_key="test-key", model="gpt-4")],
            fallback_models=["gpt-4", "gpt-3.5-turbo"],
        )

        # Mock LLM that fails with context overflow then succeeds
        llm = Mock()
        response = Mock()
        response.content = "Success"
        llm.achat = AsyncMock(side_effect=[Exception("Context length exceeded"), response])
        llm.config.model = "gpt-4"

        result = await resilient_call(
            llm,
            messages=[Mock()],
            profile_manager=profile_manager,
            event_callback=callback,
            max_retries=2,
        )

        assert result == "Success"
        # Should have emitted fallback event
        fallback_events = [
            e for e in events if e.data.get("event_subtype") == "resilience_fallback"
        ]
        assert len(fallback_events) == 1
        assert fallback_events[0].data["to_model"] == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_exhausted_raises_custom_exception(self):
        """Test that exhausted retries raise ResilienceExhaustedError."""
        # Mock LLM that always fails
        llm = Mock()
        llm.achat = AsyncMock(side_effect=Exception("Persistent error"))
        llm.config.model = "gpt-4"

        with pytest.raises(ResilienceExhaustedError) as exc_info:
            await resilient_call(
                llm,
                messages=[],
                max_retries=2,
            )

        error = exc_info.value
        assert error.attempts == 2
        assert isinstance(error.original_error, Exception)
        assert "Persistent error" in str(error.original_error)

    @pytest.mark.asyncio
    async def test_exhausted_tracks_strategies(self):
        """Test that ResilienceExhaustedError tracks strategies tried."""

        def compress_fn(messages):
            return messages[:1]

        profile_manager = ProfileManager(
            profiles=[APIProfile(api_key="test-key", model="gpt-4")],
            fallback_models=["gpt-4", "gpt-3.5-turbo"],
        )

        # Mock LLM that always fails with context overflow
        llm = Mock()
        llm.achat = AsyncMock(side_effect=Exception("Context length exceeded"))
        llm.config.model = "gpt-4"

        with pytest.raises(ResilienceExhaustedError) as exc_info:
            await resilient_call(
                llm,
                messages=[Mock(), Mock()],
                profile_manager=profile_manager,
                compress_fn=compress_fn,
                max_retries=2,
            )

        error = exc_info.value
        # Should have tried compression and fallback
        assert "context_compression" in error.strategies_tried
        assert "model_fallback" in error.strategies_tried


class TestResilientStreamingCallWithEvents:
    """Test resilient_streaming_call with event emission."""

    @pytest.mark.asyncio
    async def test_successful_streaming_no_events(self):
        """Test successful streaming call emits no resilience events."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        # Mock LLM that succeeds
        async def mock_stream(*args, **kwargs):
            yield Mock(content="chunk1")
            yield Mock(content="chunk2")

        llm = Mock()
        llm.astream = mock_stream
        llm.config.model = "gpt-4"

        chunks = []
        async for chunk in resilient_streaming_call(
            llm,
            messages=[],
            event_callback=callback,
        ):
            chunks.append(chunk)

        assert len(chunks) == 2
        # No resilience events on success
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_streaming_retry_emits_event(self):
        """Test that streaming retry emits resilience_retry event."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        # Mock LLM that fails once then succeeds
        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary error")
            yield Mock(content="chunk1")

        llm = Mock()
        llm.astream = mock_stream
        llm.config.model = "gpt-4"

        chunks = []
        async for chunk in resilient_streaming_call(
            llm,
            messages=[],
            event_callback=callback,
            max_retries=2,
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        # Should have emitted retry event
        retry_events = [e for e in events if e.data.get("event_subtype") == "resilience_retry"]
        assert len(retry_events) == 1

    @pytest.mark.asyncio
    async def test_streaming_exhausted_raises_custom_exception(self):
        """Test that exhausted streaming retries raise ResilienceExhaustedError."""

        # Mock LLM that always fails
        async def mock_stream(*args, **kwargs):
            raise Exception("Persistent error")
            yield  # Never reached

        llm = Mock()
        llm.astream = mock_stream
        llm.config.model = "gpt-4"

        with pytest.raises(ResilienceExhaustedError) as exc_info:
            async for _ in resilient_streaming_call(
                llm,
                messages=[],
                max_retries=2,
            ):
                pass

        error = exc_info.value
        assert error.attempts == 2
        assert isinstance(error.original_error, Exception)


class TestBackwardCompatibility:
    """Test that enhanced features maintain backward compatibility."""

    @pytest.mark.asyncio
    async def test_call_without_event_callback_still_works(self):
        """Test that resilient_call works without event_callback."""
        llm = Mock()
        response = Mock()
        response.content = "Success"
        llm.achat = AsyncMock(return_value=response)
        llm.config.model = "gpt-4"

        # Should work without event_callback
        result = await resilient_call(llm, messages=[])
        assert result == "Success"

    @pytest.mark.asyncio
    async def test_streaming_without_event_callback_still_works(self):
        """Test that resilient_streaming_call works without event_callback."""

        async def mock_stream(*args, **kwargs):
            yield Mock(content="chunk1")

        llm = Mock()
        llm.astream = mock_stream
        llm.config.model = "gpt-4"

        # Should work without event_callback
        chunks = []
        async for chunk in resilient_streaming_call(llm, messages=[]):
            chunks.append(chunk)

        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_old_exception_behavior_preserved(self):
        """Test that old exception behavior is preserved (raises from original)."""
        llm = Mock()
        llm.achat = AsyncMock(side_effect=ValueError("Test error"))
        llm.config.model = "gpt-4"

        with pytest.raises(ResilienceExhaustedError) as exc_info:
            await resilient_call(llm, messages=[], max_retries=1)

        # Should chain from original exception
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
