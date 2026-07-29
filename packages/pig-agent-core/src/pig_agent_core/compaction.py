"""Shared compaction reason and checkpoint contracts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CompactionReason(str, Enum):
    """Stable reason shared by manual, threshold, and overflow compaction."""

    MANUAL = "manual"
    THRESHOLD = "threshold"
    OVERFLOW = "overflow"


@dataclass(frozen=True)
class CompactionCheckpoint:
    """Durable receipt describing a completed context transition."""

    reason: CompactionReason
    original_count: int
    compacted_count: int
    before_root_id: str | None
    before_current_id: str | None
    after_root_id: str | None
    after_current_id: str | None
    before_tokens: int | None = None
    after_tokens: int | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def tokens_reclaimed(self) -> int | None:
        """Return the non-negative token reduction when both counts are known."""
        if self.before_tokens is None or self.after_tokens is None:
            return None
        return max(0, self.before_tokens - self.after_tokens)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""
        return {
            "id": self.id,
            "reason": self.reason.value,
            "original_count": self.original_count,
            "compacted_count": self.compacted_count,
            "before_root_id": self.before_root_id,
            "before_current_id": self.before_current_id,
            "after_root_id": self.after_root_id,
            "after_current_id": self.after_current_id,
            "before_tokens": self.before_tokens,
            "after_tokens": self.after_tokens,
            "tokens_reclaimed": self.tokens_reclaimed,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CompactionCheckpoint:
        """Restore a checkpoint persisted in session metadata."""
        return cls(
            id=str(value["id"]),
            reason=CompactionReason(str(value["reason"])),
            original_count=int(value.get("original_count", 0)),
            compacted_count=int(value.get("compacted_count", 0)),
            before_root_id=value.get("before_root_id"),
            before_current_id=value.get("before_current_id"),
            after_root_id=value.get("after_root_id"),
            after_current_id=value.get("after_current_id"),
            before_tokens=(
                int(value["before_tokens"]) if value.get("before_tokens") is not None else None
            ),
            after_tokens=(
                int(value["after_tokens"]) if value.get("after_tokens") is not None else None
            ),
        )
