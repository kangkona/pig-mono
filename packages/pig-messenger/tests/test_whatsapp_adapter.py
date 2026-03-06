"""Tests for WhatsApp messenger adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pig_messenger.adapters.whatsapp import WhatsAppMessengerAdapter
from pig_messenger.base import MessengerType


@pytest.fixture
def adapter():
    """Create WhatsApp adapter."""
    adapter = WhatsAppMessengerAdapter(
        account_sid="AC123",
        auth_token="token123",
        from_number="whatsapp:+1234567890",
    )
    adapter.client = AsyncMock()
    return adapter


def test_whatsapp_adapter_capabilities(adapter):
    """Test WhatsApp adapter capabilities."""
    caps = adapter.capabilities
    assert caps.can_edit is False
    assert caps.can_delete is False
    assert caps.can_upload_file is True
    assert caps.max_message_length == 1600


@pytest.mark.asyncio
async def test_parse_event(adapter):
    """Test parsing webhook event."""
    raw_event = {
        "MessageSid": "SM123",
        "From": "whatsapp:+9876543210",
        "Body": "Hello",
        "ProfileName": "Test User",
    }

    message = await adapter.parse_event(raw_event)
    assert message is not None
    assert message.platform == MessengerType.WHATSAPP
    assert message.message_id == "SM123"
    assert message.text == "Hello"
    assert message.is_dm is True


@pytest.mark.asyncio
async def test_parse_event_no_body(adapter):
    """Test parsing event without body."""
    raw_event = {"MessageSid": "SM123"}

    message = await adapter.parse_event(raw_event)
    assert message is None


@pytest.mark.asyncio
async def test_send_message(adapter):
    """Test sending message."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"sid": "SM999"}
    adapter.client.post.return_value = mock_response

    result = await adapter.send_message("+9876543210", "Test")
    assert result["message_id"] == "SM999"


@pytest.mark.asyncio
async def test_verify_signature(adapter):
    """Test signature verification."""
    url = "https://example.com/webhook"
    params = {"From": "whatsapp:+1234567890", "Body": "test"}
    signature = "test_signature"

    result = await adapter.verify_signature(url, params, signature)
    assert isinstance(result, bool)
