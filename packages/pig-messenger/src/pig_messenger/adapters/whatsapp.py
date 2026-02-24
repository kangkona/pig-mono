"""WhatsApp platform adapter (via WhatsApp Business API)."""

from typing import Optional, List
from pathlib import Path
from datetime import datetime

import httpx

from ..platform import MessagePlatform
from ..message import UniversalMessage, Attachment


class WhatsAppAdapter(MessagePlatform):
    """WhatsApp Business API adapter."""

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        verify_token: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        """Initialize WhatsApp adapter.

        Args:
            phone_number_id: WhatsApp Business phone number ID
            access_token: WhatsApp Business access token
            verify_token: Webhook verification token
            webhook_url: Webhook URL for receiving messages
        """
        super().__init__("whatsapp")

        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.verify_token = verify_token
        self.webhook_url = webhook_url

        self.api_base = "https://graph.facebook.com/v18.0"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {access_token}"}
        )

    async def send_message(
        self,
        channel_id: str,
        text: str,
        thread_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Send text message via WhatsApp.

        Args:
            channel_id: Phone number (with country code, e.g., "1234567890")
            text: Message text
            thread_id: Not applicable for WhatsApp
            **kwargs: Additional parameters

        Returns:
            Message ID
        """
        url = f"{self.api_base}/{self.phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": channel_id,
            "type": "text",
            "text": {"body": text},
        }

        response = await self.client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        return data["messages"][0]["id"]

    async def send_template(
        self, channel_id: str, template_name: str, **params
    ) -> str:
        """Send template message.

        Args:
            channel_id: Phone number
            template_name: Template name
            **params: Template parameters

        Returns:
            Message ID
        """
        url = f"{self.api_base}/{self.phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": channel_id,
            "type": "template",
            "template": {"name": template_name, "language": {"code": "en"}},
        }

        response = await self.client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        return data["messages"][0]["id"]

    async def upload_file(
        self,
        channel_id: str,
        file_path: Path,
        caption: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Send file via WhatsApp.

        Args:
            channel_id: Phone number
            file_path: File path
            caption: Optional caption
            thread_id: Not applicable

        Returns:
            Message ID
        """
        # First upload media to WhatsApp
        media_url = f"{self.api_base}/{self.phone_number_id}/media"

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/octet-stream")}
            response = await self.client.post(media_url, files=files)
            response.raise_for_status()

        media_id = response.json()["id"]

        # Determine media type
        suffix = file_path.suffix.lower()
        if suffix in [".jpg", ".jpeg", ".png"]:
            media_type = "image"
        elif suffix in [".mp4", ".3gp"]:
            media_type = "video"
        elif suffix in [".mp3", ".ogg"]:
            media_type = "audio"
        elif suffix == ".pdf":
            media_type = "document"
        else:
            media_type = "document"

        # Send media message
        url = f"{self.api_base}/{self.phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": channel_id,
            "type": media_type,
            media_type: {"id": media_id, "caption": caption or ""},
        }

        response = await self.client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        return data["messages"][0]["id"]

    async def get_history(
        self, channel_id: str, limit: int = 100
    ) -> List[UniversalMessage]:
        """Get WhatsApp message history.

        Note: WhatsApp Business API doesn't provide history retrieval.
        Would need to implement via webhook storage.

        Args:
            channel_id: Phone number
            limit: Message limit

        Returns:
            Empty list (not supported by API)
        """
        return []

    async def download_file(self, attachment: Attachment) -> bytes:
        """Download media from WhatsApp.

        Args:
            attachment: Attachment info

        Returns:
            File bytes
        """
        # Get media URL
        media_url = f"{self.api_base}/{attachment.id}"
        response = await self.client.get(media_url)
        response.raise_for_status()

        download_url = response.json()["url"]

        # Download file
        file_response = await self.client.get(download_url)
        file_response.raise_for_status()

        return file_response.content

    def handle_webhook(self, payload: dict) -> None:
        """Handle incoming webhook from WhatsApp.

        Args:
            payload: Webhook payload

        This should be called by your webhook server.
        """
        import asyncio

        # Parse webhook
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue

                value = change.get("value", {})

                for message in value.get("messages", []):
                    # Convert to UniversalMessage
                    msg = self._convert_webhook_message(message, value)

                    # Emit asynchronously
                    asyncio.create_task(self._emit_message(msg))

    def _convert_webhook_message(
        self, message: dict, value: dict
    ) -> UniversalMessage:
        """Convert WhatsApp webhook message to UniversalMessage.

        Args:
            message: Message object from webhook
            value: Value object from webhook

        Returns:
            Universal message
        """
        # Get contact info
        contacts = {c["wa_id"]: c for c in value.get("contacts", [])}
        contact = contacts.get(message["from"], {})

        profile = contact.get("profile", {})
        username = profile.get("name", message["from"])

        # Get text
        text = ""
        if message["type"] == "text":
            text = message["text"]["body"]
        elif message["type"] == "interactive":
            # Button or list response
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive["button_reply"]["title"]
            elif interactive.get("type") == "list_reply":
                text = interactive["list_reply"]["title"]

        # Handle attachments
        attachments = []
        for media_type in ["image", "video", "audio", "document"]:
            if media_type in message:
                media = message[media_type]
                attachments.append(
                    Attachment(
                        id=media["id"],
                        filename=media.get("filename", f"{media_type}.{media.get('mime_type', '').split('/')[-1]}"),
                        content_type=media.get("mime_type", ""),
                        size=0,  # Not provided in webhook
                    )
                )

        return UniversalMessage(
            id=message["id"],
            platform="whatsapp",
            channel_id=message["from"],  # Phone number
            user_id=message["from"],
            username=username,
            text=text,
            attachments=attachments,
            timestamp=datetime.fromtimestamp(int(message["timestamp"])),
            is_dm=True,  # WhatsApp is always 1:1 or groups
            raw_data=message,
        )

    def start(self) -> None:
        """Start WhatsApp adapter.

        Note: Requires external webhook server.
        Use Flask/FastAPI to receive webhooks and call handle_webhook().
        """
        print(f"WhatsApp adapter ready")
        print(f"Configure webhook: {self.webhook_url}")
        print("Call adapter.handle_webhook(payload) from your webhook server")

    def stop(self) -> None:
        """Stop WhatsApp adapter."""
        pass
