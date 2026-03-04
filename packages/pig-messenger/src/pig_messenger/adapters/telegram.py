"""Telegram messenger adapter."""

import hashlib
import hmac
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


class TelegramMessengerAdapter(BaseMessengerAdapter):
    """Telegram messenger adapter with draft streaming support."""

    def __init__(self, bot_token: str, base_url: str | None = None):
        """Initialize Telegram adapter.

        Args:
            bot_token: Telegram bot token
            base_url: Optional custom API base URL
        """
        if httpx is None:
            raise ImportError("httpx is required for Telegram adapter")

        self.bot_token = bot_token
        self.base_url = base_url or "https://api.telegram.org"
        self.api_url = f"{self.base_url}/bot{bot_token}"

        self.client = httpx.AsyncClient(timeout=30.0)

        self.capabilities = MessengerCapabilities(
            can_edit=True,
            can_delete=True,
            can_react=False,
            can_thread=False,
            can_upload_file=True,
            supports_blocks=False,
            supports_draft=True,
            max_message_length=4096,
        )

    async def parse_event(self, raw_event: dict[str, Any]) -> IncomingMessage | None:
        """Parse Telegram Update to IncomingMessage.

        Args:
            raw_event: Telegram Update JSON

        Returns:
            IncomingMessage or None if not a message
        """
        # Extract message from update
        message = raw_event.get("message") or raw_event.get("edited_message")
        if not message:
            return None

        # Skip non-text messages
        text = message.get("text")
        if not text:
            return None

        # Extract user info
        from_user = message.get("from", {})
        user = MessengerUser(
            id=str(from_user.get("id", "")),
            username=from_user.get("username", ""),
            display_name=from_user.get("first_name", ""),
        )

        # Extract chat info
        chat = message.get("chat", {})
        channel_id = str(chat.get("id", ""))

        return IncomingMessage(
            message_id=str(message.get("message_id", "")),
            platform=MessengerType.TELEGRAM,
            channel_id=channel_id,
            text=text,
            user=user,
            timestamp=message.get("date", 0),
            is_dm=chat.get("type") == "private",
        )

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Send message to Telegram.

        Args:
            channel_id: Chat ID
            text: Message text
            thread_id: Optional thread ID (not used in Telegram)
            **kwargs: Additional parameters

        Returns:
            API response with message_id
        """
        payload = {
            "chat_id": channel_id,
            "text": text,
        }
        payload.update(kwargs)

        response = await self.client.post(
            f"{self.api_url}/sendMessage",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        return {
            "message_id": str(result["result"]["message_id"]),
        }

    async def update_message(
        self, channel_id: str, message_id: str, text: str, **kwargs
    ) -> dict[str, Any]:
        """Update message in Telegram.

        Args:
            channel_id: Chat ID
            message_id: Message ID to edit
            text: New message text
            **kwargs: Additional parameters

        Returns:
            API response
        """
        payload = {
            "chat_id": channel_id,
            "message_id": message_id,
            "text": text,
        }
        payload.update(kwargs)

        response = await self.client.post(
            f"{self.api_url}/editMessageText",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete message in Telegram.

        Args:
            channel_id: Chat ID
            message_id: Message ID to delete

        Returns:
            True if successful
        """
        payload = {
            "chat_id": channel_id,
            "message_id": message_id,
        }

        response = await self.client.post(
            f"{self.api_url}/deleteMessage",
            json=payload,
        )
        response.raise_for_status()
        return True

    async def send_typing(self, channel_id: str) -> None:
        """Send typing indicator.

        Args:
            channel_id: Chat ID
        """
        payload = {
            "chat_id": channel_id,
            "action": "typing",
        }

        await self.client.post(
            f"{self.api_url}/sendChatAction",
            json=payload,
        )

    async def send_draft(
        self, channel_id: str, text: str, *, draft_id: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Send draft message (Bot API 9.5+).

        Args:
            channel_id: Chat ID
            text: Draft text
            draft_id: Optional draft ID to update
            **kwargs: Additional parameters

        Returns:
            API response with draft_id
        """
        # Note: This is a placeholder for Bot API 9.5+ draft feature
        # For now, use regular sendMessage
        return await self.send_message(channel_id, text, **kwargs)

    async def send_file(self, channel_id: str, url: str, filename: str, **kwargs) -> dict[str, Any]:
        """Send file from URL.

        Args:
            channel_id: Chat ID
            url: File URL
            filename: File name
            **kwargs: Additional parameters

        Returns:
            API response with message_id
        """
        payload = {
            "chat_id": channel_id,
            "document": url,
        }
        payload.update(kwargs)

        response = await self.client.post(
            f"{self.api_url}/sendDocument",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        return {
            "message_id": str(result["result"]["message_id"]),
        }

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
            channel_id: Chat ID
            content: File content
            filename: File name
            content_type: MIME type
            **kwargs: Additional parameters

        Returns:
            API response with message_id
        """
        files = {
            "document": (filename, content, content_type),
        }
        data = {
            "chat_id": channel_id,
        }
        data.update(kwargs)

        response = await self.client.post(
            f"{self.api_url}/sendDocument",
            data=data,
            files=files,
        )
        response.raise_for_status()
        result = response.json()

        return {
            "message_id": str(result["result"]["message_id"]),
        }

    async def verify_signature(self, request_body: bytes, signature: str) -> bool:
        """Verify Telegram webhook signature.

        Args:
            request_body: Raw request body
            signature: Signature from X-Telegram-Bot-Api-Secret-Token header

        Returns:
            True if signature is valid
        """
        # Telegram uses secret token validation
        # The signature should match the secret token set in webhook
        expected = hashlib.sha256(self.bot_token.encode()).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def aclose(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
