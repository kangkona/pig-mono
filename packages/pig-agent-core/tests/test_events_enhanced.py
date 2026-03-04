"""Tests for enhanced event system with BillingHook and resilience events."""

from typing import Any

import pytest
from pig_agent_core.observability.events import (
    AgentEvent,
    AgentEventType,
    BillingHook,
    emit_context_compressed,
    emit_model_fallback,
    emit_profile_rotated,
)


class TestResilienceEventTypes:
    """Test resilience event types."""

    def test_profile_rotated_event_type_exists(self):
        """Test that PROFILE_ROTATED event type exists."""
        assert hasattr(AgentEventType, "PROFILE_ROTATED")
        assert AgentEventType.PROFILE_ROTATED.value == "profile_rotated"

    def test_context_compressed_event_type_exists(self):
        """Test that CONTEXT_COMPRESSED event type exists."""
        assert hasattr(AgentEventType, "CONTEXT_COMPRESSED")
        assert AgentEventType.CONTEXT_COMPRESSED.value == "context_compressed"

    def test_model_fallback_event_type_exists(self):
        """Test that MODEL_FALLBACK event type exists."""
        assert hasattr(AgentEventType, "MODEL_FALLBACK")
        assert AgentEventType.MODEL_FALLBACK.value == "model_fallback"

    def test_all_event_types_are_strings(self):
        """Test that all event types are string enums."""
        for event_type in AgentEventType:
            assert isinstance(event_type.value, str)


class TestEmitProfileRotated:
    """Test emit_profile_rotated helper function."""

    def test_emit_profile_rotated_basic(self):
        """Test emitting profile rotated event."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_profile_rotated(
            callback,
            from_key="old-key-123",
            to_key="new-key-456",
        )

        assert len(events) == 1
        event = events[0]
        assert event.type == AgentEventType.PROFILE_ROTATED
        assert event.data["from_key"] == "old-key-123"
        assert event.data["to_key"] == "new-key-456"

    def test_emit_profile_rotated_with_reason(self):
        """Test emitting profile rotated event with reason."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_profile_rotated(
            callback,
            from_key="old-key",
            to_key="new-key",
            reason="rate_limit",
        )

        assert len(events) == 1
        assert events[0].data["reason"] == "rate_limit"

    def test_emit_profile_rotated_with_none_from_key(self):
        """Test emitting profile rotated event with None from_key."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_profile_rotated(
            callback,
            from_key=None,
            to_key="new-key",
        )

        assert len(events) == 1
        assert events[0].data["from_key"] is None

    def test_emit_profile_rotated_with_extra_kwargs(self):
        """Test emitting profile rotated event with extra data."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_profile_rotated(
            callback,
            from_key="old-key",
            to_key="new-key",
            cooldown=60.0,
            attempt=2,
        )

        assert len(events) == 1
        assert events[0].data["cooldown"] == 60.0
        assert events[0].data["attempt"] == 2

    def test_emit_profile_rotated_without_callback(self):
        """Test that emit_profile_rotated works without callback."""
        # Should not raise
        emit_profile_rotated(
            None,
            from_key="old-key",
            to_key="new-key",
        )


class TestEmitContextCompressed:
    """Test emit_context_compressed helper function."""

    def test_emit_context_compressed_basic(self):
        """Test emitting context compressed event."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_context_compressed(
            callback,
            original_count=10,
            compressed_count=5,
        )

        assert len(events) == 1
        event = events[0]
        assert event.type == AgentEventType.CONTEXT_COMPRESSED
        assert event.data["original_count"] == 10
        assert event.data["compressed_count"] == 5
        assert event.data["reduction"] == 5

    def test_emit_context_compressed_with_level(self):
        """Test emitting context compressed event with compression level."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_context_compressed(
            callback,
            original_count=20,
            compressed_count=10,
            compression_level=2,
        )

        assert len(events) == 1
        assert events[0].data["compression_level"] == 2

    def test_emit_context_compressed_calculates_reduction(self):
        """Test that reduction is calculated correctly."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_context_compressed(
            callback,
            original_count=100,
            compressed_count=25,
        )

        assert len(events) == 1
        assert events[0].data["reduction"] == 75

    def test_emit_context_compressed_with_extra_kwargs(self):
        """Test emitting context compressed event with extra data."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_context_compressed(
            callback,
            original_count=10,
            compressed_count=5,
            strategy="truncate",
        )

        assert len(events) == 1
        assert events[0].data["strategy"] == "truncate"

    def test_emit_context_compressed_without_callback(self):
        """Test that emit_context_compressed works without callback."""
        # Should not raise
        emit_context_compressed(
            None,
            original_count=10,
            compressed_count=5,
        )


