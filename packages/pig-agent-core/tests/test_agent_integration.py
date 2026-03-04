#!/usr/bin/env python3
"""Integration test for Agent with all subsystems."""

import sys
from pathlib import Path
from unittest.mock import Mock

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from pig_agent_core.agent import Agent  # noqa: E402
from pig_agent_core.observability.events import AgentEvent  # noqa: E402
from pig_agent_core.resilience.profile import APIProfile, ProfileManager  # noqa: E402


def create_mock_llm():
    """Create a mock LLM for testing."""
    llm = Mock()
    llm.config = Mock(model="gpt-4")
    return llm


def test_agent_initialization():
    """Test Agent initialization with new subsystems."""
    # Create profile manager
    profiles = [
        APIProfile(api_key="test-key-1", model="gpt-4"),
        APIProfile(api_key="test-key-2", model="gpt-4"),
    ]
    profile_manager = ProfileManager(profiles=profiles)

    # Create event callback
    events = []

    def event_callback(event: AgentEvent):
        events.append(event)

    # Create compress function
    def compress_fn(messages):
        # Simple compression: keep only last 5 messages
        return messages[-5:] if len(messages) > 5 else messages

    # Create agent with all subsystems
    agent = Agent(
        name="TestAgent",
        llm=create_mock_llm(),
        system_prompt="You are a helpful assistant.",
        profile_manager=profile_manager,
        event_callback=event_callback,
        compress_fn=compress_fn,
    )

    assert agent.name == "TestAgent"
    assert agent.profile_manager is not None
    assert agent.event_callback is not None
    assert agent.compress_fn is not None
    print("✓ test_agent_initialization passed")


def test_agent_has_subsystems():
    """Test that agent has all subsystem attributes."""
    agent = Agent(llm=create_mock_llm())

    # Check that new attributes exist
    assert hasattr(agent, "profile_manager")
    assert hasattr(agent, "event_callback")
    assert hasattr(agent, "compress_fn")

    # Check that they default to None
    assert agent.profile_manager is None
    assert agent.event_callback is None
    assert agent.compress_fn is None
    print("✓ test_agent_has_subsystems passed")


def test_agent_backward_compatibility():
    """Test that agent still works without new subsystems."""
    # Create agent without new subsystems (backward compatibility)
    agent = Agent(
        name="OldAgent",
        llm=create_mock_llm(),
        system_prompt="You are helpful.",
    )

    assert agent.name == "OldAgent"
    assert agent.system_prompt == "You are helpful."
    assert agent.profile_manager is None
    print("✓ test_agent_backward_compatibility passed")


def test_profile_manager_integration():
    """Test ProfileManager integration."""
    profiles = [
        APIProfile(api_key="key1", model="gpt-4"),
        APIProfile(api_key="key2", model="gpt-4"),
    ]
    profile_manager = ProfileManager(
        profiles=profiles,
        fallback_models=["gpt-4", "gpt-3.5-turbo"],
    )

    agent = Agent(llm=create_mock_llm(), profile_manager=profile_manager)

    # Verify profile manager is accessible
    assert agent.profile_manager is not None
    assert len(agent.profile_manager.profiles) == 2

    # Test profile rotation
    p1 = agent.profile_manager.get_next_profile()
    assert p1.api_key == "key1"

    p2 = agent.profile_manager.get_next_profile()
    assert p2.api_key == "key2"
    print("✓ test_profile_manager_integration passed")


def test_event_callback_integration():
    """Test event callback integration."""
    from pig_agent_core.observability.events import (
        AgentEvent as Event,
    )
    from pig_agent_core.observability.events import (
        AgentEventType,
        emit,
    )

    events = []

    def callback(event: Event):
        events.append(event)

    agent = Agent(llm=create_mock_llm(), event_callback=callback)

    # Verify callback is accessible
    assert agent.event_callback is not None

    # Test callback works
    test_event = Event(
        type=AgentEventType.AGENT_START,
        data={"agent_id": agent.name},
    )
    emit(agent.event_callback, test_event)

    assert len(events) == 1
    assert events[0].type == AgentEventType.AGENT_START
    print("✓ test_event_callback_integration passed")


def test_compress_fn_integration():
    """Test compress function integration."""

    def compress_fn(messages):
        # Keep only last 3 messages
        return messages[-3:]

    agent = Agent(llm=create_mock_llm(), compress_fn=compress_fn)

    # Verify compress function is accessible
    assert agent.compress_fn is not None

    # Test compression
    messages = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "2"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "5"},
    ]

    compressed = agent.compress_fn(messages)
    assert len(compressed) == 3
    assert compressed[0]["content"] == "3"
    print("✓ test_compress_fn_integration passed")


def test_all_subsystems_together():
    """Test all subsystems working together."""
    from pig_agent_core.observability.events import (
        AgentEvent as Event,
    )
    from pig_agent_core.observability.events import (
        AgentEventType,
        emit,
    )

    # Create all subsystems
    profiles = [APIProfile(api_key="key1", model="gpt-4")]
    profile_manager = ProfileManager(profiles=profiles)

    events = []

    def event_callback(event):
        events.append(event)

    def compress_fn(messages):
        return messages[-5:]

    # Create agent with everything
    agent = Agent(
        name="FullAgent",
        llm=create_mock_llm(),
        system_prompt="Test",
        profile_manager=profile_manager,
        event_callback=event_callback,
        compress_fn=compress_fn,
    )

    # Verify all subsystems are present
    assert agent.profile_manager is not None
    assert agent.event_callback is not None
    assert agent.compress_fn is not None

    # Test they all work
    assert agent.profile_manager.get_next_profile().api_key == "key1"

    emit(
        agent.event_callback,
        Event(type=AgentEventType.AGENT_START, data={}),
    )
    assert len(events) == 1

    compressed = agent.compress_fn([1, 2, 3, 4, 5, 6, 7])
    assert len(compressed) == 5
    print("✓ test_all_subsystems_together passed")


def main():
    """Run all tests."""
    print("Running Agent integration tests...")
    print()

    test_agent_initialization()
    test_agent_has_subsystems()
    test_agent_backward_compatibility()
    test_profile_manager_integration()
    test_event_callback_integration()
    test_compress_fn_integration()
    test_all_subsystems_together()

    print()
    print("All integration tests passed! ✓")


if __name__ == "__main__":
    main()
