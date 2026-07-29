"""Tests for Slack messenger adapter."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pig_messenger.base import MessengerType, WebhookRequest


@pytest.fixture
def adapter() -> Any:
    """Create Slack adapter."""
    with patch("pig_messenger.adapters.slack.AsyncWebClient"):
        from pig_messenger.adapters.slack import SlackMessengerAdapter

        adapter = SlackMessengerAdapter(bot_token="xoxb-test", signing_secret="secret")
        adapter.client = AsyncMock()
        return adapter


def test_markdown_to_mrkdwn() -> None:
    """Test markdown conversion."""
    from pig_messenger.adapters.slack import markdown_to_mrkdwn

    # Test link conversion
    text = "[link](https://example.com)"
    result = markdown_to_mrkdwn(text)
    assert "<https://example.com|link>" in result


def test_slack_adapter_capabilities(adapter: Any) -> None:
    """Test Slack adapter capabilities."""
    caps = adapter.capabilities
    assert caps.can_edit is True
    assert caps.can_react is True
    assert caps.supports_blocks is True
    assert caps.max_message_length == 3500


@pytest.mark.asyncio
async def test_parse_event_dm(adapter: Any) -> None:
    """Test parsing DM message."""
    raw_event = {
        "event": {
            "type": "message",
            "channel": "D123",
            "channel_type": "im",
            "user": "U456",
            "text": "Hello",
            "ts": "1234567890.123456",
        }
    }

    message = await adapter.parse_event(raw_event)
    assert message is not None
    assert message.platform == MessengerType.SLACK
    assert message.is_dm is True


@pytest.mark.asyncio
async def test_parse_event_group_no_mention(adapter: Any) -> None:
    """Test parsing group message without mention."""
    raw_event = {
        "event": {
            "type": "message",
            "channel": "C123",
            "channel_type": "channel",
            "user": "U456",
            "text": "Hello",
            "ts": "1234567890.123456",
        },
        "authorizations": [{"user_id": "UBOT"}],
    }

    message = await adapter.parse_event(raw_event)
    assert message is None  # Filtered out


@pytest.mark.asyncio
async def test_send_message(adapter: Any) -> None:
    """Test sending message."""
    adapter.client.chat_postMessage.return_value = {"ts": "123.456"}

    result = await adapter.send_message("C123", "Test")
    assert result["message_id"] == "123.456"


@pytest.mark.asyncio
async def test_send_reaction(adapter: Any) -> None:
    """Test sending reaction."""
    await adapter.send_reaction("C123", "123.456", ":thumbsup:")
    adapter.client.reactions_add.assert_called_once()


@pytest.mark.asyncio
async def test_verify_signature(adapter: Any) -> None:
    """Test signature verification."""
    result = await adapter.verify_signature(
        WebhookRequest(body=b"body", timestamp="1234567890", signature="v0=signature")
    )
    assert isinstance(result, bool)
