"""Tests for context management."""

import pytest
from pig_agent_core.context import CachedContext, build_messages, hydrate


@pytest.mark.asyncio
async def test_hydrate_returns_context():
    """Test hydrate returns CachedContext."""
    ctx = await hydrate("user123")

    assert isinstance(ctx, CachedContext)
    assert ctx.system_prompt != ""
    assert "user_id" in ctx.user_config


@pytest.mark.asyncio
async def test_hydrate_with_different_users():
    """Test hydrate with different user IDs."""
    ctx1 = await hydrate("user1")
    ctx2 = await hydrate("user2")

    assert ctx1.user_config["user_id"] == "user1"
    assert ctx2.user_config["user_id"] == "user2"


def test_cached_context_defaults():
    """Test CachedContext default values."""
    ctx = CachedContext()

    assert ctx.system_prompt == ""
    assert ctx.user_config == {}
    assert ctx.metadata == {}


def test_cached_context_with_values():
    """Test CachedContext with custom values."""
    ctx = CachedContext(
        system_prompt="Custom prompt",
        user_config={"key": "value"},
        metadata={"meta": "data"},
    )

    assert ctx.system_prompt == "Custom prompt"
    assert ctx.user_config == {"key": "value"}
    assert ctx.metadata == {"meta": "data"}


def test_build_messages_with_system_prompt():
    """Test building messages with system prompt."""
    ctx = CachedContext(system_prompt="You are helpful")
    history = []
    user_text = "Hello"

    messages = build_messages(ctx, history, user_text)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are helpful"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Hello"


def test_build_messages_without_system_prompt():
    """Test building messages without system prompt."""
    ctx = CachedContext(system_prompt="")
    history = []
    user_text = "Hello"

    messages = build_messages(ctx, history, user_text)

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"


def test_build_messages_with_history():
    """Test building messages with conversation history."""
    ctx = CachedContext(system_prompt="System")
    history = [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Second message"},
        {"role": "assistant", "content": "Second response"},
    ]
    user_text = "Third message"

    messages = build_messages(ctx, history, user_text)

    assert len(messages) == 6  # system + 4 history + 1 new
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "First message"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Third message"


def test_build_messages_preserves_history_order():
    """Test that message building preserves history order."""
    ctx = CachedContext(system_prompt="System")
    history = [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": "B"},
        {"role": "user", "content": "C"},
    ]
    user_text = "D"

    messages = build_messages(ctx, history, user_text)

    # Check order: system, A, B, C, D
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "A"
    assert messages[2]["content"] == "B"
    assert messages[3]["content"] == "C"
    assert messages[4]["content"] == "D"


def test_build_messages_empty_history():
    """Test building messages with empty history."""
    ctx = CachedContext(system_prompt="System")
    history = []
    user_text = "Hello"

    messages = build_messages(ctx, history, user_text)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_build_messages_with_tool_messages():
    """Test building messages with tool messages in history."""
    ctx = CachedContext(system_prompt="System")
    history = [
        {"role": "user", "content": "Search for X"},
        {"role": "assistant", "content": "", "tool_calls": [{"name": "search"}]},
        {"role": "tool", "content": "Results", "name": "search"},
        {"role": "assistant", "content": "Here are the results"},
    ]
    user_text = "Thanks"

    messages = build_messages(ctx, history, user_text)

    assert len(messages) == 6  # system + 4 history + 1 new
    assert messages[2]["role"] == "tool"
    assert messages[-1]["content"] == "Thanks"


@pytest.mark.asyncio
async def test_hydrate_is_async():
    """Test that hydrate is an async function."""
    import inspect

    assert inspect.iscoroutinefunction(hydrate)


def test_cached_context_is_dataclass():
    """Test that CachedContext is a dataclass."""
    from dataclasses import is_dataclass

    assert is_dataclass(CachedContext)
