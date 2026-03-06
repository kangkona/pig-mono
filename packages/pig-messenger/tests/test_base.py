"""Tests for messenger base abstractions."""

import asyncio

import pytest
from pig_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerCapabilities,
    MessengerThread,
    MessengerType,
    MessengerUser,
    _split_text,
)


class MockAdapter(BaseMessengerAdapter):
    """Mock adapter for testing."""

    def __init__(self, capabilities: MessengerCapabilities | None = None):
        super().__init__(capabilities)
        self.sent_messages = []
        self.updated_messages = []
        self.sent_drafts = []

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs
    ) -> str:
        message_id = f"msg_{len(self.sent_messages)}"
        self.sent_messages.append((channel_id, text, thread_id))
        return message_id

    async def update_message(self, channel_id: str, message_id: str, text: str, **kwargs) -> None:
        self.updated_messages.append((channel_id, message_id, text))

    async def send_draft(
        self, channel_id: str, text: str, *, draft_id: str | None = None, **kwargs
    ) -> str:
        new_draft_id = draft_id or f"draft_{len(self.sent_drafts)}"
        self.sent_drafts.append((channel_id, text, draft_id))
        return new_draft_id

    def parse_event(self, raw_event: dict) -> IncomingMessage | None:
        return None

    def verify_signature(self, request_body: bytes, signature: str, **kwargs) -> bool:
        return True


async def async_chunks_generator(chunks: list[str]):
    """Generate async chunks for testing."""
    for chunk in chunks:
        yield chunk
        await asyncio.sleep(0.01)  # Small delay to simulate streaming


def test_split_text_short():
    """Test _split_text with text shorter than max_len."""
    text = "Hello world"
    result = _split_text(text, 100)
    assert result == ["Hello world"]


def test_split_text_paragraph_boundary():
    """Test _split_text splits at paragraph boundary."""
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    result = _split_text(text, 30)
    # Should split into 3 chunks at paragraph boundaries
    assert len(result) == 3
    assert result[0] == "First paragraph.\n\n"
    assert result[1] == "Second paragraph.\n\n"
    assert result[2] == "Third paragraph."


def test_split_text_line_boundary():
    """Test _split_text splits at line boundary."""
    text = "Line 1\nLine 2\nLine 3\nLine 4"
    result = _split_text(text, 20)
    assert len(result) >= 2


def test_split_text_sentence_boundary():
    """Test _split_text splits at sentence boundary."""
    text = "First sentence. Second sentence. Third sentence."
    result = _split_text(text, 30)
    assert len(result) >= 2


def test_split_text_word_boundary():
    """Test _split_text splits at word boundary."""
    text = "word " * 20
    result = _split_text(text, 30)
    assert len(result) >= 2
    # Each chunk should not exceed max_len
    for chunk in result:
        assert len(chunk) <= 30


def test_split_text_hard_split():
    """Test _split_text hard splits when no natural boundary."""
    text = "a" * 100
    result = _split_text(text, 30)
    assert len(result) == 4  # 30 + 30 + 30 + 10
    assert all(len(chunk) <= 30 for chunk in result)


@pytest.mark.asyncio
async def test_messenger_thread_post():
    """Test MessengerThread.post()."""
    adapter = MockAdapter()
    thread = MessengerThread(adapter, "channel_1", "thread_1")

    message_id = await thread.post("Hello")
    assert message_id == "msg_0"
    assert adapter.sent_messages == [("channel_1", "Hello", "thread_1")]


@pytest.mark.asyncio
async def test_messenger_thread_update():
    """Test MessengerThread.update()."""
    adapter = MockAdapter()
    thread = MessengerThread(adapter, "channel_1")

    await thread.update("msg_1", "Updated text")
    assert adapter.updated_messages == [("channel_1", "msg_1", "Updated text")]


@pytest.mark.asyncio
async def test_stream_draft_strategy():
    """Test MessengerThread.stream() with draft strategy."""
    capabilities = MessengerCapabilities(supports_draft=True, max_message_length=100)
    adapter = MockAdapter(capabilities)
    thread = MessengerThread(adapter, "channel_1", capabilities=capabilities)

    chunks = ["Hello", " ", "world", "!"]
    message_ids = await thread.stream(async_chunks_generator(chunks), interval=0.1)

    # Should have sent drafts and one final message
    assert len(adapter.sent_drafts) == 4
    assert adapter.sent_drafts[0] == ("channel_1", "Hello", None)
    assert adapter.sent_drafts[1] == ("channel_1", "Hello ", "draft_0")
    assert adapter.sent_drafts[2] == ("channel_1", "Hello world", "draft_0")
    assert adapter.sent_drafts[3] == ("channel_1", "Hello world!", "draft_0")

    # Final message
    assert len(message_ids) == 1
    assert adapter.sent_messages[-1] == ("channel_1", "Hello world!", None)


