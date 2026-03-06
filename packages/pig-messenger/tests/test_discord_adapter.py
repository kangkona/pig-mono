"""Tests for Discord messenger adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pig_messenger.adapters.discord import DiscordMessengerAdapter
from pig_messenger.base import MessengerType


@pytest.fixture
def adapter():
    """Create Discord adapter."""
    adapter = DiscordMessengerAdapter(bot_token="test_token", public_key="test_key")
    adapter.client = AsyncMock()
    return adapter


def test_discord_adapter_capabilities(adapter):
    """Test Discord adapter capabilities."""
    caps = adapter.capabilities
    assert caps.can_edit is True
    assert caps.can_react is True
    assert caps.can_thread is True
    assert caps.max_message_length == 2000


@pytest.mark.asyncio
async def test_parse_event_message(adapter):
    """Test parsing message event."""
    raw_event = {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": "123",
            "channel_id": "456",
            "content": "Hello",
            "author": {
                "id": "789",
                "username": "testuser",
                "bot": False,
            },
        },
    }

    message = await adapter.parse_event(raw_event)
    assert message is not None
    assert message.platform == MessengerType.DISCORD
    assert message.message_id == "123"
    assert message.text == "Hello"


@pytest.mark.asyncio
async def test_parse_event_bot_message(adapter):
    """Test parsing bot message."""
    raw_event = {
        "t": "MESSAGE_CREATE",
        "d": {
            "author": {"bot": True},
        },
    }

    message = await adapter.parse_event(raw_event)
    assert message is None


@pytest.mark.asyncio
async def test_send_message(adapter):
    """Test sending message."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "999"}
    adapter.client.post.return_value = mock_response

    result = await adapter.send_message("456", "Test")
    assert result["message_id"] == "999"


@pytest.mark.asyncio
async def test_update_message(adapter):
    """Test updating message."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "999"}
    adapter.client.patch.return_value = mock_response

    result = await adapter.update_message("456", "999", "Updated")
    assert result["id"] == "999"


@pytest.mark.asyncio
async def test_delete_message(adapter):
    """Test deleting message."""
    mock_response = MagicMock()
    adapter.client.delete.return_value = mock_response

    result = await adapter.delete_message("456", "999")
    assert result is True


@pytest.mark.asyncio
async def test_send_reaction(adapter):
    """Test sending reaction."""
    await adapter.send_reaction("456", "999", "👍")
    adapter.client.put.assert_called_once()


@pytest.mark.asyncio
async def test_verify_signature(adapter):
    """Test signature verification."""
    result = await adapter.verify_signature(b"body", "sig", "timestamp")
    assert isinstance(result, bool)
