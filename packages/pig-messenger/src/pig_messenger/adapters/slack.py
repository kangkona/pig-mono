"""Slack messenger adapter."""

import hashlib
import hmac
import logging
import re
from typing import Any

try:
    from slack_sdk.web.async_client import AsyncWebClient
except ImportError:
    AsyncWebClient = None  # type: ignore

from pig_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerCapabilities,
    MessengerType,
    MessengerUser,
)

logger = logging.getLogger(__name__)


def markdown_to_mrkdwn(text: str) -> str:
    """Convert markdown to Slack mrkdwn format.

    Args:
        text: Markdown text

    Returns:
        Slack mrkdwn formatted text
    """
    # Preserve code blocks
    text = re.sub(r"```(\w+)?\n(.*?)\n```", r"```\2```", text, flags=re.DOTALL)

    # Convert bold: **text** or __text__ -> *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"__(.+?)__", r"*\1*", text)

    # Convert italic: *text* or _text_ -> _text_
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"_\1_", text)

    # Convert links: [text](url) -> <url|text>
    text = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", r"<\2|\1>", text)

    # Convert headers: # Header -> *Header*
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)

    return text


class SlackMessengerAdapter(BaseMessengerAdapter):
    """Slack messenger adapter with blocks and reactions."""

    def __init__(
        self,
        bot_token: str,
        signing_secret: str | None = None,
    ):
        """Initialize Slack adapter.

        Args:
            bot_token: Slack bot token
            signing_secret: Slack signing secret for verification
        """
        if AsyncWebClient is None:
            raise ImportError("slack_sdk is required for Slack adapter")

        self.bot_token = bot_token
        self.signing_secret = signing_secret
        self.client = AsyncWebClient(token=bot_token)

        self.capabilities = MessengerCapabilities(
            can_edit=True,
            can_delete=True,
            can_react=True,
            can_thread=True,
            can_upload_file=True,
            supports_blocks=True,
            supports_draft=False,
            max_message_length=3500,
        )

    async def parse_event(self, raw_event: dict[str, Any]) -> IncomingMessage | None:
        """Parse Slack event to IncomingMessage.

        Args:
            raw_event: Slack Events API payload

        Returns:
            IncomingMessage or None
        """
        # Handle URL verification
        if raw_event.get("type") == "url_verification":
            return None

        # Extract event
        event = raw_event.get("event", {})
        event_type = event.get("type")

        # Only handle message events
        if event_type != "message":
            return None

        # Skip bot messages and message changes
        if event.get("subtype") in ["bot_message", "message_changed"]:
            return None

        text = event.get("text", "")
        channel_id = event.get("channel", "")
        user_id = event.get("user", "")

        # Check if group channel
        channel_type = event.get("channel_type", "")
        is_group = channel_type in ["group", "channel"]

        # Group channel filtering: only respond to mentions or thread replies
        if is_group:
            bot_user_id = raw_event.get("authorizations", [{}])[0].get("user_id")
            is_mention = bot_user_id and f"<@{bot_user_id}>" in text
            is_thread_reply = "thread_ts" in event and event.get("thread_ts") != event.get("ts")

            if not (is_mention or is_thread_reply):
                return None

        user = MessengerUser(
            id=user_id,
            username="",  # Would need users.info API call
            display_name="",
        )

        return IncomingMessage(
            message_id=event.get("ts", ""),
            platform=MessengerType.SLACK,
            channel_id=channel_id,
            text=text,
            user=user,
            timestamp=float(event.get("ts", 0)),
            is_dm=channel_type == "im",
        )

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Send message to Slack.

        Args:
            channel_id: Channel ID
            text: Message text
            thread_id: Optional thread timestamp
            **kwargs: Additional parameters

        Returns:
            API response with message_id (ts)
        """
        response = await self.client.chat_postMessage(
            channel=channel_id,
            text=text,
            thread_ts=thread_id,
            **kwargs,
        )

        return {
            "message_id": response["ts"],
        }

    async def update_message(
        self, channel_id: str, message_id: str, text: str, **kwargs
    ) -> dict[str, Any]:
        """Update message in Slack.

        Args:
            channel_id: Channel ID
            message_id: Message timestamp
            text: New text
            **kwargs: Additional parameters

        Returns:
            API response
        """
        response = await self.client.chat_update(
            channel=channel_id,
            ts=message_id,
            text=text,
            **kwargs,
        )
        return response.data

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete message in Slack.

        Args:
            channel_id: Channel ID
            message_id: Message timestamp

        Returns:
            True if successful
        """
        await self.client.chat_delete(
            channel=channel_id,
            ts=message_id,
        )
        return True

    async def send_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        """Add reaction to message.

        Args:
            channel_id: Channel ID
            message_id: Message timestamp
            emoji: Emoji name (without colons)
        """
        await self.client.reactions_add(
            channel=channel_id,
            timestamp=message_id,
            name=emoji.strip(":"),
        )

    async def send_blocks(
        self,
        channel_id: str,
        blocks: list[dict[str, Any]],
        *,
        text_fallback: str = "",
        thread_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Send blocks to Slack.

        Args:
            channel_id: Channel ID
            blocks: Block Kit blocks
            text_fallback: Fallback text
            thread_id: Optional thread timestamp
            **kwargs: Additional parameters

        Returns:
            API response with message_id
        """
        response = await self.client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text=text_fallback,
            thread_ts=thread_id,
            **kwargs,
        )

        return {
            "message_id": response["ts"],
        }

    async def send_file(self, channel_id: str, url: str, filename: str, **kwargs) -> dict[str, Any]:
        """Send file from URL.

        Args:
            channel_id: Channel ID
            url: File URL
            filename: File name
            **kwargs: Additional parameters

        Returns:
            API response
        """
        # Slack doesn't support direct URL upload, would need to download first
        raise NotImplementedError("URL file upload not supported")

    async def send_file_content(
        self,
        channel_id: str,
        content: bytes,
        filename: str,
        content_type: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Send file from content.

        Args:
            channel_id: Channel ID
            content: File content
            filename: File name
            content_type: MIME type
            **kwargs: Additional parameters

        Returns:
            API response
        """
        response = await self.client.files_upload_v2(
            channel=channel_id,
            content=content,
            filename=filename,
            **kwargs,
        )
        return response.data

    async def open_dm(self, user_id: str) -> str:
        """Open DM channel with user.

        Args:
            user_id: User ID

        Returns:
            Channel ID
        """
        response = await self.client.conversations_open(users=[user_id])
        return response["channel"]["id"]

    async def get_user_tz(self, user_id: str) -> str:
        """Get user timezone.

        Args:
            user_id: User ID

        Returns:
            Timezone string
        """
        response = await self.client.users_info(user=user_id)
        return response["user"].get("tz", "UTC")

    async def verify_signature(self, request_body: bytes, timestamp: str, signature: str) -> bool:
        """Verify Slack request signature.

        Args:
            request_body: Raw request body
            timestamp: X-Slack-Request-Timestamp header
            signature: X-Slack-Signature header

        Returns:
            True if signature is valid
        """
        if not self.signing_secret:
            return True

        sig_basestring = f"v0:{timestamp}:{request_body.decode()}"
        expected = (
            "v0="
            + hmac.new(
                self.signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )

        return hmac.compare_digest(expected, signature)

    async def aclose(self) -> None:
        """Close Slack client."""
        # AsyncWebClient doesn't need explicit closing
        pass
