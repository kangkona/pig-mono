"""Memory abstraction for agent conversation history.

Provides protocol for custom memory implementations with a default in-memory provider.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class Message:
    """A single message in conversation history.

    Attributes:
        role: Message role (system, user, assistant, tool)
        content: Message content
        tool_calls: Optional tool calls (for assistant messages)
        tool_call_id: Optional tool call ID (for tool messages)
        name: Optional tool name (for tool messages)
    """

    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def model_dump(self) -> dict[str, Any]:
        """Convert to dict for LLM API."""
        result: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.name:
            result["name"] = self.name
        return result


class MemoryProvider(Protocol):
    """Protocol for memory storage implementations.

    Allows products to provide custom memory backends (Redis, PostgreSQL, etc.)
    while core package works with any implementation.
    """

    async def get_messages(self, session_id: str) -> list[Message]:
        """Retrieve conversation history for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            List of messages in chronological order
        """
        ...

    async def add_message(self, session_id: str, message: Message) -> None:
        """Add a message to conversation history.

        Args:
            session_id: Unique session identifier
            message: Message to add
        """
        ...

    async def clear_messages(self, session_id: str) -> None:
        """Clear all messages for a session.

        Args:
            session_id: Unique session identifier
        """
        ...

    async def get_metadata(self, session_id: str) -> dict[str, Any]:
        """Get session metadata.

        Args:
            session_id: Unique session identifier

        Returns:
            Session metadata dict
        """
        ...

    async def set_metadata(self, session_id: str, metadata: dict[str, Any]) -> None:
        """Set session metadata.

        Args:
            session_id: Unique session identifier
            metadata: Metadata to store
        """
        ...


class InMemoryProvider:
    """Default in-memory memory provider.

    Stores conversation history in memory. Suitable for development
    and single-process deployments. For production, use a persistent
    backend like Redis or PostgreSQL.
    """

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        self._messages: dict[str, list[Message]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    async def get_messages(self, session_id: str) -> list[Message]:
        """Retrieve conversation history for a session."""
        return self._messages.get(session_id, [])

    async def add_message(self, session_id: str, message: Message) -> None:
        """Add a message to conversation history."""
        if session_id not in self._messages:
            self._messages[session_id] = []
        self._messages[session_id].append(message)

    async def clear_messages(self, session_id: str) -> None:
        """Clear all messages for a session."""
        if session_id in self._messages:
            self._messages[session_id] = []

    async def get_metadata(self, session_id: str) -> dict[str, Any]:
        """Get session metadata."""
        return self._metadata.get(session_id, {})

    async def set_metadata(self, session_id: str, metadata: dict[str, Any]) -> None:
        """Set session metadata."""
        self._metadata[session_id] = metadata
