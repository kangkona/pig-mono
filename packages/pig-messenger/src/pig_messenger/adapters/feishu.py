"""Feishu (飞书/Lark) platform adapter."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from ..message import Attachment, UniversalMessage
from ..platform import MessagePlatform

if TYPE_CHECKING:
    import lark_oapi as lark


class FeishuAdapter(MessagePlatform):
    """Feishu (Lark) platform adapter.

    Supports two modes:
    - ``use_ws=True`` (default): SDK long-connection via ``lark_oapi``.
      ``start()`` blocks like SlackAdapter.
    - ``use_ws=False``: Webhook mode – requires an external callback server
      that calls ``handle_event()``.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        verification_token: str | None = None,
        encrypt_key: str | None = None,
        *,
        use_ws: bool = True,
    ):
        """Initialize Feishu adapter.

        Args:
            app_id: Feishu app ID
            app_secret: Feishu app secret
            verification_token: Event verification token
            encrypt_key: Event encryption key
            use_ws: Use SDK WebSocket long connection (default True)
        """
        super().__init__("feishu")

        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
        self.use_ws = use_ws

        self._ws_client: lark.ws.Client | None = None
        self._lark_client: lark.Client | None = None

        if use_ws:
            self._init_sdk()
        else:
            self.api_base = "https://open.feishu.cn/open-apis"
            self.client = httpx.AsyncClient()
            self.tenant_access_token = None

    # ------------------------------------------------------------------
    # SDK (WebSocket) helpers
    # ------------------------------------------------------------------

    def _init_sdk(self) -> None:
        """Build lark_oapi objects for WebSocket mode."""
        import lark_oapi as lark

        event_handler = (
            lark.EventDispatcherHandler.builder(
                self.verification_token or "",
                self.encrypt_key or "",
            )
            .register_p2_im_message_receive_v1(self._on_sdk_message)
            .build()
        )

        self._lark_client = (
            lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).build()
        )

        self._ws_client = lark.ws.Client(
            app_id=self.app_id,
            app_secret=self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

    def _on_sdk_message(self, data) -> None:
        """Handle incoming message from SDK long connection.

        ``data`` is a ``P2ImMessageReceiveV1`` instance from lark_oapi.

        This runs synchronously inside the SDK's asyncio event loop,
        so we dispatch the async handler via ``create_task`` with error
        handling to prevent silent failures.
        """
        import asyncio

        try:
            event = data.event
            message = event.message
            sender = event.sender

            content = json.loads(message.content) if message.content else {}
            text = re.sub(r"@_user_\d+", "", content.get("text", "")).strip()

            msg = UniversalMessage(
                id=message.message_id or "",
                platform="feishu",
                channel_id=message.chat_id or "",
                user_id=sender.sender_id.open_id or "",
                username=sender.sender_id.user_id or "",
                text=text,
                timestamp=datetime.fromtimestamp(int(message.create_time or 0) / 1000),
                is_mention=bool(message.mentions),
                raw_data={},
            )

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._safe_emit(msg))
            except RuntimeError:
                asyncio.run(self._emit_message(msg))
        except Exception as e:
            print(f"[FeishuAdapter] _on_sdk_message error: {e}")
            import traceback

            traceback.print_exc()

    async def _safe_emit(self, msg: UniversalMessage) -> None:
        """Emit message with error handling for fire-and-forget tasks."""
        try:
            await self._emit_message(msg)
        except Exception as e:
            print(f"[FeishuAdapter] message handler error: {e}")
            import traceback

            traceback.print_exc()

    # ------------------------------------------------------------------
    # Webhook helpers
    # ------------------------------------------------------------------

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
        thread_id: str | None = None,
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
        if self.use_ws:
            return self._send_message_sdk(channel_id, text, thread_id)
        return await self._send_message_http(channel_id, text, thread_id)

    def _send_message_sdk(
        self,
        channel_id: str,
        text: str,
        thread_id: str | None = None,
    ) -> str:
        """Send message via lark_oapi SDK client."""
        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        receive_id_type = "open_id" if channel_id.startswith("ou_") else "chat_id"

        body = (
            CreateMessageRequestBody.builder()
            .receive_id(channel_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        )

        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(body)
            .build()
        )

        response = self._lark_client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(f"Feishu SDK send failed: code={response.code}, msg={response.msg}")
        return response.data.message_id

    async def _send_message_http(
        self,
        channel_id: str,
        text: str,
        thread_id: str | None = None,
    ) -> str:
        """Send message via HTTP (webhook mode)."""
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

    # ------------------------------------------------------------------
    # Card messages (streaming support)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_card_content(text: str) -> dict:
        """Build a Feishu interactive card JSON payload.

        Args:
            text: Markdown text for the card body

        Returns:
            Card content dict suitable for ``msg_type="interactive"``
        """
        return {
            "elements": [{"tag": "markdown", "content": text}],
        }

    async def send_card(
        self,
        channel_id: str,
        text: str,
        **kwargs,
    ) -> str:
        """Send an interactive card message.

        Args:
            channel_id: Chat ID (chat_id or open_id)
            text: Markdown text for the card body
            **kwargs: Additional parameters

        Returns:
            Message ID
        """
        if self.use_ws:
            return self._send_card_sdk(channel_id, text)
        return await self._send_card_http(channel_id, text)

    def _send_card_sdk(self, channel_id: str, text: str) -> str:
        """Send interactive card via lark_oapi SDK."""
        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        receive_id_type = "open_id" if channel_id.startswith("ou_") else "chat_id"
        card_content = self._build_card_content(text)

        body = (
            CreateMessageRequestBody.builder()
            .receive_id(channel_id)
            .msg_type("interactive")
            .content(json.dumps(card_content))
            .build()
        )

        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(body)
            .build()
        )

        response = self._lark_client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(
                f"Feishu SDK send_card failed: code={response.code}, msg={response.msg}"
            )
        return response.data.message_id

    async def _send_card_http(self, channel_id: str, text: str) -> str:
        """Send interactive card via HTTP."""
        token = await self._get_tenant_access_token()

        url = f"{self.api_base}/im/v1/messages"
        headers = {"Authorization": f"Bearer {token}"}

        receive_id_type = "chat_id" if channel_id.startswith("oc_") else "open_id"
        params = {"receive_id_type": receive_id_type}

        card_content = self._build_card_content(text)
        payload = {
            "receive_id": channel_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content),
        }

        response = await self.client.post(url, headers=headers, params=params, json=payload)
        response.raise_for_status()

        return response.json()["data"]["message_id"]

    async def update_card(
        self,
        message_id: str,
        text: str,
        **kwargs,
    ) -> None:
        """Update an existing interactive card message.

        Args:
            message_id: ID of the card message to update
            text: New markdown text for the card body
            **kwargs: Additional parameters
        """
        if self.use_ws:
            self._update_card_sdk(message_id, text)
        else:
            await self._update_card_http(message_id, text)

    def _update_card_sdk(self, message_id: str, text: str) -> None:
        """Update card via lark_oapi SDK (PATCH)."""
        from lark_oapi.api.im.v1 import (
            PatchMessageRequest,
            PatchMessageRequestBody,
        )

        card_content = self._build_card_content(text)

        body = PatchMessageRequestBody.builder().content(json.dumps(card_content)).build()

        request = PatchMessageRequest.builder().message_id(message_id).request_body(body).build()

        response = self._lark_client.im.v1.message.patch(request)
        if not response.success():
            raise RuntimeError(
                f"Feishu SDK update_card failed: code={response.code}, msg={response.msg}"
            )

    async def _update_card_http(self, message_id: str, text: str) -> None:
        """Update card via HTTP (PATCH)."""
        token = await self._get_tenant_access_token()

        url = f"{self.api_base}/im/v1/messages/{message_id}"
        headers = {"Authorization": f"Bearer {token}"}

        card_content = self._build_card_content(text)
        payload = {"content": json.dumps(card_content)}

        response = await self.client.patch(url, headers=headers, json=payload)
        response.raise_for_status()

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    async def upload_file(
        self,
        channel_id: str,
        file_path: Path,
        caption: str | None = None,
        thread_id: str | None = None,
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

            response = await self.client.post(upload_url, headers=headers, files=files, data=data)
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

    async def get_history(self, channel_id: str, limit: int = 100) -> list[UniversalMessage]:
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
            text=re.sub(
                r"@_user_\d+", "", json.loads(message.get("content", "{}")).get("text", "")
            ).strip(),
            timestamp=datetime.fromtimestamp(int(event.get("create_time", 0)) / 1000),
            is_mention=message.get("mentions") is not None,
            raw_data=event,
        )

    def start(self) -> None:
        """Start Feishu adapter.

        In WebSocket mode, this blocks (like SlackAdapter).
        In webhook mode, prints setup instructions.
        """
        if self.use_ws:
            self._ws_client.start()
        else:
            print("Feishu adapter ready")
            print("Configure event callback in Feishu Admin")

    def stop(self) -> None:
        """Stop Feishu adapter."""
        if self._ws_client is not None:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self._ws_client._disconnect())
            except Exception:
                pass
