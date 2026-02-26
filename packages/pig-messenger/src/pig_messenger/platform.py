"""Platform adapter base class."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from .message import Attachment, UniversalMessage


class MessagePlatform(ABC):
    """Abstract base class for message platforms."""

    def __init__(self, name: str):
        """Initialize platform adapter.

        Args:
            name: Platform name
        """
        self.name = name
        self.on_message: Callable | None = None

    @abstractmethod
    async def send_message(
        self,
        channel_id: str,
        text: str,
        thread_id: str | None = None,
        **kwargs,
    ) -> str:
        """Send a message to a channel.

        Args:
            channel_id: Channel ID
            text: Message text
            thread_id: Thread ID (if replying in thread)
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        pass

    @abstractmethod
    async def upload_file(
        self,
        channel_id: str,
        file_path: Path,
        caption: str | None = None,
        thread_id: str | None = None,
    ) -> str:
        """Upload a file to a channel.

        Args:
            channel_id: Channel ID
            file_path: Path to file
            caption: Optional caption
            thread_id: Thread ID (if in thread)

        Returns:
            Message ID
        """
        pass

    @abstractmethod
    async def get_history(self, channel_id: str, limit: int = 100) -> list[UniversalMessage]:
        """Get message history from a channel.

        Args:
            channel_id: Channel ID
            limit: Maximum messages to retrieve

        Returns:
            List of messages
        """
        pass

    @abstractmethod
    async def download_file(self, attachment: Attachment) -> bytes:
        """Download a file attachment.

        Args:
            attachment: Attachment info

        Returns:
            File bytes
        """
        pass

    @abstractmethod
    def start(self) -> None:
        """Start listening for messages.

        This should be a blocking call that runs the event loop.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop listening for messages."""
        pass

    async def send_card(
        self,
        channel_id: str,
        text: str,
        **kwargs,
    ) -> str:
        """Send an interactive card message.

        Platforms that support rich cards (e.g. Feishu) should override this.
        Default implementation falls back to ``send_message``.

        Args:
            channel_id: Channel ID
            text: Card body text (markdown)
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        return await self.send_message(channel_id, text, **kwargs)

    async def update_card(
        self,
        message_id: str,
        text: str,
        **kwargs,
    ) -> None:
        """Update an existing card message.

        Platforms that support in-place card updates should override this.
        Default implementation is a no-op.

        Args:
            message_id: ID of the card message to update
            text: New card body text (markdown)
            **kwargs: Platform-specific arguments
        """
        return  # no-op for platforms without card support

    def set_message_handler(self, handler: Callable) -> None:
        """Set the message handler callback.

        Args:
            handler: Function that receives UniversalMessage
        """
        self.on_message = handler

    async def _emit_message(self, message: UniversalMessage) -> None:
        """Emit a message to the handler.

        Args:
            message: Universal message
        """
        if self.on_message:
            await self.on_message(message)


class PlatformConfig(ABC):
    """Platform configuration base."""

    platform_name: str
    enabled: bool = True
