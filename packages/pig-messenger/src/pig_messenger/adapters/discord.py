"""Discord platform adapter."""

from typing import Optional, List
from pathlib import Path
from datetime import datetime

import discord

from ..platform import MessagePlatform
from ..message import UniversalMessage, Attachment


class DiscordAdapter(MessagePlatform):
    """Discord platform adapter."""

    def __init__(self, bot_token: str):
        """Initialize Discord adapter.

        Args:
            bot_token: Discord bot token
        """
        super().__init__("discord")

        self.bot_token = bot_token
        self.client = discord.Client(intents=discord.Intents.all())
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup Discord event handlers."""

        @self.client.event
        async def on_ready():
            print(f"✓ Discord bot ready: {self.client.user}")

        @self.client.event
        async def on_message(message: discord.Message):
            # Skip bot's own messages
            if message.author == self.client.user:
                return

            # Check if bot is mentioned or DM
            is_mention = self.client.user in message.mentions
            is_dm = isinstance(message.channel, discord.DMChannel)

            if not (is_mention or is_dm):
                return

            # Convert to universal message
            await self._handle_discord_message(message, is_mention, is_dm)

    async def _handle_discord_message(
        self, message: discord.Message, is_mention: bool, is_dm: bool
    ):
        """Convert Discord message to UniversalMessage."""

        # Handle attachments
        attachments = []
        for attach in message.attachments:
            attachments.append(
                Attachment(
                    id=str(attach.id),
                    filename=attach.filename,
                    content_type=attach.content_type or "",
                    size=attach.size,
                    url=attach.url,
                )
            )

        # Create universal message
        text = message.content
        if is_mention:
            # Remove mention
            text = text.replace(f"<@{self.client.user.id}>", "").strip()

        msg = UniversalMessage(
            id=str(message.id),
            platform="discord",
            channel_id=str(message.channel.id),
            channel_name=getattr(message.channel, "name", None),
            user_id=str(message.author.id),
            username=message.author.display_name,
            text=text,
            attachments=attachments,
            timestamp=message.created_at,
            is_mention=is_mention,
            is_dm=is_dm,
            raw_data={"message": message},
        )

        await self._emit_message(msg)

    async def send_message(
        self,
        channel_id: str,
        text: str,
        thread_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Send message to Discord channel."""
        channel = self.client.get_channel(int(channel_id))

        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        # Send message
        msg = await channel.send(text, **kwargs)

        return str(msg.id)

    async def upload_file(
        self,
        channel_id: str,
        file_path: Path,
        caption: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Upload file to Discord."""
        channel = self.client.get_channel(int(channel_id))

        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        msg = await channel.send(content=caption, file=discord.File(str(file_path)))

        return str(msg.id)

    async def get_history(
        self, channel_id: str, limit: int = 100
    ) -> List[UniversalMessage]:
        """Get Discord channel history."""
        channel = self.client.get_channel(int(channel_id))

        if not channel:
            return []

        messages = []
        async for msg in channel.history(limit=limit):
            if msg.author == self.client.user:
                continue

            messages.append(
                UniversalMessage(
                    id=str(msg.id),
                    platform="discord",
                    channel_id=str(channel_id),
                    user_id=str(msg.author.id),
                    username=msg.author.display_name,
                    text=msg.content,
                    timestamp=msg.created_at,
                    raw_data={"message": msg},
                )
            )

        return messages

    async def download_file(self, attachment: Attachment) -> bytes:
        """Download file from Discord."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(attachment.url)
            response.raise_for_status()
            return response.content

    def start(self) -> None:
        """Start Discord bot (blocking)."""
        self.client.run(self.bot_token)

    def stop(self) -> None:
        """Stop Discord bot."""
        asyncio.create_task(self.client.close())
