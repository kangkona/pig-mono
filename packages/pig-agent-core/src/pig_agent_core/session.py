"""Session management with tree structure and JSONL storage."""

import json
import re
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field

from .compaction import CompactionCheckpoint, CompactionReason
from .session_manager import resolve_session_dir
from .tools import ToolResult
from .usage import UsageLedger

_UUID_LIKE_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


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

    def available_tool_names_at(
        self,
        entry_id: str | None = None,
        *,
        initial_tool_names: Iterable[str] = (),
    ) -> set[str]:
        """Reconstruct tools available at one transcript point.

        Tool activation is branch-local because only anchors on the selected
        root-to-entry path are considered.
        """
        target_id = entry_id if entry_id is not None else self.current_id
        names = set(initial_tool_names)
        if target_id is None:
            return names
        if target_id not in self.entries:
            raise ValueError(f"Entry {target_id} not found")
        for entry in self.get_path_to_entry(target_id):
            added = entry.metadata.get("added_tool_names", ())
            if isinstance(added, list | tuple | set):
                names.update(name for name in added if isinstance(name, str) and name)
        return names

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
        ordered_entries: list[SessionEntry] = []
        parent_ids: set[str] = set()
        for line in lines:
            line = line.strip()
            if not line:
                continue

            entry = SessionEntry.model_validate_json(line)
            tree.entries[entry.id] = entry
            ordered_entries.append(entry)
            if entry.parent_id is not None:
                parent_ids.add(entry.parent_id)

        if ordered_entries:
            leaf_candidates = [
                (index, entry)
                for index, entry in enumerate(ordered_entries)
                if entry.id not in parent_ids
            ]
            _, current_entry = max(
                leaf_candidates or list(enumerate(ordered_entries)),
                key=lambda item: (item[1].timestamp, item[0]),
            )
            tree.current_id = current_entry.id

            root_entry = current_entry
            visited: set[str] = set()
            while (
                root_entry.parent_id is not None
                and root_entry.parent_id in tree.entries
                and root_entry.parent_id not in visited
            ):
                visited.add(root_entry.id)
                root_entry = tree.entries[root_entry.parent_id]

            tree.root_id = root_entry.id

        return tree


