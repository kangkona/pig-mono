"""Feishu adapter compatibility wrapper for new messenger architecture."""

import logging
from typing import Any

from pig_messenger.adapters.feishu import FeishuAdapter
from pig_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerCapabilities,
    MessengerType,
    MessengerUser,
)

logger = logging.getLogger(__name__)


class FeishuMessengerAdapter(BaseMessengerAdapter):
    """Feishu messenger adapter wrapping legacy FeishuAdapter."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        verification_token: str | None = None,
        encrypt_key: str | None = None,
        use_ws: bool = True,
    ):
        """Initialize Feishu adapter.

        Args:
            app_id: Feishu app ID
            app_secret: Feishu app secret
            verification_token: Event verification token
            encrypt_key: Event encryption key
            use_ws: Use SDK WebSocket long connection
        """
        self.adapter = FeishuAdapter(
            app_id=app_id,
            app_secret=app_secret,
            verification_token=verification_token,
            encrypt_key=encrypt_key,
            use_ws=use_ws,
        )

        self.capabilities = MessengerCapabilities(
            can_edit=True,
            can_delete=False,
            can_react=False,
            can_thread=True,
            can_upload_file=True,
            supports_blocks=True,
            supports_draft=False,
            max_message_length=10000,
        )

    async def parse_event(self, raw_event: dict[str, Any]) -> IncomingMessage | None:
        """Parse Feishu event to IncomingMessage.

        Args:
            raw_event: Feishu event payload

        Returns:
            IncomingMessage or None
        """
        # Let legacy adapter handle event
        await self.adapter.handle_event(raw_event)

        # Extract message from event
        event = raw_event.get("event", {})
        if event.get("type") != "message":
            return None

        message = event.get("message", {})
        sender = event.get("sender", {})

        user = MessengerUser(
            id=sender.get("sender_id", {}).get("open_id", ""),
            username=sender.get("sender_id", {}).get("user_id", ""),
            display_name="",
        )

        return IncomingMessage(
            message_id=message.get("message_id", ""),
            platform=MessengerType.FEISHU,
            channel_id=message.get("chat_id", ""),
            text=message.get("content", ""),
            user=user,
            timestamp=0,
            is_dm=message.get("chat_type") == "p2p",
        )

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Send message to Feishu.

        Args:
            channel_id: Chat ID
            text: Message text
            thread_id: Optional thread ID
            **kwargs: Additional parameters

        Returns:
            API response with message_id
        """
        message_id = await self.adapter.send_message(
            channel_id=channel_id,
            text=text,
            thread_id=thread_id,
            **kwargs,
        )

        return {
            "message_id": message_id,
        }

    async def update_message(
        self, channel_id: str, message_id: str, text: str, **kwargs
    ) -> dict[str, Any]:
        """Update message in Feishu.

        Args:
            channel_id: Chat ID
            message_id: Message ID
            text: New text
            **kwargs: Additional parameters

        Returns:
            Empty dict
        """
        # Legacy adapter doesn't have update_message
        raise NotImplementedError("Message editing not implemented in legacy adapter")

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete message (not supported).

        Args:
            channel_id: Chat ID
            message_id: Message ID

        Returns:
            False
        """
        raise NotImplementedError("Feishu does not support message deletion")

    async def verify_signature(self, request_body: bytes, signature: str) -> bool:
        """Verify Feishu webhook signature.

        Args:
            request_body: Raw request body
            signature: Signature header

        Returns:
            True if valid
        """
        # Legacy adapter handles verification internally
        return True

    async def aclose(self) -> None:
        """Close adapter."""
        self.adapter.stop()
