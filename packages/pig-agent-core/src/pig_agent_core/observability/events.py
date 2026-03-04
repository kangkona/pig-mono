"""Event system for agent observability.

Extracted from sophia-pro LiteAgent's observability system.
"""

import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class AgentEventType(str, Enum):
    """Event types for agent execution tracking."""

    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    SPAN_START = "span_start"
    SPAN_END = "span_end"
    # Resilience event types
    PROFILE_ROTATED = "profile_rotated"
    CONTEXT_COMPRESSED = "context_compressed"
    MODEL_FALLBACK = "model_fallback"


@dataclass
class AgentEvent:
    """Event emitted during agent execution.

    Attributes:
        type: Event type
        timestamp: Unix timestamp when event occurred
        data: Event-specific data
        span_id: Optional span ID for tracing
        parent_span_id: Optional parent span ID
    """

    type: AgentEventType
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
    span_id: str | None = None
    parent_span_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary.

        Returns:
            Dictionary representation of event
        """
        return {
            "type": self.type.value,
            "timestamp": self.timestamp,
            "data": self.data,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
        }


# Type alias for event callbacks
AgentEventCallback = Callable[[AgentEvent], None]


class BillingHook(Protocol):
    """Protocol for billing/cost tracking hooks.

    Products can implement this protocol to track LLM usage costs.
    """

    def on_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Called when an LLM call completes.

        Args:
            model: Model name (e.g., "gpt-4", "claude-3-5-sonnet-20241022")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            user_id: Optional user identifier for cost attribution
            metadata: Optional additional metadata
        """
        ...

    def on_tool_call(
        self,
        tool_name: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Called when a tool is executed.

        Args:
            tool_name: Name of the tool
            user_id: Optional user identifier
            metadata: Optional additional metadata
        """
        ...

    def get_usage_summary(self, user_id: str | None = None) -> dict[str, Any]:
        """Get usage summary for cost tracking.

        Args:
            user_id: Optional user identifier to filter by

        Returns:
            Dictionary with usage statistics
        """
        ...


def emit(callback: AgentEventCallback | None, event: AgentEvent) -> None:
    """Emit an event to the callback.

    Args:
        callback: Optional callback function to receive event
        event: Event to emit
    """
    if callback:
        try:
            callback(event)
        except Exception as e:
            # Don't let callback errors break agent execution
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error in event callback: {e}")


@contextmanager
def span(
    name: str,
    callback: AgentEventCallback | None = None,
    attrs: dict[str, Any] | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
):
    """Context manager for tracing spans.

    Emits span_start and span_end events with timing information.

    Args:
        name: Span name
        callback: Optional callback for events
        attrs: Optional attributes to attach to span
        span_id: Optional span ID (generated if not provided)
        parent_span_id: Optional parent span ID

    Yields:
        Span ID

    Example:
        >>> def my_callback(event):
        ...     print(f"Event: {event.type} - {event.data}")
        >>> with span("my_operation", callback=my_callback, attrs={"user": "123"}):
        ...     # Do work
        ...     pass
    """
    import uuid

    # Generate span ID if not provided
    if span_id is None:
        span_id = str(uuid.uuid4())

    # Prepare span data
    span_data = {
        "name": name,
        "span_id": span_id,
        **(attrs or {}),
    }

    # Emit start event
    start_time = time.time()
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.SPAN_START,
            timestamp=start_time,
            data=span_data,
            span_id=span_id,
            parent_span_id=parent_span_id,
        ),
    )

    try:
        yield span_id
    finally:
        # Emit end event with duration
        end_time = time.time()
        duration = end_time - start_time
        emit(
            callback,
            AgentEvent(
                type=AgentEventType.SPAN_END,
                timestamp=end_time,
                data={
                    **span_data,
                    "duration": duration,
                },
                span_id=span_id,
                parent_span_id=parent_span_id,
            ),
        )


def emit_agent_start(
    callback: AgentEventCallback | None,
    agent_id: str,
    user_id: str | None = None,
    **kwargs: Any,
) -> None:
    """Emit agent_start event.

    Args:
        callback: Optional callback for event
        agent_id: Agent identifier
        user_id: Optional user identifier
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.AGENT_START,
            data={
                "agent_id": agent_id,
                "user_id": user_id,
                **kwargs,
            },
        ),
    )


