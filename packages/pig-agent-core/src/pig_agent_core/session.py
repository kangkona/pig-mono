"""Session management with tree structure and JSONL storage."""

import json
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field

from .tools import ToolResult


def serialize_compaction_tool_result(result: ToolResult | Any, max_chars: int = 4000) -> str:
    """Serialize tool output for compaction without letting huge outputs dominate."""
    if isinstance(result, ToolResult):
        return cast(str, result.serialize(max_chars=max_chars))

    return cast(str, ToolResult(ok=True, data=result).serialize(max_chars=max_chars))


class SessionEntry(BaseModel):
    """A single entry in the session tree."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionTree:
    """Tree-based session storage."""

    def __init__(self) -> None:
        """Initialize session tree."""
        self.entries: dict[str, SessionEntry] = {}
        self.current_id: str | None = None
        self.root_id: str | None = None

    def add_entry(
        self, role: str, content: str, parent_id: str | None = None, **metadata: Any
    ) -> SessionEntry:
        """Add an entry to the tree.

        Args:
            role: Message role (user, assistant, system, tool)
            content: Message content
            parent_id: Parent entry ID (uses current if None)
            **metadata: Additional metadata

        Returns:
            Created entry
        """
        if parent_id is None:
            parent_id = self.current_id

        entry = SessionEntry(parent_id=parent_id, role=role, content=content, metadata=metadata)

        self.entries[entry.id] = entry
        self.current_id = entry.id

        if self.root_id is None:
            self.root_id = entry.id

        return entry

    def get_path_to_entry(self, entry_id: str) -> list[SessionEntry]:
        """Get path from root to entry.

        Args:
            entry_id: Entry ID

        Returns:
            List of entries from root to entry
        """
        path: list[SessionEntry] = []
        current = self.entries.get(entry_id)

        while current:
            path.insert(0, current)
            current = self.entries.get(current.parent_id) if current.parent_id else None

        return path

    def get_children(self, entry_id: str) -> list[SessionEntry]:
        """Get children of an entry.

        Args:
            entry_id: Entry ID

        Returns:
            List of child entries
        """
        return [e for e in self.entries.values() if e.parent_id == entry_id]

    def get_branches(self, entry_id: str) -> list[list[SessionEntry]]:
        """Get all branches from an entry.

        Args:
            entry_id: Entry ID

        Returns:
            List of branches (each branch is a list of entries)
        """
        children = self.get_children(entry_id)
        if not children:
            return [[]]

        branches = []
        for child in children:
            child_branches = self.get_branches(child.id)
            for branch in child_branches:
                branches.append([child] + branch)

        return branches

    def switch_to(self, entry_id: str) -> None:
        """Switch current context to an entry.

        Args:
            entry_id: Entry ID to switch to
        """
        if entry_id not in self.entries:
            raise ValueError(f"Entry {entry_id} not found")

        self.current_id = entry_id

    def get_current_path(self) -> list[SessionEntry]:
        """Get current conversation path.

        Returns:
            List of entries from root to current
        """
        if self.current_id is None:
            return []

        return self.get_path_to_entry(self.current_id)

    def to_jsonl(self) -> str:
        """Export tree to JSONL format.

        Returns:
            JSONL string
        """
        lines = []
        for entry in self.entries.values():
            lines.append(entry.model_dump_json())
        return "\n".join(lines)

    @classmethod
    def from_jsonl(cls, jsonl: str) -> "SessionTree":
        """Load tree from JSONL format.

        Args:
            jsonl: JSONL string

        Returns:
            Loaded session tree
        """
        return cls.from_jsonl_iter(jsonl.splitlines())

    @classmethod
    def from_jsonl_iter(cls, lines: Iterable[str]) -> "SessionTree":
        """Load tree from an iterable of JSONL lines.

        This avoids materializing large session files in memory before parsing.
        """
        tree = cls()

        last_entry: SessionEntry | None = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            entry = SessionEntry.model_validate_json(line)
            tree.entries[entry.id] = entry
            last_entry = entry

            if entry.parent_id is None:
                tree.root_id = entry.id

        if last_entry is not None:
            tree.current_id = last_entry.id

        return tree


class Session:
    """Enhanced session with tree structure and compaction."""

    def __init__(
        self,
        name: str | None = None,
        workspace: str | None = None,
        auto_save: bool = True,
    ) -> None:
        """Initialize session.

        Args:
            name: Session name
            workspace: Workspace directory
            auto_save: Auto-save after changes
        """
        self.id = str(uuid.uuid4())
        self.name = name or f"session-{self.id[:8]}"
        self.workspace = Path(workspace) if workspace else Path.cwd()
        self.auto_save = auto_save

        self.tree = SessionTree()
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        self.metadata: dict[str, Any] = {
            "tokens_used": 0,
            "cost": 0.0,
            "model": None,
        }

    def add_message(
        self, role: str, content: str, parent_id: str | None = None, **metadata: Any
    ) -> SessionEntry:
        """Add a message to the session.

        Args:
            role: Message role
            content: Message content
            parent_id: Parent entry ID
            **metadata: Additional metadata

        Returns:
            Created entry
        """
        entry = self.tree.add_entry(role, content, parent_id, **metadata)
        self.updated_at = datetime.utcnow()

        if self.auto_save:
            self.save()

        return entry

    def get_current_conversation(self) -> list[SessionEntry]:
        """Get current conversation path.

        Returns:
            List of entries
        """
        return self.tree.get_current_path()

    def branch_to(self, entry_id: str) -> None:
        """Branch to a different point in history.

        Args:
            entry_id: Entry ID to branch to
        """
        self.tree.switch_to(entry_id)
        self.updated_at = datetime.utcnow()

        if self.auto_save:
            self.save()

    def compact(
        self,
        instructions: str | None = None,
        *,
        max_tool_chars: int = 1000,
    ) -> list[SessionEntry]:
        """Compact old messages.

        Args:
            instructions: Custom compaction instructions

        Returns:
            Compacted messages
        """
        # Get current path
        path = self.get_current_conversation()

        if len(path) <= 10:  # Don't compact if too short
            return path

        # Keep recent messages
        recent = path[-5:]

        # Compact older messages without embedding full tool payloads.
        old = path[:-5]

        tool_summaries = []
        for entry in old:
            if entry.role == "tool":
                tool_name = entry.metadata.get("name", "tool")
                tool_summaries.append(
                    f"- {tool_name}: "
                    + serialize_compaction_tool_result(entry.content, max_chars=max_tool_chars)
                )

        summary_content = f"[Compacted {len(old)} messages]\n"
        if instructions:
            summary_content += f"Instructions: {instructions}\n"
        summary_content += f"Topics covered: {len({e.role for e in old})} roles"
        if tool_summaries:
            summary_content += "\nTool outputs:\n" + "\n".join(tool_summaries[:10])

        summary_entry = SessionEntry(
            role="system",
            content=summary_content,
            metadata={
                "compacted": True,
                "original_count": len(old),
            },
        )
        self.tree.entries[summary_entry.id] = summary_entry
        self.tree.root_id = summary_entry.id

        if recent:
            recent[0].parent_id = summary_entry.id
            self.tree.current_id = recent[-1].id
        else:
            self.tree.current_id = summary_entry.id

        self.updated_at = datetime.utcnow()

        if self.auto_save:
            self.save()

        # Return compacted path
        return self.get_current_conversation()

    def fork(self, entry_id: str, new_name: str | None = None) -> "Session":
        """Fork session from a point.

        Args:
            entry_id: Entry ID to fork from
            new_name: Name for the new session

        Returns:
            New session
        """
        # Create new session
        new_session = Session(
            name=new_name or f"{self.name}-fork",
            workspace=str(self.workspace),
            auto_save=self.auto_save,
        )

        # Copy path to entry
        path = self.tree.get_path_to_entry(entry_id)
        for entry in path:
            new_session.add_message(role=entry.role, content=entry.content, **entry.metadata)

        return new_session

    def save(self, path: Path | None = None) -> Path:
        """Save session to JSONL file.

        Args:
            path: File path (auto-generated if None)

        Returns:
            Saved file path
        """
        if path is None:
            # Auto-generate path
            session_dir = self.workspace / ".sessions"
            session_dir.mkdir(exist_ok=True)
            path = session_dir / f"{self.name}-{self.id[:8]}.jsonl"

        metadata = dict(self.metadata)
        metadata["entries"] = len(self.tree.entries)

        # Save metadata and tree
        data = {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": metadata,
        }

        tree_jsonl = self.tree.to_jsonl()

        # Write header + tree tail without duplicating the tree in metadata.
        with open(path, "w") as f:
            f.write(json.dumps(data) + "\n")
            f.write(tree_jsonl)

        return path

    @classmethod
    def load(cls, path: Path) -> "Session":
        """Load session from JSONL file.

        Args:
            path: File path

        Returns:
            Loaded session
        """
        with open(path) as f:
            # Read header
            header = json.loads(f.readline())

            tree = SessionTree.from_jsonl_iter(f)

        # Create session
        session = cls(name=header["name"], workspace=str(path.parent.parent), auto_save=False)

        session.id = header["id"]
        session.created_at = datetime.fromisoformat(header["created_at"])
        session.updated_at = datetime.fromisoformat(header["updated_at"])
        session.metadata = header["metadata"]
        session.tree = tree

        return session

    def get_info(self) -> dict[str, Any]:
        """Get session info.

        Returns:
            Session information
        """
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "entries": len(self.tree.entries),
            "current_path_length": len(self.get_current_conversation()),
            "branches": len(self.tree.get_branches(self.tree.root_id)) if self.tree.root_id else 0,
            "metadata": self.metadata,
        }
