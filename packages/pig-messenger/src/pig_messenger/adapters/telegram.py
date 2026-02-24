"""Telegram platform adapter."""

from typing import Optional, List
from pathlib import Path
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from ..platform import MessagePlatform
from ..message import UniversalMessage, Attachment


class TelegramAdapter(MessagePlatform):
    """Telegram platform adapter."""

    def __init__(self, bot_token: str):
        """Initialize Telegram adapter.

        Args:
            bot_token: Telegram bot token
        """
        super().__init__("telegram")

        self.bot_token = bot_token
        self.app = Application.builder().token(bot_token).build()
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup Telegram handlers."""

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle incoming message."""
            if not update.message:
                return

            message = update.message

            # Create universal message
            attachments = []

            # Handle photo
            if message.photo:
                photo = message.photo[-1]  # Largest size
                attachments.append(
                    Attachment(
                        id=photo.file_id,
                        filename="photo.jpg",
                        content_type="image/jpeg",
                        size=photo.file_size or 0,
                        url=None,  # Need to get via get_file
                    )
                )

            # Handle document
            if message.document:
                doc = message.document
                attachments.append(
                    Attachment(
                        id=doc.file_id,
                        filename=doc.file_name or "document",
                        content_type=doc.mime_type or "",
                        size=doc.file_size or 0,
                    )
                )

            msg = UniversalMessage(
                id=str(message.message_id),
                platform="telegram",
                channel_id=str(message.chat.id),
                channel_name=message.chat.title if message.chat.title else None,
                user_id=str(message.from_user.id),
                username=message.from_user.full_name,
                user_email=None,
                text=message.text or message.caption or "",
                attachments=attachments,
                timestamp=message.date,
                is_mention=False,  # Telegram doesn't have @mentions in same way
                is_dm=message.chat.type == "private",
                raw_data={"update": update},
            )

            await self._emit_message(msg)

        # Register handlers
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        self.app.add_handler(MessageHandler(filters.PHOTO, handle_message))
        self.app.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    async def send_message(
        self,
        channel_id: str,
        text: str,
        thread_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Send message to Telegram chat."""
        message = await self.app.bot.send_message(
            chat_id=int(channel_id),
            text=text,
            reply_to_message_id=int(thread_id) if thread_id else None,
            **kwargs,
        )

        return str(message.message_id)

    async def upload_file(
        self,
        channel_id: str,
        file_path: Path,
        caption: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Upload file to Telegram."""
        message = await self.app.bot.send_document(
            chat_id=int(channel_id),
            document=open(file_path, "rb"),
            caption=caption,
            reply_to_message_id=int(thread_id) if thread_id else None,
        )

        return str(message.message_id)

    async def get_history(
        self, channel_id: str, limit: int = 100
    ) -> List[UniversalMessage]:
        """Get Telegram chat history."""
        # Telegram doesn't provide easy history API
        # Would need to implement using updates
        return []

    async def download_file(self, attachment: Attachment) -> bytes:
        """Download file from Telegram."""
        file = await self.app.bot.get_file(attachment.id)
        return await file.download_as_bytearray()

    def start(self) -> None:
        """Start Telegram bot (blocking)."""
        self.app.run_polling()

    def stop(self) -> None:
        """Stop Telegram bot."""
        self.app.stop()