class TestEmitModelFallback:
    """Test emit_model_fallback helper function."""

    def test_emit_model_fallback_basic(self):
        """Test emitting model fallback event."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_model_fallback(
            callback,
            from_model="gpt-4",
            to_model="gpt-3.5-turbo",
        )

        assert len(events) == 1
        event = events[0]
        assert event.type == AgentEventType.MODEL_FALLBACK
        assert event.data["from_model"] == "gpt-4"
        assert event.data["to_model"] == "gpt-3.5-turbo"

    def test_emit_model_fallback_with_reason(self):
        """Test emitting model fallback event with reason."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_model_fallback(
            callback,
            from_model="gpt-4",
            to_model="gpt-3.5-turbo",
            reason="context_overflow",
        )

        assert len(events) == 1
        assert events[0].data["reason"] == "context_overflow"

    def test_emit_model_fallback_with_extra_kwargs(self):
        """Test emitting model fallback event with extra data."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_model_fallback(
            callback,
            from_model="gpt-4",
            to_model="gpt-3.5-turbo",
            attempt=3,
            cost_savings=0.5,
        )

        assert len(events) == 1
        assert events[0].data["attempt"] == 3
        assert events[0].data["cost_savings"] == 0.5

    def test_emit_model_fallback_without_callback(self):
        """Test that emit_model_fallback works without callback."""
        # Should not raise
        emit_model_fallback(
            None,
            from_model="gpt-4",
            to_model="gpt-3.5-turbo",
        )


class TestBillingHookProtocol:
    """Test BillingHook protocol."""

    def test_billing_hook_protocol_exists(self):
        """Test that BillingHook protocol is defined."""
        assert BillingHook is not None

    def test_billing_hook_has_on_llm_call(self):
        """Test that BillingHook has on_llm_call method."""
        # Check that protocol has the method signature
        assert hasattr(BillingHook, "on_llm_call")

    def test_billing_hook_has_on_tool_call(self):
        """Test that BillingHook has on_tool_call method."""
        assert hasattr(BillingHook, "on_tool_call")

    def test_billing_hook_has_get_usage_summary(self):
        """Test that BillingHook has get_usage_summary method."""
        assert hasattr(BillingHook, "get_usage_summary")

    def test_billing_hook_implementation(self):
        """Test implementing BillingHook protocol."""

        class SimpleBillingHook:
            def __init__(self):
                self.llm_calls = []
                self.tool_calls = []

            def on_llm_call(
                self,
                model: str,
                input_tokens: int,
                output_tokens: int,
                user_id: str | None = None,
                metadata: dict[str, Any] | None = None,
            ) -> None:
                self.llm_calls.append(
                    {
                        "model": model,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "user_id": user_id,
                    }
                )

            def on_tool_call(
                self,
                tool_name: str,
                user_id: str | None = None,
                metadata: dict[str, Any] | None = None,
            ) -> None:
                self.tool_calls.append({"tool_name": tool_name, "user_id": user_id})

            def get_usage_summary(self, user_id: str | None = None) -> dict[str, Any]:
                return {
                    "total_llm_calls": len(self.llm_calls),
                    "total_tool_calls": len(self.tool_calls),
                }

        # Create instance and test
        hook = SimpleBillingHook()
        hook.on_llm_call("gpt-4", 100, 50, user_id="user123")
        hook.on_tool_call("search_web", user_id="user123")

        assert len(hook.llm_calls) == 1
        assert len(hook.tool_calls) == 1
        assert hook.llm_calls[0]["model"] == "gpt-4"
        assert hook.tool_calls[0]["tool_name"] == "search_web"

        summary = hook.get_usage_summary()
        assert summary["total_llm_calls"] == 1
        assert summary["total_tool_calls"] == 1

    def test_billing_hook_with_cost_calculation(self):
        """Test BillingHook implementation with cost calculation."""

        class CostTrackingHook:
            # Simplified pricing (per 1K tokens)
            PRICING = {
                "gpt-4": {"input": 0.03, "output": 0.06},
                "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            }

            def __init__(self):
                self.total_cost = 0.0

            def on_llm_call(
                self,
                model: str,
                input_tokens: int,
                output_tokens: int,
                user_id: str | None = None,
                metadata: dict[str, Any] | None = None,
            ) -> None:
                if model in self.PRICING:
                    pricing = self.PRICING[model]
                    cost = (input_tokens / 1000 * pricing["input"]) + (
                        output_tokens / 1000 * pricing["output"]
                    )
                    self.total_cost += cost

            def on_tool_call(
                self,
                tool_name: str,
                user_id: str | None = None,
                metadata: dict[str, Any] | None = None,
            ) -> None:
                pass  # No cost for tools

            def get_usage_summary(self, user_id: str | None = None) -> dict[str, Any]:
                return {"total_cost": self.total_cost}

        hook = CostTrackingHook()
        hook.on_llm_call("gpt-4", 1000, 500)  # $0.03 + $0.03 = $0.06
        hook.on_llm_call("gpt-3.5-turbo", 1000, 500)  # $0.001 + $0.001 = $0.002

        summary = hook.get_usage_summary()
        assert summary["total_cost"] == pytest.approx(0.062, rel=1e-6)


class TestEventTimestamps:
    """Test that resilience events have timestamps."""

    def test_profile_rotated_has_timestamp(self):
        """Test that profile rotated event has timestamp."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_profile_rotated(callback, from_key="old", to_key="new")

        assert len(events) == 1
        assert events[0].timestamp > 0

    def test_context_compressed_has_timestamp(self):
        """Test that context compressed event has timestamp."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_context_compressed(callback, original_count=10, compressed_count=5)

        assert len(events) == 1
        assert events[0].timestamp > 0

    def test_model_fallback_has_timestamp(self):
        """Test that model fallback event has timestamp."""
        events = []

        def callback(event: AgentEvent):
            events.append(event)

        emit_model_fallback(callback, from_model="gpt-4", to_model="gpt-3.5-turbo")

        assert len(events) == 1
        assert events[0].timestamp > 0
