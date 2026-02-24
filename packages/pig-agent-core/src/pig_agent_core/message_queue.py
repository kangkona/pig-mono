"""Message queue for handling messages while agent is working."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class MessageType(str, Enum):
    """Type of queued message."""

    STEERING = "steering"  # Interrupt after current tool
    FOLLOWUP = "followup"  # Wait until agent completely done


class QueuedMessage(BaseModel):
    """A message in the queue."""

    content: str
    type: MessageType = MessageType.FOLLOWUP
    timestamp: Optional[str] = None


class MessageQueue:
    """Queue for messages submitted while agent is working."""

    def __init__(self):
        """Initialize message queue."""
        self.queue: list[QueuedMessage] = []
        self.is_processing = False
        self.steering_mode = "one-at-a-time"  # or "all"
        self.followup_mode = "one-at-a-time"  # or "all"

    def add_steering(self, message: str) -> None:
        """Add a steering message (interrupt after current tool).

        Args:
            message: Message content
        """
        self.queue.append(
            QueuedMessage(content=message, type=MessageType.STEERING)
        )

    def add_followup(self, message: str) -> None:
        """Add a follow-up message (wait until fully done).

        Args:
            message: Message content
        """
        self.queue.append(
            QueuedMessage(content=message, type=MessageType.FOLLOWUP)
        )

    def get_steering_messages(self) -> list[QueuedMessage]:
        """Get all steering messages and remove from queue.

        Returns:
            List of steering messages
        """
        steering = [m for m in self.queue if m.type == MessageType.STEERING]

        # Remove from queue
        self.queue = [m for m in self.queue if m.type != MessageType.STEERING]

        # Apply mode
        if self.steering_mode == "one-at-a-time" and steering:
            return [steering[0]]
        return steering

    def get_followup_messages(self) -> list[QueuedMessage]:
        """Get all follow-up messages and remove from queue.

        Returns:
            List of follow-up messages
        """
        followup = [m for m in self.queue if m.type == MessageType.FOLLOWUP]

        # Remove from queue
        self.queue = [m for m in self.queue if m.type != MessageType.FOLLOWUP]

        # Apply mode
        if self.followup_mode == "one-at-a-time" and followup:
            return [followup[0]]
        return followup

    def peek(self) -> Optional[QueuedMessage]:
        """Peek at next message without removing.

        Returns:
            Next message or None
        """
        return self.queue[0] if self.queue else None

    def clear(self) -> list[QueuedMessage]:
        """Clear all queued messages.

        Returns:
            List of cleared messages
        """
        messages = self.queue.copy()
        self.queue.clear()
        return messages

    def has_steering(self) -> bool:
        """Check if there are steering messages.

        Returns:
            True if steering messages exist
        """
        return any(m.type == MessageType.STEERING for m in self.queue)

    def has_followup(self) -> bool:
        """Check if there are follow-up messages.

        Returns:
            True if follow-up messages exist
        """
        return any(m.type == MessageType.FOLLOWUP for m in self.queue)

    def __len__(self) -> int:
        """Get queue length."""
        return len(self.queue)

    def __bool__(self) -> bool:
        """Check if queue has messages."""
        return len(self.queue) > 0

    def get_status(self) -> str:
        """Get queue status string.

        Returns:
            Status description
        """
        if not self.queue:
            return "Queue empty"

        steering = sum(1 for m in self.queue if m.type == MessageType.STEERING)
        followup = sum(1 for m in self.queue if m.type == MessageType.FOLLOWUP)

        parts = []
        if steering:
            parts.append(f"{steering} steering")
        if followup:
            parts.append(f"{followup} follow-up")

        return f"Queued: {', '.join(parts)}"
