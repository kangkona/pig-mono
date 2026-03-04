"""Tool audit logging for tracking tool usage and debugging.

Provides audit trail for tool executions with filtering and export capabilities.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolAuditEntry:
    """Single audit entry for a tool execution.

    Attributes:
        tool_name: Name of the tool
        timestamp: Unix timestamp when tool was called
        user_id: User who triggered the tool
        args: Tool arguments
        success: Whether execution succeeded
        error: Error message if failed
        duration: Execution duration in seconds
        result_size: Size of result in characters
        metadata: Additional metadata
    """

    tool_name: str
    timestamp: float
    user_id: str
    args: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None
    duration: float = 0.0
    result_size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "args": self.args,
            "success": self.success,
            "error": self.error,
            "duration": self.duration,
            "result_size": self.result_size,
            "metadata": self.metadata,
        }


class ToolAuditLog:
    """Audit log for tool executions.

    Maintains a history of tool calls with filtering and export capabilities.
    """

    def __init__(self, max_entries: int = 10000):
        """Initialize audit log.

        Args:
            max_entries: Maximum number of entries to keep (oldest removed first)
        """
        self.max_entries = max_entries
        self._entries: list[ToolAuditEntry] = []
        self._seq: int = 0

    def log(
        self,
        tool_name: str,
        user_id: str,
        args: dict[str, Any] | None = None,
        success: bool = True,
        error: str | None = None,
        duration: float = 0.0,
        result_size: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a tool execution.

        Args:
            tool_name: Name of the tool
            user_id: User who triggered the tool
            args: Tool arguments
            success: Whether execution succeeded
            error: Error message if failed
            duration: Execution duration in seconds
            result_size: Size of result in characters
            metadata: Additional metadata
        """
        self._seq += 1
        ts = time.time()

        entry = ToolAuditEntry(
            tool_name=tool_name,
            timestamp=ts,
            user_id=user_id,
            args=args or {},
            success=success,
            error=error,
            duration=duration,
            result_size=result_size,
            metadata=metadata or {},
        )

        self._entries.append(entry)

        # Trim if exceeds max
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]

    def get_entries(
        self,
        tool_name: str | None = None,
        user_id: str | None = None,
        success: bool | None = None,
        limit: int | None = None,
    ) -> list[ToolAuditEntry]:
        """Get audit entries with optional filtering.

        Args:
            tool_name: Filter by tool name
            user_id: Filter by user ID
            success: Filter by success status
            limit: Maximum number of entries to return

        Returns:
            List of matching audit entries (most recent first)
        """
        entries = self._entries

        # Apply filters
        if tool_name is not None:
            entries = [e for e in entries if e.tool_name == tool_name]

        if user_id is not None:
            entries = [e for e in entries if e.user_id == user_id]

        if success is not None:
            entries = [e for e in entries if e.success == success]

        # Reverse to get most recent first (entries are appended in order)
        entries = list(reversed(entries))

        # Apply limit
        if limit is not None:
            entries = entries[:limit]

        return entries

    def get_failed_entries(self, limit: int | None = None) -> list[ToolAuditEntry]:
        """Get failed tool executions.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of failed audit entries (most recent first)
        """
        return self.get_entries(success=False, limit=limit)

    def export_json(self, filepath: str) -> None:
        """Export audit log to JSON file.

        Args:
            filepath: Path to output file
        """
        data = [entry.to_dict() for entry in self._entries]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def clear(self) -> None:
        """Clear all audit entries."""
        self._entries.clear()

    def __len__(self) -> int:
        """Get number of entries in log."""
        return len(self._entries)