class Session:
    """Enhanced session with tree structure and compaction."""

    def __init__(
        self,
        name: str | None = None,
        workspace: str | None = None,
        auto_save: bool = True,
        session_dir: str | Path | None = None,
    ) -> None:
        """Initialize session.

        Args:
            name: Session name
            workspace: Workspace directory
            auto_save: Auto-save after changes
            session_dir: Explicit session directory override
        """
        self.id = str(uuid.uuid4())
        self.name = name or f"session-{self.id[:8]}"
        self.workspace = Path(workspace) if workspace else Path.cwd()
        self.auto_save = auto_save
        self.session_dir = Path(session_dir).expanduser().resolve() if session_dir else None
        self._save_path: Path | None = None

        self.tree = SessionTree()
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        self.metadata: dict[str, Any] = {
            "tokens_used": 0,
            "cost": 0.0,
            "model": None,
        }
        self.usage_ledger = UsageLedger()
        self.metadata["usage"] = self.usage_ledger.snapshot()

    @property
    def last_compaction_checkpoint(self) -> CompactionCheckpoint | None:
        """Return the most recent completed compaction receipt, if any."""
        value = self.metadata.get("last_compaction_checkpoint")
        if not isinstance(value, dict):
            return None
        try:
            return CompactionCheckpoint.from_dict(value)
        except (KeyError, TypeError, ValueError):
            return None

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

    def add_tool_result(
        self,
        result: ToolResult,
        *,
        name: str,
        parent_id: str | None = None,
        **metadata: Any,
    ) -> SessionEntry:
        """Persist a tool result and its transcript activation anchor."""
        if result.added_tool_names:
            metadata["added_tool_names"] = list(dict.fromkeys(result.added_tool_names))
        return self.add_message(
            "tool",
            result.serialize(),
            parent_id,
            name=name,
            **metadata,
        )

    def available_tool_names_at(
        self,
        entry_id: str | None = None,
        *,
        initial_tool_names: Iterable[str] = (),
    ) -> set[str]:
        """Return the branch-local active tool set at a transcript point."""
        return self.tree.available_tool_names_at(
            entry_id,
            initial_tool_names=initial_tool_names,
        )

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
        reason: CompactionReason | str = CompactionReason.MANUAL,
        usage: dict[str, int | None] | None = None,
        checkpoint_id: str | None = None,
        replacement_messages: Iterable[Any] | None = None,
    ) -> list[SessionEntry]:
        """Compact old messages.

        Args:
            instructions: Custom compaction instructions
            max_tool_chars: Maximum serialized characters per summarized tool result
            reason: Why compaction was requested
            usage: Optional before/after token counts
            checkpoint_id: Correlation identifier supplied by overflow recovery
            replacement_messages: Exact successful retry context to persist. A
                leading host-owned base system prompt is omitted because the
                host reconstructs it independently.

        Returns:
            Compacted messages
        """
        reason = CompactionReason(reason)

        # Get current path
        path = self.get_current_conversation()

        if len(path) <= 10 and reason is not CompactionReason.OVERFLOW:
            return path

        if len(path) <= 1:
            return path

        # Keep recent messages
        recent_count = min(5, max(1, len(path) - 1))
        recent = path[-recent_count:]

        # Compact older messages without embedding full tool payloads.
        old = path[:-recent_count]
        before_root_id = path[0].id
        before_current_id = self.tree.current_id

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

        summary_metadata: dict[str, Any] = {
            "compacted": True,
            "original_count": len(old),
            "compaction_reason": reason.value,
        }
        replacement_specs: list[tuple[str, str, dict[str, Any]]] = []
        if replacement_messages is not None:
            for index, message in enumerate(replacement_messages):
                if isinstance(message, dict):
                    role = message.get("role")
                    content = message.get("content")
                    raw_metadata = message.get("metadata")
                else:
                    role = getattr(message, "role", None)
                    content = getattr(message, "content", None)
                    raw_metadata = getattr(message, "metadata", None)
                if not isinstance(role, str) or not isinstance(content, str):
                    continue
                metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
                # The base agent system prompt is reconstructed independently
                # by the product host; only compacted system messages belong in
                # the Session transcript.
                if index == 0 and role == "system" and not metadata.get("compacted"):
                    continue
                replacement_specs.append((role, content, metadata))

        if not replacement_specs:
            replacement_specs = [
                ("system", summary_content, summary_metadata),
                *[(entry.role, entry.content, dict(entry.metadata)) for entry in recent],
            ]

        inherited_tool_names: list[str] = []
        for entry in path:
            added = entry.metadata.get("added_tool_names", ())
            if isinstance(added, list | tuple | set):
                inherited_tool_names.extend(
                    name for name in added if isinstance(name, str) and name
                )

        compacted_path: list[SessionEntry] = []
        parent_id: str | None = None
        for role, content, metadata in replacement_specs:
            entry = SessionEntry(
                parent_id=parent_id,
                role=role,
                content=content,
                metadata=dict(metadata),
            )
            compacted_path.append(entry)
            parent_id = entry.id

        compacted_root = compacted_path[0]
        compacted_root.metadata.update(summary_metadata)
        if inherited_tool_names:
            existing_names = compacted_root.metadata.get("added_tool_names", ())
            prior_names = (
                [name for name in existing_names if isinstance(name, str) and name]
                if isinstance(existing_names, list | tuple | set)
                else []
            )
            compacted_root.metadata["added_tool_names"] = list(
                dict.fromkeys([*prior_names, *inherited_tool_names])
            )

        after_current_id = compacted_path[-1].id
        after_token_value = usage.get("after_tokens") if usage else None
        before_token_value = usage.get("before_tokens") if usage else None
        after_tokens = int(after_token_value) if after_token_value is not None else None
        if before_token_value is not None and after_tokens is None:
            from .token_counter import count_message_tokens

            after_tokens = count_message_tokens(
                [{"role": entry.role, "content": entry.content} for entry in compacted_path],
                self.metadata.get("model"),
            )
        checkpoint = CompactionCheckpoint(
            id=checkpoint_id or str(uuid.uuid4()),
            reason=reason,
            original_count=len(old),
            compacted_count=len(compacted_path),
            before_root_id=before_root_id,
            before_current_id=before_current_id,
            after_root_id=compacted_root.id,
            after_current_id=after_current_id,
            before_tokens=int(before_token_value) if before_token_value is not None else None,
            after_tokens=after_tokens,
        )
        compacted_root.metadata["compaction_checkpoint"] = checkpoint.to_dict()
        # Preserve the original tree as historical branches. The compacted
        # current path is detached, so no sibling can inherit this branch's
        # summary or tool payloads.
        self.tree.entries.update({entry.id: entry for entry in compacted_path})
        self.tree.root_id = compacted_root.id
        self.tree.current_id = after_current_id

        self.usage_ledger.record_compaction(
            reason=reason,
            before_tokens=checkpoint.before_tokens,
            after_tokens=checkpoint.after_tokens,
            metadata={"checkpoint_id": checkpoint.id},
        )
        self.metadata["usage"] = self.usage_ledger.snapshot()
        self.metadata["last_compaction_checkpoint"] = checkpoint.to_dict()

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
            session_dir=self.session_dir,
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
        if path is None and self._save_path is not None:
            path = self._save_path
        if path is None:
            # Auto-generate path
            session_dir = resolve_session_dir(self.workspace, self.session_dir)
            session_dir.mkdir(parents=True, exist_ok=True)
            file_id = self.id[:8] if _UUID_LIKE_ID_RE.fullmatch(self.id) else self.id
            path = session_dir / f"{self.name}-{file_id}.jsonl"
        else:
            path = Path(path)

        self.metadata["usage"] = self.usage_ledger.snapshot()
        metadata = dict(self.metadata)
        metadata["entries"] = len(self.tree.entries)

        # Save metadata and tree. Persist the authoritative current/root ids so
        # reload restores the exact conversation tip instead of inferring it from
        # entry timestamps (which resurrects stale off-path branch leaves).
        data = {
            "id": self.id,
            "name": self.name,
            "workspace": str(self.workspace),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "current_id": self.tree.current_id,
            "root_id": self.tree.root_id,
            "metadata": metadata,
        }

        # Write header + tree tail without duplicating the tree in metadata.
        with open(path, "w") as f:
            f.write(json.dumps(data) + "\n")
            for entry in self.tree.entries.values():
                f.write(entry.model_dump_json() + "\n")

        self._save_path = path.resolve()
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
        workspace = header.get("workspace")
        resolved_workspace = (
            str(Path(workspace).expanduser())
            if isinstance(workspace, str) and workspace
            else str(path.parent.parent)
        )
        session = cls(name=header["name"], workspace=resolved_workspace, auto_save=False)
        session.session_dir = path.parent.resolve()

        session.id = header["id"]
        session.created_at = datetime.fromisoformat(header["created_at"])
        session.updated_at = datetime.fromisoformat(header["updated_at"])
        session.metadata = header["metadata"]
        usage_snapshot = session.metadata.get("usage")
        session.usage_ledger = UsageLedger(
            usage_snapshot if isinstance(usage_snapshot, dict) else None
        )
        session.metadata["usage"] = session.usage_ledger.snapshot()
        session.tree = tree
        session._save_path = path.resolve()

        # Prefer the persisted tip/root when present and still valid; fall back
        # to from_jsonl_iter's timestamp heuristic for legacy files that predate
        # these header fields.
        header_current = header.get("current_id")
        if isinstance(header_current, str) and header_current in tree.entries:
            tree.current_id = header_current
        header_root = header.get("root_id")
        if isinstance(header_root, str) and header_root in tree.entries:
            tree.root_id = header_root

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