def emit_agent_end(
    callback: AgentEventCallback | None,
    agent_id: str,
    success: bool = True,
    error: str | None = None,
    **kwargs: Any,
) -> None:
    """Emit agent_end event.

    Args:
        callback: Optional callback for event
        agent_id: Agent identifier
        success: Whether agent completed successfully
        error: Optional error message
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.AGENT_END,
            data={
                "agent_id": agent_id,
                "success": success,
                "error": error,
                **kwargs,
            },
        ),
    )


def emit_turn_start(
    callback: AgentEventCallback | None,
    turn_number: int,
    user_message: str | None = None,
    **kwargs: Any,
) -> None:
    """Emit turn_start event.

    Args:
        callback: Optional callback for event
        turn_number: Turn number in conversation
        user_message: Optional user message
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.TURN_START,
            data={
                "turn_number": turn_number,
                "user_message": user_message,
                **kwargs,
            },
        ),
    )


def emit_turn_end(
    callback: AgentEventCallback | None,
    turn_number: int,
    assistant_message: str | None = None,
    tool_calls: int = 0,
    **kwargs: Any,
) -> None:
    """Emit turn_end event.

    Args:
        callback: Optional callback for event
        turn_number: Turn number in conversation
        assistant_message: Optional assistant message
        tool_calls: Number of tool calls made
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.TURN_END,
            data={
                "turn_number": turn_number,
                "assistant_message": assistant_message,
                "tool_calls": tool_calls,
                **kwargs,
            },
        ),
    )


def emit_tool_start(
    callback: AgentEventCallback | None,
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """Emit tool_start event.

    Args:
        callback: Optional callback for event
        tool_name: Name of tool being called
        tool_args: Optional tool arguments
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.TOOL_START,
            data={
                "tool_name": tool_name,
                "tool_args": tool_args,
                **kwargs,
            },
        ),
    )


def emit_tool_end(
    callback: AgentEventCallback | None,
    tool_name: str,
    success: bool = True,
    error: str | None = None,
    result: Any = None,
    **kwargs: Any,
) -> None:
    """Emit tool_end event.

    Args:
        callback: Optional callback for event
        tool_name: Name of tool that was called
        success: Whether tool completed successfully
        error: Optional error message
        result: Optional tool result
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.TOOL_END,
            data={
                "tool_name": tool_name,
                "success": success,
                "error": error,
                "result": result,
                **kwargs,
            },
        ),
    )


def emit_profile_rotated(
    callback: AgentEventCallback | None,
    from_key: str | None,
    to_key: str,
    reason: str | None = None,
    **kwargs: Any,
) -> None:
    """Emit profile_rotated event.

    Args:
        callback: Optional callback for event
        from_key: Previous API key (truncated for security)
        to_key: New API key (truncated for security)
        reason: Optional reason for rotation
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.PROFILE_ROTATED,
            data={
                "from_key": from_key,
                "to_key": to_key,
                "reason": reason,
                **kwargs,
            },
        ),
    )


def emit_context_compressed(
    callback: AgentEventCallback | None,
    original_count: int,
    compressed_count: int,
    compression_level: int = 1,
    **kwargs: Any,
) -> None:
    """Emit context_compressed event.

    Args:
        callback: Optional callback for event
        original_count: Original message count
        compressed_count: Compressed message count
        compression_level: Compression level (1, 2, or 3)
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.CONTEXT_COMPRESSED,
            data={
                "original_count": original_count,
                "compressed_count": compressed_count,
                "compression_level": compression_level,
                "reduction": original_count - compressed_count,
                **kwargs,
            },
        ),
    )


def emit_model_fallback(
    callback: AgentEventCallback | None,
    from_model: str,
    to_model: str,
    reason: str | None = None,
    **kwargs: Any,
) -> None:
    """Emit model_fallback event.

    Args:
        callback: Optional callback for event
        from_model: Original model name
        to_model: Fallback model name
        reason: Optional reason for fallback
        **kwargs: Additional event data
    """
    emit(
        callback,
        AgentEvent(
            type=AgentEventType.MODEL_FALLBACK,
            data={
                "from_model": from_model,
                "to_model": to_model,
                "reason": reason,
                **kwargs,
            },
        ),
    )
