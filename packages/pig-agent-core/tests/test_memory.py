"""Tests for memory module."""

import pytest
from pig_agent_core.memory import InMemoryProvider, Message


class TestMessage:
    """Test Message dataclass."""

    def test_basic_message(self):
        """Test creating a basic message."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        assert msg.name is None

    def test_message_with_tool_calls(self):
        """Test message with tool calls."""
        tool_calls = [{"id": "call_1", "function": {"name": "search", "arguments": "{}"}}]
        msg = Message(role="assistant", content="", tool_calls=tool_calls)
        assert msg.tool_calls == tool_calls

    def test_message_with_tool_call_id(self):
        """Test tool result message."""
        msg = Message(
            role="tool",
            content="Result",
            tool_call_id="call_1",
            name="search",
        )
        assert msg.tool_call_id == "call_1"
        assert msg.name == "search"

    def test_model_dump_basic(self):
        """Test model_dump for basic message."""
        msg = Message(role="user", content="Hello")
        dumped = msg.model_dump()
        assert dumped == {"role": "user", "content": "Hello"}

    def test_model_dump_with_tool_calls(self):
        """Test model_dump with tool calls."""
        tool_calls = [{"id": "call_1"}]
        msg = Message(role="assistant", content="", tool_calls=tool_calls)
        dumped = msg.model_dump()
        assert dumped["tool_calls"] == tool_calls

    def test_model_dump_with_tool_result(self):
        """Test model_dump for tool result."""
        msg = Message(
            role="tool",
            content="Result",
            tool_call_id="call_1",
            name="search",
        )
        dumped = msg.model_dump()
        assert dumped["tool_call_id"] == "call_1"
        assert dumped["name"] == "search"


class TestInMemoryProvider:
    """Test InMemoryProvider implementation."""

    @pytest.mark.asyncio
    async def test_empty_session(self):
        """Test getting messages from empty session."""
        provider = InMemoryProvider()
        messages = await provider.get_messages("session_1")
        assert messages == []

    @pytest.mark.asyncio
    async def test_add_and_get_message(self):
        """Test adding and retrieving a message."""
        provider = InMemoryProvider()
        msg = Message(role="user", content="Hello")

        await provider.add_message("session_1", msg)
        messages = await provider.get_messages("session_1")

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_multiple_messages(self):
        """Test adding multiple messages."""
        provider = InMemoryProvider()

        msg1 = Message(role="user", content="Hello")
        msg2 = Message(role="assistant", content="Hi there")
        msg3 = Message(role="user", content="How are you?")

        await provider.add_message("session_1", msg1)
        await provider.add_message("session_1", msg2)
        await provider.add_message("session_1", msg3)

        messages = await provider.get_messages("session_1")
        assert len(messages) == 3
        assert messages[0].content == "Hello"
        assert messages[1].content == "Hi there"
        assert messages[2].content == "How are you?"

    @pytest.mark.asyncio
    async def test_multiple_sessions(self):
        """Test messages are isolated per session."""
        provider = InMemoryProvider()

        msg1 = Message(role="user", content="Session 1")
        msg2 = Message(role="user", content="Session 2")

        await provider.add_message("session_1", msg1)
        await provider.add_message("session_2", msg2)

        messages1 = await provider.get_messages("session_1")
        messages2 = await provider.get_messages("session_2")

        assert len(messages1) == 1
        assert len(messages2) == 1
        assert messages1[0].content == "Session 1"
        assert messages2[0].content == "Session 2"

    @pytest.mark.asyncio
    async def test_clear_messages(self):
        """Test clearing messages."""
        provider = InMemoryProvider()

        msg = Message(role="user", content="Hello")
        await provider.add_message("session_1", msg)

        await provider.clear_messages("session_1")
        messages = await provider.get_messages("session_1")

        assert messages == []

    @pytest.mark.asyncio
    async def test_clear_nonexistent_session(self):
        """Test clearing messages from nonexistent session."""
        provider = InMemoryProvider()
        await provider.clear_messages("nonexistent")
        # Should not raise error

    @pytest.mark.asyncio
    async def test_get_metadata_empty(self):
        """Test getting metadata from empty session."""
        provider = InMemoryProvider()
        metadata = await provider.get_metadata("session_1")
        assert metadata == {}

    @pytest.mark.asyncio
    async def test_set_and_get_metadata(self):
        """Test setting and getting metadata."""
        provider = InMemoryProvider()
        metadata = {"user_id": "user_123", "preferences": {"theme": "dark"}}

        await provider.set_metadata("session_1", metadata)
        retrieved = await provider.get_metadata("session_1")

        assert retrieved == metadata

    @pytest.mark.asyncio
    async def test_metadata_isolation(self):
        """Test metadata is isolated per session."""
        provider = InMemoryProvider()

        await provider.set_metadata("session_1", {"key": "value1"})
        await provider.set_metadata("session_2", {"key": "value2"})

        meta1 = await provider.get_metadata("session_1")
        meta2 = await provider.get_metadata("session_2")

        assert meta1["key"] == "value1"
        assert meta2["key"] == "value2"

    @pytest.mark.asyncio
    async def test_update_metadata(self):
        """Test updating metadata."""
        provider = InMemoryProvider()

        await provider.set_metadata("session_1", {"key": "old"})
        await provider.set_metadata("session_1", {"key": "new"})

        metadata = await provider.get_metadata("session_1")
        assert metadata["key"] == "new"

    @pytest.mark.asyncio
    async def test_messages_with_tool_calls(self):
        """Test storing messages with tool calls."""
        provider = InMemoryProvider()

        tool_calls = [
            {
                "id": "call_1",
                "function": {"name": "search", "arguments": '{"query": "test"}'},
            }
        ]
        msg = Message(role="assistant", content="", tool_calls=tool_calls)

        await provider.add_message("session_1", msg)
        messages = await provider.get_messages("session_1")

        assert len(messages) == 1
        assert messages[0].tool_calls == tool_calls

    @pytest.mark.asyncio
    async def test_conversation_flow(self):
        """Test a complete conversation flow."""
        provider = InMemoryProvider()

        # System message
        await provider.add_message(
            "session_1",
            Message(role="system", content="You are a helpful assistant."),
        )

        # User message
        await provider.add_message(
            "session_1",
            Message(role="user", content="What's the weather?"),
        )

        # Assistant with tool call
        await provider.add_message(
            "session_1",
            Message(
                role="assistant",
                content="",
                tool_calls=[{"id": "call_1", "function": {"name": "get_weather"}}],
            ),
        )

        # Tool result
        await provider.add_message(
            "session_1",
            Message(
                role="tool",
                content="Sunny, 72°F",
                tool_call_id="call_1",
                name="get_weather",
            ),
        )

        # Final assistant response
        await provider.add_message(
            "session_1",
            Message(role="assistant", content="It's sunny and 72°F."),
        )

        messages = await provider.get_messages("session_1")
        assert len(messages) == 5
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[2].role == "assistant"
        assert messages[2].tool_calls is not None
        assert messages[3].role == "tool"
        assert messages[4].role == "assistant"
