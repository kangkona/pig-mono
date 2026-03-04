#!/usr/bin/env python3
"""Standalone test for observability event system."""

import sys
import time
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from pig_agent_core.observability.events import (  # noqa: E402
    AgentEvent,
    AgentEventType,
    emit,
    emit_agent_end,
    emit_agent_start,
    emit_tool_end,
    emit_tool_start,
    emit_turn_end,
    emit_turn_start,
    span,
)


def test_agent_event_creation():
    """Test AgentEvent creation."""
    event = AgentEvent(
        type=AgentEventType.AGENT_START,
        data={"agent_id": "test-agent"},
    )

    assert event.type == AgentEventType.AGENT_START
    assert event.data["agent_id"] == "test-agent"
    assert event.timestamp > 0
    print("✓ test_agent_event_creation passed")


def test_agent_event_to_dict():
    """Test AgentEvent to_dict conversion."""
    event = AgentEvent(
        type=AgentEventType.TOOL_START,
        data={"tool_name": "search"},
        span_id="span-123",
        parent_span_id="parent-456",
    )

    event_dict = event.to_dict()
    assert event_dict["type"] == "tool_start"
    assert event_dict["data"]["tool_name"] == "search"
    assert event_dict["span_id"] == "span-123"
    assert event_dict["parent_span_id"] == "parent-456"
    print("✓ test_agent_event_to_dict passed")


def test_emit_with_callback():
    """Test emit with callback."""
    events = []

    def callback(event):
        events.append(event)

    event = AgentEvent(type=AgentEventType.AGENT_START, data={"test": "data"})
    emit(callback, event)

    assert len(events) == 1
    assert events[0].type == AgentEventType.AGENT_START
    print("✓ test_emit_with_callback passed")


def test_emit_without_callback():
    """Test emit without callback (should not error)."""
    event = AgentEvent(type=AgentEventType.AGENT_START)
    emit(None, event)  # Should not raise
    print("✓ test_emit_without_callback passed")


def test_emit_with_failing_callback():
    """Test emit with failing callback (should not raise)."""

    def failing_callback(event):
        raise Exception("Callback error")

    event = AgentEvent(type=AgentEventType.AGENT_START)
    emit(failing_callback, event)  # Should not raise
    print("✓ test_emit_with_failing_callback passed")


def test_span_context_manager():
    """Test span context manager."""
    events = []

    def callback(event):
        events.append(event)

    with span("test_operation", callback=callback, attrs={"user": "123"}):
        time.sleep(0.01)  # Simulate work

    assert len(events) == 2
    assert events[0].type == AgentEventType.SPAN_START
    assert events[1].type == AgentEventType.SPAN_END
    assert events[0].data["name"] == "test_operation"
    assert events[0].data["user"] == "123"
    assert "duration" in events[1].data
    assert events[1].data["duration"] > 0
    print("✓ test_span_context_manager passed")


def test_span_with_span_id():
    """Test span with custom span ID."""
    events = []

    def callback(event):
        events.append(event)

    with span(
        "test_op",
        callback=callback,
        span_id="custom-span-id",
        parent_span_id="parent-id",
    ) as span_id:
        assert span_id == "custom-span-id"

    assert events[0].span_id == "custom-span-id"
    assert events[0].parent_span_id == "parent-id"
    print("✓ test_span_with_span_id passed")


def test_span_generates_id():
    """Test span generates ID if not provided."""
    events = []

    def callback(event):
        events.append(event)

    with span("test_op", callback=callback) as span_id:
        assert span_id is not None
        assert len(span_id) > 0

    assert events[0].span_id == span_id
    print("✓ test_span_generates_id passed")


def test_emit_agent_start():
    """Test emit_agent_start helper."""
    events = []

    def callback(event):
        events.append(event)

    emit_agent_start(callback, agent_id="agent-1", user_id="user-1", extra="data")

    assert len(events) == 1
    assert events[0].type == AgentEventType.AGENT_START
    assert events[0].data["agent_id"] == "agent-1"
    assert events[0].data["user_id"] == "user-1"
    assert events[0].data["extra"] == "data"
    print("✓ test_emit_agent_start passed")


def test_emit_agent_end():
    """Test emit_agent_end helper."""
    events = []

    def callback(event):
        events.append(event)

    emit_agent_end(callback, agent_id="agent-1", success=False, error="Test error")

    assert len(events) == 1
    assert events[0].type == AgentEventType.AGENT_END
    assert events[0].data["agent_id"] == "agent-1"
    assert events[0].data["success"] is False
    assert events[0].data["error"] == "Test error"
    print("✓ test_emit_agent_end passed")


def test_emit_turn_start():
    """Test emit_turn_start helper."""
    events = []

    def callback(event):
        events.append(event)

    emit_turn_start(callback, turn_number=1, user_message="Hello")

    assert len(events) == 1
    assert events[0].type == AgentEventType.TURN_START
    assert events[0].data["turn_number"] == 1
    assert events[0].data["user_message"] == "Hello"
    print("✓ test_emit_turn_start passed")


def test_emit_turn_end():
    """Test emit_turn_end helper."""
    events = []

    def callback(event):
        events.append(event)

    emit_turn_end(callback, turn_number=1, assistant_message="Hi there", tool_calls=2)

    assert len(events) == 1
    assert events[0].type == AgentEventType.TURN_END
    assert events[0].data["turn_number"] == 1
    assert events[0].data["assistant_message"] == "Hi there"
    assert events[0].data["tool_calls"] == 2
    print("✓ test_emit_turn_end passed")


def test_emit_tool_start():
    """Test emit_tool_start helper."""
    events = []

    def callback(event):
        events.append(event)

    emit_tool_start(callback, tool_name="search", tool_args={"query": "test"})

    assert len(events) == 1
    assert events[0].type == AgentEventType.TOOL_START
    assert events[0].data["tool_name"] == "search"
    assert events[0].data["tool_args"]["query"] == "test"
    print("✓ test_emit_tool_start passed")


def test_emit_tool_end():
    """Test emit_tool_end helper."""
    events = []

    def callback(event):
        events.append(event)

    emit_tool_end(callback, tool_name="search", success=True, result={"items": [1, 2, 3]})

    assert len(events) == 1
    assert events[0].type == AgentEventType.TOOL_END
    assert events[0].data["tool_name"] == "search"
    assert events[0].data["success"] is True
    assert events[0].data["result"]["items"] == [1, 2, 3]
    print("✓ test_emit_tool_end passed")


def test_event_types():
    """Test all event types are defined."""
    assert AgentEventType.AGENT_START == "agent_start"
    assert AgentEventType.AGENT_END == "agent_end"
    assert AgentEventType.TURN_START == "turn_start"
    assert AgentEventType.TURN_END == "turn_end"
    assert AgentEventType.TOOL_START == "tool_start"
    assert AgentEventType.TOOL_END == "tool_end"
    assert AgentEventType.SPAN_START == "span_start"
    assert AgentEventType.SPAN_END == "span_end"
    print("✓ test_event_types passed")


def main():
    """Run all tests."""
    print("Running observability event system tests...")
    print()

    test_agent_event_creation()
    test_agent_event_to_dict()
    test_emit_with_callback()
    test_emit_without_callback()
    test_emit_with_failing_callback()
    test_span_context_manager()
    test_span_with_span_id()
    test_span_generates_id()
    test_emit_agent_start()
    test_emit_agent_end()
    test_emit_turn_start()
    test_emit_turn_end()
    test_emit_tool_start()
    test_emit_tool_end()
    test_event_types()

    print()
    print("All tests passed! ✓")


if __name__ == "__main__":
    main()
