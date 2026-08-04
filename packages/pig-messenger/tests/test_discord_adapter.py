"""Tests for Discord messenger adapter."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pig_messenger.adapters.discord import DiscordMessengerAdapter
from pig_messenger.base import MessengerType, WebhookRequest


@pytest.fixture
def adapter() -> Any:
    """Create Discord adapter."""
    adapter = DiscordMessengerAdapter(bot_token="test_token", public_key="test_key")
    adapter.client = AsyncMock()
    return adapter


def test_discord_adapter_capabilities(adapter: Any) -> None:
    """Test Discord adapter capabilities."""
    caps = adapter.capabilities
    assert caps.can_edit is True
    assert caps.can_react is True
    assert caps.can_thread is True
    assert caps.max_message_length == 2000


@pytest.mark.asyncio
async def test_parse_event_message(adapter: Any) -> None:
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
async def test_parse_event_bot_message(adapter: Any) -> None:
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
async def test_send_message(adapter: Any) -> None:
    """Test sending message."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "999"}
    adapter.client.post.return_value = mock_response

    result = await adapter.send_message("456", "Test")
    assert result["message_id"] == "999"


@pytest.mark.asyncio
async def test_update_message(adapter: Any) -> None:
    """Test updating message."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "999"}
    adapter.client.patch.return_value = mock_response

    result = await adapter.update_message("456", "999", "Updated")
    assert result["id"] == "999"


@pytest.mark.asyncio
async def test_delete_message(adapter: Any) -> None:
    """Test deleting message."""
    mock_response = MagicMock()
    adapter.client.delete.return_value = mock_response

    result = await adapter.delete_message("456", "999")
    assert result is True


@pytest.mark.asyncio
async def test_send_reaction(adapter: Any) -> None:
    """Test sending reaction."""
    await adapter.send_reaction("456", "999", "👍")
    adapter.client.put.assert_called_once()


@pytest.mark.asyncio
async def test_verify_signature(adapter: Any) -> None:
    """Test signature verification."""
    private_key = Ed25519PrivateKey.generate()
    adapter.public_key = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex()
    )
    body = b"body"
    timestamp = "timestamp"
    signature = private_key.sign(timestamp.encode() + body).hex()
    result = await adapter.verify_signature(
        WebhookRequest(body=body, signature=signature, timestamp=timestamp)
    )
    assert result is True

    tampered = await adapter.verify_signature(
        WebhookRequest(body=b"tampered", signature=signature, timestamp=timestamp)
    )
    assert tampered is False


@pytest.mark.asyncio
async def test_verify_signature_fails_closed_without_public_key() -> None:
    adapter = DiscordMessengerAdapter(bot_token="test_token")

    assert await adapter.verify_signature(WebhookRequest(signature="signature")) is False