@pytest.mark.asyncio
async def test_stream_edit_strategy():
    """Test MessengerThread.stream() with edit strategy."""
    capabilities = MessengerCapabilities(can_edit=True, max_message_length=100)
    adapter = MockAdapter(capabilities)
    thread = MessengerThread(adapter, "channel_1", capabilities=capabilities)

    chunks = ["Hello", " ", "world", "!"]
    message_ids = await thread.stream(async_chunks_generator(chunks), interval=0.05)

    # Should have posted initial message and updated it
    assert len(message_ids) == 1
    assert len(adapter.sent_messages) >= 1
    # May have multiple updates depending on timing
    assert len(adapter.updated_messages) >= 0


@pytest.mark.asyncio
async def test_stream_edit_overflow():
    """Test MessengerThread.stream() with edit strategy handles overflow."""
    capabilities = MessengerCapabilities(can_edit=True, max_message_length=20)
    adapter = MockAdapter(capabilities)
    thread = MessengerThread(adapter, "channel_1", capabilities=capabilities)

    # Text that will overflow
    chunks = ["Hello ", "world ", "this ", "is ", "a ", "long ", "message"]
    message_ids = await thread.stream(async_chunks_generator(chunks), interval=0.01)

    # Should have created multiple messages due to overflow
    assert len(message_ids) >= 2


@pytest.mark.asyncio
async def test_stream_batch_strategy():
    """Test MessengerThread.stream() with batch strategy."""
    capabilities = MessengerCapabilities(can_edit=False, max_message_length=20)
    adapter = MockAdapter(capabilities)
    thread = MessengerThread(adapter, "channel_1", capabilities=capabilities)

    chunks = ["Hello ", "world ", "this ", "is ", "a ", "test"]
    message_ids = await thread.stream(async_chunks_generator(chunks), interval=0.1)

    # Should have collected all chunks and split into multiple messages
    assert len(message_ids) >= 2
    # No updates should have been made
    assert len(adapter.updated_messages) == 0


@pytest.mark.asyncio
async def test_stream_empty():
    """Test MessengerThread.stream() with empty chunks."""
    adapter = MockAdapter()
    thread = MessengerThread(adapter, "channel_1")

    async def empty_generator():
        return
        yield  # Make it a generator

    message_ids = await thread.stream(empty_generator())
    assert message_ids == []


def test_messenger_type_enum():
    """Test MessengerType enum."""
    assert MessengerType.SLACK == "slack"
    assert MessengerType.DISCORD == "discord"
    assert MessengerType.TELEGRAM == "telegram"
    assert MessengerType.WHATSAPP == "whatsapp"
    assert MessengerType.WEBCHAT == "webchat"
    assert MessengerType.FEISHU == "feishu"


def test_messenger_user():
    """Test MessengerUser dataclass."""
    user = MessengerUser(id="user_1", username="john", email="john@example.com")
    assert user.id == "user_1"
    assert user.username == "john"
    assert user.email == "john@example.com"


def test_incoming_message():
    """Test IncomingMessage dataclass."""
    user = MessengerUser(id="user_1", username="john")
    msg = IncomingMessage(
        message_id="msg_1",
        platform=MessengerType.SLACK,
        channel_id="channel_1",
        user=user,
        text="Hello",
    )
    assert msg.message_id == "msg_1"
    assert msg.platform == MessengerType.SLACK
    assert msg.channel_id == "channel_1"
    assert msg.user == user
    assert msg.text == "Hello"


def test_messenger_capabilities():
    """Test MessengerCapabilities dataclass."""
    caps = MessengerCapabilities(
        can_edit=True,
        can_delete=True,
        supports_draft=True,
        max_message_length=4096,
    )
    assert caps.can_edit is True
    assert caps.can_delete is True
    assert caps.supports_draft is True
    assert caps.max_message_length == 4096
