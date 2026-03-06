"""Tests for Telegram messenger adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pig_messenger.adapters.telegram import TelegramMessengerAdapter
from pig_messenger.base import MessengerType


@pytest.fixture
def adapter():
    """Create Telegram adapter."""
    adapter = TelegramMessengerAdapter(bot_token="test_token")
    # Mock the HTTP client
    adapter.client = AsyncMock()
    return adapter


def test_telegram_adapter_capabilities(adapter):
    """Test Telegram adapter capabilities."""
    caps = adapter.capabilities
    assert caps.can_edit is True
    assert caps.can_delete is True
    assert caps.can_react is False
    assert caps.supports_draft is True
    assert caps.max_message_length == 4096


@pytest.mark.asyncio
async def test_parse_event_text_message(adapter):
    """Test parsing text message."""
    raw_event = {
        "message": {
            "message_id": 123,
            "from": {
                "id": 456,
                "username": "testuser",
                "first_name": "Test",
            },
            "chat": {
                "id": 789,
                "type": "private",
            },
            "text": "Hello world",
            "date": 1234567890,
        }
    }

    message = await adapter.parse_event(raw_event)
    assert message is not None
    assert message.message_id == "123"
    assert message.platform == MessengerType.TELEGRAM
    assert message.channel_id == "789"
    assert message.text == "Hello world"
    assert message.user.id == "456"
    assert message.user.username == "testuser"
    assert message.is_dm is True


@pytest.mark.asyncio
async def test_parse_event_no_message(adapter):
    """Test parsing event without message."""
    raw_event = {"update_id": 123}
    message = await adapter.parse_event(raw_event)
    assert message is None


@pytest.mark.asyncio
async def test_parse_event_no_text(adapter):
    """Test parsing event without text."""
    raw_event = {
        "message": {
            "message_id": 123,
            "from": {"id": 456},
            "chat": {"id": 789},
            "photo": [{"file_id": "abc"}],
        }
    }
    message = await adapter.parse_event(raw_event)
    assert message is None


@pytest.mark.asyncio
async def test_send_message(adapter):
    """Test sending message."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 999}}
    adapter.client.post.return_value = mock_response

    result = await adapter.send_message("789", "Test message")
    assert result["message_id"] == "999"
    adapter.client.post.assert_called_once()


@pytest.mark.asyncio
async def test_update_message(adapter):
    """Test updating message."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 999}}
    adapter.client.post.return_value = mock_response

    result = await adapter.update_message("789", "999", "Updated text")
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_delete_message(adapter):
    """Test deleting message."""
    mock_response = MagicMock()
    adapter.client.post.return_value = mock_response

    result = await adapter.delete_message("789", "999")
    assert result is True


@pytest.mark.asyncio
async def test_send_typing(adapter):
    """Test sending typing indicator."""
    await adapter.send_typing("789")
    adapter.client.post.assert_called_once()


@pytest.mark.asyncio
async def test_send_file(adapter):
    """Test sending file from URL."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 888}}
    adapter.client.post.return_value = mock_response

    result = await adapter.send_file("789", "https://example.com/file.pdf", "file.pdf")
    assert result["message_id"] == "888"


@pytest.mark.asyncio
async def test_send_file_content(adapter):
    """Test sending file from content."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 777}}
    adapter.client.post.return_value = mock_response

    result = await adapter.send_file_content("789", b"file content", "test.txt", "text/plain")
    assert result["message_id"] == "777"


@pytest.mark.asyncio
async def test_verify_signature(adapter):
    """Test signature verification."""
    signature = "test_signature"
    result = await adapter.verify_signature(b"request body", signature)
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_aclose(adapter):
    """Test closing adapter."""
    await adapter.aclose()
    adapter.client.aclose.assert_called_once()
