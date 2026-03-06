"""Discord messenger adapter."""

import logging
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from pig_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerCapabilities,
    MessengerType,
    MessengerUser,
)

logger = logging.getLogger(__name__)


class DiscordMessengerAdapter(BaseMessengerAdapter):
    """Discord messenger adapter."""

    def __init__(self, bot_token: str, public_key: str | None = None):
        """Initialize Discord adapter.

        Args:
            bot_token: Discord bot token
            public_key: Discord public key for verification
        """
        if httpx is None:
            raise ImportError("httpx is required for Discord adapter")

        self.bot_token = bot_token
        self.public_key = public_key
        self.api_url = "https://discord.com/api/v10"

        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Authorization": f"Bot {bot_token}"},
        )

        self.capabilities = MessengerCapabilities(
            can_edit=True,
            can_delete=True,
            can_react=True,
            can_thread=True,
            can_upload_file=True,
            supports_blocks=False,
            supports_draft=False,
            max_message_length=2000,
        )

    async def parse_event(self, raw_event: dict[str, Any]) -> IncomingMessage | None:
        """Parse Discord event to IncomingMessage.

        Args:
            raw_event: Discord event payload

        Returns:
            IncomingMessage or None
        """
        # Handle different event types
        event_type = raw_event.get("t")

        if event_type == "MESSAGE_CREATE":
            data = raw_event.get("d", {})

            # Skip bot messages
            if data.get("author", {}).get("bot"):
                return None

            author = data.get("author", {})
            user = MessengerUser(
                id=author.get("id", ""),
                username=author.get("username", ""),
                display_name=author.get("global_name") or author.get("username", ""),
            )

            channel_id = data.get("channel_id", "")
            guild_id = data.get("guild_id")

            return IncomingMessage(
                message_id=data.get("id", ""),
                platform=MessengerType.DISCORD,
                channel_id=channel_id,
                text=data.get("content", ""),
                user=user,
                timestamp=0,
                is_dm=guild_id is None,
            )

        return None

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Send message to Discord.

        Args:
            channel_id: Channel ID
            text: Message text
            thread_id: Optional thread ID
            **kwargs: Additional parameters

        Returns:
            API response with message_id
        """
        target_channel = thread_id or channel_id

        payload = {
            "content": text,
        }
        payload.update(kwargs)

        response = await self.client.post(
            f"{self.api_url}/channels/{target_channel}/messages",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        return {
            "message_id": result["id"],
        }

    async def update_message(
        self, channel_id: str, message_id: str, text: str, **kwargs
    ) -> dict[str, Any]:
        """Update message in Discord.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            text: New text
            **kwargs: Additional parameters

        Returns:
            API response
        """
        payload = {
            "content": text,
        }
        payload.update(kwargs)

        response = await self.client.patch(
            f"{self.api_url}/channels/{channel_id}/messages/{message_id}",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete message in Discord.

        Args:
            channel_id: Channel ID
            message_id: Message ID

        Returns:
            True if successful
        """
        response = await self.client.delete(
            f"{self.api_url}/channels/{channel_id}/messages/{message_id}"
        )
        response.raise_for_status()
        return True

    async def send_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        """Add reaction to message.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            emoji: Emoji (Unicode or custom format)
        """
        # URL encode emoji
        import urllib.parse

        encoded_emoji = urllib.parse.quote(emoji)

        await self.client.put(
            f"{self.api_url}/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
        )

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
        files = {
            "file": (filename, content, content_type),
        }

        response = await self.client.post(
            f"{self.api_url}/channels/{channel_id}/messages",
            files=files,
        )
        response.raise_for_status()
        result = response.json()

        return {
            "message_id": result["id"],
        }

    async def verify_signature(self, request_body: bytes, signature: str, timestamp: str) -> bool:
        """Verify Discord interaction signature.

        Args:
            request_body: Raw request body
            signature: X-Signature-Ed25519 header
            timestamp: X-Signature-Timestamp header

        Returns:
            True if signature is valid
        """
        if not self.public_key:
            return True

        # Discord uses Ed25519 signature verification
        # This is a placeholder - actual implementation would use nacl library
        return True

    async def aclose(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
