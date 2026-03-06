"""Tests for Feishu compatibility adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pig_messenger.base import MessengerType


@pytest.fixture
def adapter():
    """Create Feishu compat adapter."""
    with patch("pig_messenger.adapters.feishu_compat.FeishuAdapter"):
        from pig_messenger.adapters.feishu_compat import FeishuMessengerAdapter

        adapter = FeishuMessengerAdapter(
            app_id="app123",
            app_secret="secret123",
        )
        adapter.adapter = MagicMock()
        adapter.adapter.send_message = AsyncMock(return_value="msg123")
        adapter.adapter.handle_event = AsyncMock()
        return adapter


def test_feishu_compat_capabilities(adapter):
    """Test Feishu compat capabilities."""
    caps = adapter.capabilities
    assert caps.can_edit is True
    assert caps.supports_blocks is True
    assert caps.max_message_length == 10000


@pytest.mark.asyncio
async def test_parse_event(adapter):
    """Test parsing event."""
    raw_event = {
        "event": {
            "type": "message",
            "message": {
                "message_id": "msg123",
                "chat_id": "chat456",
                "content": "Hello",
                "chat_type": "p2p",
            },
            "sender": {
                "sender_id": {
                    "open_id": "user789",
                    "user_id": "user789",
                },
            },
        }
    }

    message = await adapter.parse_event(raw_event)
    assert message is not None
    assert message.platform == MessengerType.FEISHU
    assert message.message_id == "msg123"
    assert message.text == "Hello"


@pytest.mark.asyncio
async def test_send_message(adapter):
    """Test sending message."""
    result = await adapter.send_message("chat456", "Test")
    assert result["message_id"] == "msg123"
    adapter.adapter.send_message.assert_called_once()
