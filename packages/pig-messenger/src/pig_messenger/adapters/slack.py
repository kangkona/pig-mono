"""Slack platform adapter."""

from typing import Optional, List
from pathlib import Path
from datetime import datetime

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

from ..platform import MessagePlatform
from ..message import UniversalMessage, Attachment


class SlackAdapter(MessagePlatform):
    """Slack platform adapter using Socket Mode."""

    def __init__(
        self,
        app_token: str,
        bot_token: str,
        bot_user_id: Optional[str] = None,
    ):
        """Initialize Slack adapter.

        Args:
            app_token: Slack app-level token (xapp-...)
            bot_token: Slack bot token (xoxb-...)
            bot_user_id: Bot user ID (auto-detected if None)
        """
        super().__init__("slack")

        self.app = App(token=bot_token)
        self.client = WebClient(token=bot_token)
        self.app_token = app_token
        self.bot_user_id = bot_user_id
        self.handler = None

        # Auto-detect bot user ID
        if not self.bot_user_id:
            auth = self.client.auth_test()
            self.bot_user_id = auth["user_id"]

        # Register event handlers
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup Slack event handlers."""
        import asyncio

        def _run_async(coro):
            """Run async coroutine from sync context."""
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, coro).result()
            else:
                return asyncio.run(coro)

        @self.app.event("app_mention")
        def handle_mention(event, say):
            """Handle @mention."""
            _run_async(self._handle_slack_message(event, is_mention=True))

        @self.app.event("message")
        def handle_message(event, say):
            """Handle direct messages and channel messages."""
            # Skip bot's own messages
            if event.get("user") == self.bot_user_id:
                return

            # Check if it's a DM or if bot is mentioned
            channel_type = event.get("channel_type")
            is_dm = channel_type == "im"
            text = event.get("text", "")
            is_mention = f"<@{self.bot_user_id}>" in text

            if is_dm or is_mention:
                _run_async(self._handle_slack_message(event, is_mention=is_mention, is_dm=is_dm))

    async def _handle_slack_message(
        self, event: dict, is_mention: bool = False, is_dm: bool = False
    ):
        """Convert Slack event to UniversalMessage and emit.

        Args:
            event: Slack event
            is_mention: Is bot mentioned
            is_dm: Is direct message
        """
        # Get user info
        user_id = event.get("user", "")
        try:
            user_info = self.client.users_info(user=user_id)
            username = user_info["user"]["real_name"] or user_info["user"]["name"]
            user_email = user_info["user"].get("profile", {}).get("email")
        except Exception:
            username = user_id
            user_email = None

        # Clean mention from text
        text = event.get("text", "")
        if is_mention:
            text = text.replace(f"<@{self.bot_user_id}>", "").strip()

        # Handle attachments
        attachments = []
        for file in event.get("files", []):
            attachments.append(
                Attachment(
                    id=file["id"],
                    filename=file["name"],
                    content_type=file.get("mimetype", ""),
                    size=file.get("size", 0),
                    url=file.get("url_private"),
                )
            )

        # Create universal message
        message = UniversalMessage(
            id=event["ts"],
            platform="slack",
            channel_id=event["channel"],
            user_id=user_id,
            username=username,
            user_email=user_email,
            text=text,
            attachments=attachments,
            timestamp=datetime.fromtimestamp(float(event["ts"])),
            is_mention=is_mention,
            is_dm=is_dm,
            is_thread="thread_ts" in event,
            thread_id=event.get("thread_ts"),
            raw_data=event,
        )

        # Emit to handler
        await self._emit_message(message)

    async def send_message(
        self,
        channel_id: str,
        text: str,
        thread_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Send message to Slack channel.

        Args:
            channel_id: Channel ID
            text: Message text
            thread_id: Thread timestamp (if replying in thread)
            **kwargs: Additional Slack arguments

        Returns:
            Message timestamp
        """
        result = self.client.chat_postMessage(
            channel=channel_id,
            text=text,
            thread_ts=thread_id,
            **kwargs,
        )

        return result["ts"]

    async def upload_file(
        self,
        channel_id: str,
        file_path: Path,
        caption: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Upload file to Slack.

        Args:
            channel_id: Channel ID
            file_path: File path
            caption: Optional caption
            thread_id: Thread timestamp

        Returns:
            File ID
        """
        result = self.client.files_upload_v2(
            channel=channel_id,
            file=str(file_path),
            initial_comment=caption,
            thread_ts=thread_id,
        )

        return result["file"]["id"]

    async def get_history(
        self, channel_id: str, limit: int = 100
    ) -> List[UniversalMessage]:
        """Get Slack channel history.

        Args:
            channel_id: Channel ID
            limit: Message limit

        Returns:
            List of universal messages
        """
        result = self.client.conversations_history(channel=channel_id, limit=limit)

        messages = []
        for msg in result["messages"]:
            # Skip bot messages
            if msg.get("user") == self.bot_user_id:
                continue

            # Convert to universal format
            # (simplified - full implementation would be more complete)
            messages.append(
                UniversalMessage(
                    id=msg["ts"],
                    platform="slack",
                    channel_id=channel_id,
                    user_id=msg.get("user", ""),
                    username="",  # Would need to fetch
                    text=msg.get("text", ""),
                    timestamp=datetime.fromtimestamp(float(msg["ts"])),
                    raw_data=msg,
                )
            )

        return messages

    async def download_file(self, attachment: Attachment) -> bytes:
        """Download file from Slack.

        Args:
            attachment: Attachment info

        Returns:
            File bytes
        """
        import httpx

        headers = {"Authorization": f"Bearer {self.client.token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(attachment.url, headers=headers)
            response.raise_for_status()
            return response.content

    def start(self) -> None:
        """Start Slack bot (blocking)."""
        self.handler = SocketModeHandler(self.app, self.app_token)
        self.handler.start()

    def stop(self) -> None:
        """Stop Slack bot."""
        if self.handler:
            self.handler.close()
