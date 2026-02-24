"""Feishu (飞书/Lark) platform adapter."""

from typing import Optional, List
from pathlib import Path
from datetime import datetime
import json

import httpx

from ..platform import MessagePlatform
from ..message import UniversalMessage, Attachment


class FeishuAdapter(MessagePlatform):
    """Feishu (Lark) platform adapter."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        verification_token: Optional[str] = None,
        encrypt_key: Optional[str] = None,
    ):
        """Initialize Feishu adapter.

        Args:
            app_id: Feishu app ID
            app_secret: Feishu app secret
            verification_token: Event verification token
            encrypt_key: Event encryption key
        """
        super().__init__("feishu")

        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key

        self.api_base = "https://open.feishu.cn/open-apis"
        self.client = httpx.AsyncClient()
        self.tenant_access_token = None

    async def _get_tenant_access_token(self) -> str:
        """Get tenant access token.

        Returns:
            Tenant access token
        """
        if self.tenant_access_token:
            return self.tenant_access_token

        url = f"{self.api_base}/auth/v3/tenant_access_token/internal"

        payload = {"app_id": self.app_id, "app_secret": self.app_secret}

        response = await self.client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        self.tenant_access_token = data["tenant_access_token"]

        return self.tenant_access_token

    async def send_message(
        self,
        channel_id: str,
        text: str,
        thread_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Send message to Feishu chat.

        Args:
            channel_id: Chat ID (chat_id or open_id)
            text: Message text
            thread_id: Root message ID (if replying)
            **kwargs: Additional parameters

        Returns:
            Message ID
        """
        token = await self._get_tenant_access_token()

        url = f"{self.api_base}/im/v1/messages"

        headers = {"Authorization": f"Bearer {token}"}

        # Determine receive_id_type
        if channel_id.startswith("oc_"):
            receive_id_type = "chat_id"
        elif channel_id.startswith("ou_"):
            receive_id_type = "open_id"
        else:
            receive_id_type = "chat_id"

        params = {"receive_id_type": receive_id_type}

        payload = {
            "receive_id": channel_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }

        if thread_id:
            payload["root_id"] = thread_id

        response = await self.client.post(url, headers=headers, params=params, json=payload)
        response.raise_for_status()

        data = response.json()
        return data["data"]["message_id"]

    async def upload_file(
        self,
        channel_id: str,
        file_path: Path,
        caption: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Upload file to Feishu.

        Args:
            channel_id: Chat ID
            file_path: File path
            caption: Caption (sent as separate message)
            thread_id: Root message ID

        Returns:
            Message ID
        """
        token = await self._get_tenant_access_token()

        # Upload file first
        upload_url = f"{self.api_base}/im/v1/files"
        headers = {"Authorization": f"Bearer {token}"}

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            data = {"file_type": "stream"}

            response = await self.client.post(
                upload_url, headers=headers, files=files, data=data
            )
            response.raise_for_status()

        file_key = response.json()["data"]["file_key"]

        # Send file message
        msg_url = f"{self.api_base}/im/v1/messages"

        receive_id_type = "chat_id" if channel_id.startswith("oc_") else "open_id"
        params = {"receive_id_type": receive_id_type}

        payload = {
            "receive_id": channel_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}),
        }

        response = await self.client.post(msg_url, headers=headers, params=params, json=payload)
        response.raise_for_status()

        message_id = response.json()["data"]["message_id"]

        # Send caption if provided
        if caption:
            await self.send_message(channel_id, caption, thread_id=message_id)

        return message_id

    async def get_history(
        self, channel_id: str, limit: int = 100
    ) -> List[UniversalMessage]:
        """Get Feishu chat history.

        Args:
            channel_id: Chat ID
            limit: Message limit

        Returns:
            List of messages
        """
        # Simplified - full implementation would paginate
        return []

    async def download_file(self, attachment: Attachment) -> bytes:
        """Download file from Feishu.

        Args:
            attachment: Attachment with file_key as ID

        Returns:
            File bytes
        """
        token = await self._get_tenant_access_token()

        url = f"{self.api_base}/im/v1/messages/{attachment.id}/resources/{attachment.id}"
        headers = {"Authorization": f"Bearer {token}"}

        response = await self.client.get(url, headers=headers, params={"type": "file"})
        response.raise_for_status()

        return response.content

    def handle_event(self, payload: dict) -> None:
        """Handle Feishu event callback.

        Args:
            payload: Event payload

        Call this from your event callback server.
        """
        import asyncio

        event = payload.get("event", {})

        # Handle message event
        if event.get("type") == "message":
            msg = self._convert_feishu_message(event)
            asyncio.create_task(self._emit_message(msg))

    def _convert_feishu_message(self, event: dict) -> UniversalMessage:
        """Convert Feishu event to UniversalMessage."""

        message = event.get("message", {})

        return UniversalMessage(
            id=message.get("message_id", ""),
            platform="feishu",
            channel_id=message.get("chat_id", ""),
            user_id=event.get("sender", {}).get("sender_id", {}).get("open_id", ""),
            username=event.get("sender", {}).get("sender_id", {}).get("user_id", ""),
            text=json.loads(message.get("content", "{}")).get("text", ""),
            timestamp=datetime.fromtimestamp(int(event.get("create_time", 0)) / 1000),
            is_mention=message.get("mentions") is not None,
            raw_data=event,
        )

    def start(self) -> None:
        """Start Feishu adapter.

        Requires external event callback server.
        """
        print("Feishu adapter ready")
        print("Configure event callback in Feishu Admin")

    def stop(self) -> None:
        """Stop Feishu adapter."""
        pass
