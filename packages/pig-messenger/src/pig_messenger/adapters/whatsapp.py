"""WhatsApp messenger adapter via Twilio."""

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


class WhatsAppMessengerAdapter(BaseMessengerAdapter):
    """WhatsApp messenger adapter using Twilio API."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
    ):
        """Initialize WhatsApp adapter.

        Args:
            account_sid: Twilio account SID
            auth_token: Twilio auth token
            from_number: WhatsApp from number (format: whatsapp:+1234567890)
        """
        if httpx is None:
            raise ImportError("httpx is required for WhatsApp adapter")

        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.api_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"

        self.client = httpx.AsyncClient(
            timeout=30.0,
            auth=(account_sid, auth_token),
        )

        self.capabilities = MessengerCapabilities(
            can_edit=False,
            can_delete=False,
            can_react=False,
            can_thread=False,
            can_upload_file=True,
            supports_blocks=False,
            supports_draft=False,
            max_message_length=1600,
        )

    async def parse_event(self, raw_event: dict[str, Any]) -> IncomingMessage | None:
        """Parse Twilio webhook to IncomingMessage.

        Args:
            raw_event: Twilio webhook form data

        Returns:
            IncomingMessage or None
        """
        # Twilio sends form data, not JSON
        message_sid = raw_event.get("MessageSid")
        from_number = raw_event.get("From", "")
        body = raw_event.get("Body", "")

        if not message_sid or not body:
            return None

        # Extract phone number from whatsapp:+1234567890 format
        user_id = from_number.replace("whatsapp:", "")

        user = MessengerUser(
            id=user_id,
            username=user_id,
            display_name=raw_event.get("ProfileName", user_id),
        )

        return IncomingMessage(
            message_id=message_sid,
            platform=MessengerType.WHATSAPP,
            channel_id=user_id,
            text=body,
            user=user,
            timestamp=0,
            is_dm=True,
        )

    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Send message to WhatsApp.

        Args:
            channel_id: Phone number
            text: Message text
            thread_id: Not used
            **kwargs: Additional parameters

        Returns:
            API response with message_id
        """
        # Ensure channel_id has whatsapp: prefix
        to_number = channel_id if channel_id.startswith("whatsapp:") else f"whatsapp:{channel_id}"

        payload = {
            "From": self.from_number,
            "To": to_number,
            "Body": text,
        }
        payload.update(kwargs)

        response = await self.client.post(
            f"{self.api_url}/Messages.json",
            data=payload,
        )
        response.raise_for_status()
        result = response.json()

        return {
            "message_id": result["sid"],
        }

    async def update_message(
        self, channel_id: str, message_id: str, text: str, **kwargs
    ) -> dict[str, Any]:
        """Update message (not supported by WhatsApp).

        Args:
            channel_id: Phone number
            message_id: Message ID
            text: New text
            **kwargs: Additional parameters

        Returns:
            Empty dict

        Raises:
            NotImplementedError: WhatsApp doesn't support message editing
        """
        raise NotImplementedError("WhatsApp does not support message editing")

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete message (not supported by WhatsApp).

        Args:
            channel_id: Phone number
            message_id: Message ID

        Returns:
            False

        Raises:
            NotImplementedError: WhatsApp doesn't support message deletion
        """
        raise NotImplementedError("WhatsApp does not support message deletion")

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
            channel_id: Phone number
            content: File content
            filename: File name
            content_type: MIME type
            **kwargs: Additional parameters

        Returns:
            API response
        """
        # WhatsApp via Twilio requires media URL, not direct upload
        raise NotImplementedError("Direct file upload not supported, use media URL")

    async def verify_signature(self, url: str, params: dict[str, str], signature: str) -> bool:
        """Verify Twilio request signature.

        Args:
            url: Full request URL
            params: Request parameters
            signature: X-Twilio-Signature header

        Returns:
            True if signature is valid
        """
        # Construct data string
        data_string = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))

        # Compute HMAC-SHA1
        expected = hmac.new(
            self.auth_token.encode(),
            data_string.encode(),
            hashlib.sha1,
        ).digest()

        import base64

        expected_b64 = base64.b64encode(expected).decode()

        return hmac.compare_digest(expected_b64, signature)

    async def aclose(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
