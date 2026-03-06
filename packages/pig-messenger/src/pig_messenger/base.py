"""Production-grade messenger base abstractions.

This module provides the foundation for building reliable multi-platform bots
with streaming support, including:
- MessengerType enum for platform identification
- MessengerUser, IncomingMessage, MessengerCapabilities dataclasses
- MessengerThread for bound context with 3-strategy streaming
- BaseMessengerAdapter ABC for platform adapters
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessengerType(str, Enum):
    """Supported messenger platforms."""

    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    WEBCHAT = "webchat"
    FEISHU = "feishu"


@dataclass
class MessengerUser:
    """Messenger user information."""

    id: str
    username: str
    email: str | None = None
    display_name: str | None = None


@dataclass
class IncomingMessage:
    """Incoming message from any platform."""

    # Identity
    message_id: str
    platform: MessengerType

    # Location
    channel_id: str

    # Content
    text: str

    # Optional fields with defaults
    thread_key: str | None = None  # Unique key for conversation threading
    reply_thread_id: str | None = None  # Platform-specific thread ID
    user: MessengerUser | None = None
    owner_user_id: str | None = None  # User who owns this conversation
    attachments: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float | None = None
    is_mention: bool = False
    is_dm: bool = False
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessengerCapabilities:
    """Platform capabilities and limits."""

    # Feature flags
    can_edit: bool = False
    can_delete: bool = False
    can_react: bool = False
    can_thread: bool = False
    can_upload_file: bool = False
    supports_blocks: bool = False
    supports_draft: bool = False  # Native draft streaming support

    # Limits
    max_message_length: int = 2000
    rate_limit_per_second: float = 1.0


def _split_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks at natural boundaries.

    Priority: \\n\\n > \\n > . > space
    Only breaks in second half of max_len to keep chunks readable.

    Args:
        text: Text to split
        max_len: Maximum length per chunk

    Returns:
        List of text chunks
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > max_len:
        # Find split point in second half
        split_start = max_len // 2
        chunk_text = remaining[:max_len]

        # Try to find natural boundary (in order of preference)
        split_pos = None
        for delimiter in ["\n\n", "\n", ". ", " "]:
            pos = chunk_text.rfind(delimiter, split_start)
            if pos != -1:
                split_pos = pos + len(delimiter)
                break

        if split_pos is None:
            # No natural boundary found, hard split
            split_pos = max_len

        chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:]

    if remaining:
        chunks.append(remaining)

    return chunks


class MessengerThread:
    """Bound context for adapter + coordinates with streaming support.

    Provides 3-strategy streaming:
    1. Draft streaming (supports_draft=True) - push native draft frames, commit final
    2. Edit streaming (can_edit=True) - post initial, edit at intervals, auto-split on overflow
    3. Batch fallback - collect all chunks, split, post sequentially
    """

    def __init__(
        self,
        adapter: "BaseMessengerAdapter",
        channel_id: str,
        thread_id: str | None = None,
        capabilities: MessengerCapabilities | None = None,
    ):
        """Initialize messenger thread.

        Args:
            adapter: Platform adapter
            channel_id: Channel ID
            thread_id: Thread ID (optional)
            capabilities: Platform capabilities
        """
        self.adapter = adapter
        self.channel_id = channel_id
        self.thread_id = thread_id
        self.capabilities = capabilities or MessengerCapabilities()

    async def post(self, text: str, **kwargs: Any) -> str:
        """Post a message.

        Args:
            text: Message text
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        return await self.adapter.send_message(
            self.channel_id, text, thread_id=self.thread_id, **kwargs
        )

    async def update(self, message_id: str, text: str, **kwargs: Any) -> None:
        """Update an existing message.

        Args:
            message_id: Message ID to update
            text: New text
            **kwargs: Platform-specific arguments
        """
        await self.adapter.update_message(self.channel_id, message_id, text, **kwargs)

    async def delete(self, message_id: str, **kwargs: Any) -> None:
        """Delete a message.

        Args:
            message_id: Message ID to delete
            **kwargs: Platform-specific arguments
        """
        await self.adapter.delete_message(self.channel_id, message_id, **kwargs)

    async def react(self, message_id: str, emoji: str, **kwargs: Any) -> None:
        """React to a message.

        Args:
            message_id: Message ID
            emoji: Emoji reaction
            **kwargs: Platform-specific arguments
        """
        await self.adapter.send_reaction(self.channel_id, message_id, emoji, **kwargs)

    async def typing(self, **kwargs: Any) -> None:
        """Send typing indicator.

        Args:
            **kwargs: Platform-specific arguments
        """
        await self.adapter.send_typing(self.channel_id, **kwargs)

    async def post_file(self, url: str, filename: str, **kwargs: Any) -> str:
        """Post a file from URL.

        Args:
            url: File URL
            filename: Filename
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        return await self.adapter.send_file(self.channel_id, url, filename, **kwargs)

    async def post_file_content(
        self, content: bytes, filename: str, content_type: str, **kwargs: Any
    ) -> str:
        """Post file content.

        Args:
            content: File bytes
            filename: Filename
            content_type: MIME type
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        return await self.adapter.send_file_content(
            self.channel_id, content, filename, content_type, **kwargs
        )

    async def post_blocks(self, blocks: list[dict], text_fallback: str = "", **kwargs: Any) -> str:
        """Post structured blocks.

        Args:
            blocks: Block structure (platform-specific)
            text_fallback: Fallback text
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        return await self.adapter.send_blocks(
            self.channel_id, blocks, text_fallback=text_fallback, thread_id=self.thread_id, **kwargs
        )

    async def stream(
        self,
        async_chunks: AsyncIterator[str],
        interval: float = 0.5,
        **kwargs: Any,
    ) -> list[str]:
        """Stream message chunks with auto-selected strategy.

        Strategies (auto-selected based on capabilities):
        1. Draft streaming (supports_draft=True) - zero edit history
        2. Edit streaming (can_edit=True) - throttled edits, auto-split on overflow
        3. Batch fallback - collect all, split, post sequentially

        Args:
            async_chunks: Async iterator of text chunks
            interval: Update interval in seconds (for edit strategy)
            **kwargs: Platform-specific arguments

        Returns:
            List of message IDs
        """
        if self.capabilities.supports_draft:
            return await self._stream_draft(async_chunks, **kwargs)
        elif self.capabilities.can_edit:
            return await self._stream_edit(async_chunks, interval, **kwargs)
        else:
            return await self._stream_batch(async_chunks, **kwargs)

    async def _stream_draft(self, async_chunks: AsyncIterator[str], **kwargs: Any) -> list[str]:
        """Draft streaming strategy - push native draft frames, commit final.

        Args:
            async_chunks: Async iterator of text chunks
            **kwargs: Platform-specific arguments

        Returns:
            List of message IDs (single final message)
        """
        accumulated = ""
        draft_id = None

        async for chunk in async_chunks:
            accumulated += chunk
            draft_id = await self.adapter.send_draft(
                self.channel_id, accumulated, draft_id=draft_id, **kwargs
            )

        # Commit final message
        if accumulated:
            message_id = await self.post(accumulated, **kwargs)
            return [message_id]
        return []

    async def _stream_edit(
        self, async_chunks: AsyncIterator[str], interval: float, **kwargs: Any
    ) -> list[str]:
        """Edit streaming strategy - post initial, edit at intervals, auto-split on overflow.

        Args:
            async_chunks: Async iterator of text chunks
            interval: Update interval in seconds
            **kwargs: Platform-specific arguments

        Returns:
            List of message IDs
        """
        accumulated = ""
        message_ids = []
        current_message_id = None
        last_update = 0.0

        async for chunk in async_chunks:
            accumulated += chunk
            now = asyncio.get_event_loop().time()

            # Check if we need to split due to overflow
            if len(accumulated) > self.capabilities.max_message_length:
                # Post current content and start new message
                max_len = self.capabilities.max_message_length
                if current_message_id:
                    await self.update(
                        current_message_id,
                        accumulated[:max_len],
                        **kwargs,
                    )
                else:
                    current_message_id = await self.post(accumulated[:max_len], **kwargs)
                message_ids.append(current_message_id)

                # Start new message with overflow
                accumulated = accumulated[max_len:]
                current_message_id = None
                last_update = now
                continue

            # Throttled update
            if now - last_update >= interval:
                if current_message_id:
                    await self.update(current_message_id, accumulated, **kwargs)
                else:
                    current_message_id = await self.post(accumulated, **kwargs)
                last_update = now

        # Final update
        if accumulated:
            if current_message_id:
                await self.update(current_message_id, accumulated, **kwargs)
            else:
                current_message_id = await self.post(accumulated, **kwargs)
            if current_message_id and current_message_id not in message_ids:
                message_ids.append(current_message_id)

        return message_ids

    async def _stream_batch(self, async_chunks: AsyncIterator[str], **kwargs: Any) -> list[str]:
        """Batch fallback strategy - collect all chunks, split, post sequentially.

        Args:
            async_chunks: Async iterator of text chunks
            **kwargs: Platform-specific arguments

        Returns:
            List of message IDs
        """
        accumulated = ""
        async for chunk in async_chunks:
            accumulated += chunk

        if not accumulated:
            return []

        # Split and post
        chunks = _split_text(accumulated, self.capabilities.max_message_length)
        message_ids = []
        for chunk in chunks:
            message_id = await self.post(chunk, **kwargs)
            message_ids.append(message_id)

        return message_ids


# Type alias for Gateway event handlers
GatewayEventHandler = Callable[[dict[str, Any]], None]


class BaseMessengerAdapter(ABC):
    """Abstract base class for messenger platform adapters."""

    def __init__(self, capabilities: MessengerCapabilities | None = None):
        """Initialize adapter.

        Args:
            capabilities: Platform capabilities
        """
        self.capabilities = capabilities or MessengerCapabilities()

    @abstractmethod
    async def send_message(
        self, channel_id: str, text: str, *, thread_id: str | None = None, **kwargs: Any
    ) -> str:
        """Send a message.

        Args:
            channel_id: Channel ID
            text: Message text
            thread_id: Thread ID (optional)
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        pass

    @abstractmethod
    async def update_message(
        self, channel_id: str, message_id: str, text: str, **kwargs: Any
    ) -> None:
        """Update an existing message.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            text: New text
            **kwargs: Platform-specific arguments
        """
        pass

    @abstractmethod
    def parse_event(self, raw_event: dict[str, Any]) -> IncomingMessage | None:
        """Parse platform event to IncomingMessage.

        Args:
            raw_event: Raw platform event

        Returns:
            IncomingMessage or None if not a message event
        """
        pass

    @abstractmethod
    def verify_signature(self, request_body: bytes, signature: str, **kwargs: Any) -> bool:
        """Verify webhook signature.

        Args:
            request_body: Raw request body
            signature: Signature from headers
            **kwargs: Platform-specific arguments (e.g., timestamp)

        Returns:
            True if signature is valid
        """
        pass

    # Virtual methods (can be overridden)

    async def delete_message(self, channel_id: str, message_id: str, **kwargs: Any) -> None:
        """Delete a message.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            **kwargs: Platform-specific arguments
        """
        logger.warning(f"{self.__class__.__name__} does not support delete_message")

    async def send_typing(self, channel_id: str, **kwargs: Any) -> None:  # noqa: B027
        """Send typing indicator.

        Args:
            channel_id: Channel ID
            **kwargs: Platform-specific arguments
        """
        pass  # Optional, no-op by default

    async def send_draft(
        self, channel_id: str, text: str, *, draft_id: str | None = None, **kwargs: Any
    ) -> str:
        """Send draft message (for draft streaming).

        Args:
            channel_id: Channel ID
            text: Draft text
            draft_id: Existing draft ID (for updates)
            **kwargs: Platform-specific arguments

        Returns:
            Draft ID
        """
        logger.warning(f"{self.__class__.__name__} does not support send_draft")
        return draft_id or "unsupported"

    async def send_reaction(
        self, channel_id: str, message_id: str, emoji: str, **kwargs: Any
    ) -> None:
        """React to a message.

        Args:
            channel_id: Channel ID
            message_id: Message ID
            emoji: Emoji reaction
            **kwargs: Platform-specific arguments
        """
        logger.warning(f"{self.__class__.__name__} does not support send_reaction")

    async def send_file(self, channel_id: str, url: str, filename: str, **kwargs: Any) -> str:
        """Send a file from URL.

        Args:
            channel_id: Channel ID
            url: File URL
            filename: Filename
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        logger.warning(f"{self.__class__.__name__} does not support send_file")
        return ""

    async def send_file_content(
        self,
        channel_id: str,
        content: bytes,
        filename: str,
        content_type: str,
        **kwargs: Any,
    ) -> str:
        """Send file content.

        Args:
            channel_id: Channel ID
            content: File bytes
            filename: Filename
            content_type: MIME type
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        logger.warning(f"{self.__class__.__name__} does not support send_file_content")
        return ""

    async def send_blocks(
        self,
        channel_id: str,
        blocks: list[dict],
        *,
        text_fallback: str = "",
        thread_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send structured blocks.

        Args:
            channel_id: Channel ID
            blocks: Block structure (platform-specific)
            text_fallback: Fallback text
            thread_id: Thread ID (optional)
            **kwargs: Platform-specific arguments

        Returns:
            Message ID
        """
        # Default: fall back to text
        return await self.send_message(channel_id, text_fallback, thread_id=thread_id, **kwargs)

    async def open_dm(self, user_id: str, **kwargs: Any) -> str:
        """Open a DM channel with a user.

        Args:
            user_id: User ID
            **kwargs: Platform-specific arguments

        Returns:
            Channel ID
        """
        logger.warning(f"{self.__class__.__name__} does not support open_dm")
        return ""

    async def get_user_tz(self, user_id: str, **kwargs: Any) -> str:
        """Get user's timezone.

        Args:
            user_id: User ID
            **kwargs: Platform-specific arguments

        Returns:
            Timezone string (e.g., "America/Los_Angeles")
        """
        return "UTC"  # Default

    async def aclose(self) -> None:  # noqa: B027
        """Close adapter resources."""
        pass  # Optional cleanup
