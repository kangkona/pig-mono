"""Tests for messenger base abstractions."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pig_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerCapabilities,
    MessengerThread,
    MessengerType,
    MessengerUser,
    WebhookRequest,
    _split_text,
)


class MockAdapter(BaseMessengerAdapter):
    """Mock adapter for testing."""

    def __init__(self, capabilities: MessengerCapabilities | None = None) -> None:
        super().__init__(capabilities)
        self.sent_messages: list[tuple[str, str, str | None]] = []
        self.updated_messages: list[tuple[str, str, str]] = []
        self.sent_drafts: list[tuple[str, str, str | None]] = []

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs: Any
    ) -> str:
        message_id = f"msg_{len(self.sent_messages)}"
        self.sent_messages.append((channel_id, text, thread_id))
        return message_id

    async def update_message(
        self, channel_id: str, message_id: str, text: str, **kwargs: Any
    ) -> None:
        self.updated_messages.append((channel_id, message_id, text))

    async def send_draft(
        self, channel_id: str, text: str, *, draft_id: str | None = None, **kwargs: Any
    ) -> str:
        new_draft_id = draft_id or f"draft_{len(self.sent_drafts)}"
        self.sent_drafts.append((channel_id, text, draft_id))
        return new_draft_id

    async def parse_event(self, raw_event: dict) -> IncomingMessage | None:
        return None

    async def verify_signature(self, request: WebhookRequest) -> bool:
        return True


async def async_chunks_generator(chunks: list[str]) -> Any:
    """Generate async chunks for testing."""
    for chunk in chunks:
        yield chunk
        await asyncio.sleep(0.01)  # Small delay to simulate streaming


def test_signature_verification_is_required_by_adapter_contract() -> None:
    """Webhook authentication remains a required adapter capability."""
    assert "verify_signature" in BaseMessengerAdapter.__abstractmethods__


@pytest.mark.asyncio
async def test_signature_verification_is_polymorphic() -> None:
    """Callers can verify a webhook through the base adapter interface."""
    adapter: BaseMessengerAdapter = MockAdapter()
    assert await adapter.verify_signature(WebhookRequest(signature="test")) is True


def test_split_text_short() -> None:
    """Test _split_text with text shorter than max_len."""
    text = "Hello world"
    result = _split_text(text, 100)
    assert result == ["Hello world"]


def test_split_text_paragraph_boundary() -> None:
    """Test _split_text splits at paragraph boundary."""
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    result = _split_text(text, 30)
    # Should split into 3 chunks at paragraph boundaries
    assert len(result) == 3
    assert result[0] == "First paragraph.\n\n"
    assert result[1] == "Second paragraph.\n\n"
    assert result[2] == "Third paragraph."


def test_split_text_line_boundary() -> None:
    """Test _split_text splits at line boundary."""
    text = "Line 1\nLine 2\nLine 3\nLine 4"
    result = _split_text(text, 20)
    assert len(result) >= 2


def test_split_text_sentence_boundary() -> None:
    """Test _split_text splits at sentence boundary."""
    text = "First sentence. Second sentence. Third sentence."
    result = _split_text(text, 30)
    assert len(result) >= 2


def test_split_text_word_boundary() -> None:
    """Test _split_text splits at word boundary."""
    text = "word " * 20
    result = _split_text(text, 30)
    assert len(result) >= 2
    # Each chunk should not exceed max_len
    for chunk in result:
        assert len(chunk) <= 30


def test_split_text_hard_split() -> None:
    """Test _split_text hard splits when no natural boundary."""
    text = "a" * 100
    result = _split_text(text, 30)
    assert len(result) == 4  # 30 + 30 + 30 + 10
    assert all(len(chunk) <= 30 for chunk in result)


@pytest.mark.asyncio
async def test_messenger_thread_post() -> None:
    """Test MessengerThread.post()."""
    adapter = MockAdapter()
    thread = MessengerThread(adapter, "channel_1", "thread_1")

    message_id = await thread.post("Hello")
    assert message_id == "msg_0"
    assert adapter.sent_messages == [("channel_1", "Hello", "thread_1")]


@pytest.mark.asyncio
async def test_messenger_thread_post_normalizes_mapping_response() -> None:
    """Provider response mappings expose their message ID through thread helpers."""
    adapter = MockAdapter()
    with patch.object(
        adapter, "send_message", AsyncMock(return_value={"message_id": "provider_msg_1"})
    ):
        thread = MessengerThread(adapter, "channel_1")
        assert await thread.post("Hello") == "provider_msg_1"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{}, {"message_id": ""}, {"message_id": None}])
async def test_messenger_thread_post_rejects_malformed_mapping_response(
    response: dict[str, object],
) -> None:
    """Provider mappings must contain a non-empty string message ID."""
    adapter = MockAdapter()
    with patch.object(adapter, "send_message", AsyncMock(return_value=response)):
        thread = MessengerThread(adapter, "channel_1")
        error_type = TypeError if response.get("message_id", "") is None else ValueError
        with pytest.raises(error_type) as exc_info:
            await thread.post("secret message body")

    error = str(exc_info.value)
    assert "message_id" in error
    assert repr(tuple(sorted(response))) in error
    assert "secret message body" not in error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"draft_id": "draft_1"}, "draft_1"),
        ({"message_id": "message_1"}, "message_1"),
        ({"draft_id": "", "message_id": "message_2"}, "message_2"),
        ({"draft_id": 7, "message_id": "message_3"}, "message_3"),
    ],
)
async def test_stream_draft_accepts_either_response_identifier(
    response: dict[str, object], expected: str
) -> None:
    """Draft providers may identify a draft with either supported key."""
    capabilities = MessengerCapabilities(supports_draft=True)
    adapter = MockAdapter(capabilities)
    with patch.object(adapter, "send_draft", AsyncMock(return_value=response)) as send_draft:
        thread = MessengerThread(adapter, "channel_1", capabilities=capabilities)
        await thread.stream(async_chunks_generator(["one", "two"]))

    assert send_draft.await_args_list[1].kwargs["draft_id"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{}, {"draft_id": "", "message_id": ""}, {"draft_id": 7}])
async def test_stream_draft_rejects_malformed_mapping_response(
    response: dict[str, object],
) -> None:
    """Draft streaming fails closed when neither response ID is usable."""
    capabilities = MessengerCapabilities(supports_draft=True)
    adapter = MockAdapter(capabilities)
    with patch.object(adapter, "send_draft", AsyncMock(return_value=response)):
        thread = MessengerThread(adapter, "channel_1", capabilities=capabilities)
        error_type = TypeError if response.get("draft_id") == 7 else ValueError
        with pytest.raises(error_type) as exc_info:
            await thread.stream(async_chunks_generator(["secret draft body"]))

    error = str(exc_info.value)
    assert "draft_id" in error
    assert "message_id" in error
    assert repr(tuple(sorted(response))) in error
    assert "secret draft body" not in error


@pytest.mark.asyncio
async def test_messenger_thread_update() -> None:
    """Test MessengerThread.update()."""
    adapter = MockAdapter()
    thread = MessengerThread(adapter, "channel_1")

    await thread.update("msg_1", "Updated text")
    assert adapter.updated_messages == [("channel_1", "msg_1", "Updated text")]


@pytest.mark.asyncio
async def test_stream_draft_strategy() -> None:
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
async def test_stream_edit_strategy() -> None:
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
async def test_stream_edit_overflow() -> None:
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
async def test_stream_batch_strategy() -> None:
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
async def test_stream_empty() -> None:
    """Test MessengerThread.stream() with empty chunks."""
    adapter = MockAdapter()
    thread = MessengerThread(adapter, "channel_1")

    async def empty_generator() -> Any:
        return
        yield  # Make it a generator

    message_ids = await thread.stream(empty_generator())
    assert message_ids == []


def test_messenger_type_enum() -> None:
    """Test MessengerType enum."""
    assert MessengerType.SLACK.value == "slack"
    assert MessengerType.DISCORD.value == "discord"
    assert MessengerType.TELEGRAM.value == "telegram"
    assert MessengerType.WHATSAPP.value == "whatsapp"
    assert MessengerType.WEBCHAT.value == "webchat"
    assert MessengerType.FEISHU.value == "feishu"


def test_messenger_user() -> None:
    """Test MessengerUser dataclass."""
    user = MessengerUser(id="user_1", username="john", email="john@example.com")
    assert user.id == "user_1"
    assert user.username == "john"
    assert user.email == "john@example.com"


def test_incoming_message() -> None:
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


def test_messenger_capabilities() -> None:
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
