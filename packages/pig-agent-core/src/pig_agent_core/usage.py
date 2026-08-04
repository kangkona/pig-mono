"""Categorized usage accounting for agent, tool, and maintenance work."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class UsageKind(str, Enum):
    """Why usage was incurred.

    Keeping maintenance work separate prevents compaction and branch summaries
    from being presented as ordinary assistant turns.
    """

    ASSISTANT = "assistant"
    TOOL = "tool"
    COMPACTION = "compaction"
    BRANCH_SUMMARY = "branch_summary"


@dataclass(frozen=True)
class UsageRecord:
    """Receipt for one usage-accounting operation."""

    kind: UsageKind
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    chargeable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _empty_bucket() -> dict[str, int]:
    return {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
    }


class UsageLedger:
    """Aggregate usage without conflating user turns and runtime maintenance."""

    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        self._by_kind: dict[str, dict[str, int]] = {
            kind.value: _empty_bucket() for kind in UsageKind
        }
        self._llm_calls = 0
        self._tool_calls = 0
        if snapshot:
            self._restore(snapshot)

    def _restore(self, snapshot: dict[str, Any]) -> None:
        self._llm_calls = max(0, int(snapshot.get("llm_calls", 0)))
        self._tool_calls = max(0, int(snapshot.get("tool_calls", 0)))
        raw_by_kind = snapshot.get("by_kind", {})
        if not isinstance(raw_by_kind, dict):
            return
        for kind in UsageKind:
            raw = raw_by_kind.get(kind.value)
            if not isinstance(raw, dict):
                continue
            bucket = self._by_kind[kind.value]
            for key, value in raw.items():
                if isinstance(value, int | float):
                    bucket[str(key)] = max(0, int(value))

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore a prior snapshot while preserving this ledger's identity."""
        self._by_kind = {kind.value: _empty_bucket() for kind in UsageKind}
        self._llm_calls = 0
        self._tool_calls = 0
        self._restore(snapshot)

    def record_llm(
        self,
        *,
        kind: UsageKind = UsageKind.ASSISTANT,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Record an actual provider call under its semantic purpose."""
        if kind is UsageKind.TOOL:
            raise ValueError("LLM usage cannot use the tool category")
        record = UsageRecord(
            kind=kind,
            model=model,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            cached_tokens=max(0, int(cached_tokens)),
            chargeable=True,
            metadata=dict(metadata or {}),
        )
        bucket = self._by_kind[kind.value]
        bucket["calls"] += 1
        bucket["input_tokens"] += record.input_tokens
        bucket["output_tokens"] += record.output_tokens
        bucket["cached_tokens"] += min(record.cached_tokens, record.input_tokens)
        self._llm_calls += 1
        return record

    def record_tool(self, tool_name: str, *, metadata: dict[str, Any] | None = None) -> UsageRecord:
        """Record one attempted tool execution separately from token usage."""
        record = UsageRecord(
            kind=UsageKind.TOOL,
            metadata={"tool_name": tool_name, **dict(metadata or {})},
        )
        self._by_kind[UsageKind.TOOL.value]["calls"] += 1
        self._tool_calls += 1
        return record

    def record_compaction(
        self,
        *,
        reason: str | Enum,
        before_tokens: int | None = None,
        after_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Record structural context reduction, which is not itself billable."""
        reason_value = reason.value if isinstance(reason, Enum) else str(reason)
        before = max(0, int(before_tokens or 0))
        after = max(0, int(after_tokens or 0))
        reclaimed = max(0, before - after)
        bucket = self._by_kind[UsageKind.COMPACTION.value]
        bucket["calls"] += 1
        bucket["before_tokens"] = bucket.get("before_tokens", 0) + before
        bucket["after_tokens"] = bucket.get("after_tokens", 0) + after
        bucket["tokens_reclaimed"] = bucket.get("tokens_reclaimed", 0) + reclaimed
        return UsageRecord(
            kind=UsageKind.COMPACTION,
            metadata={
                "reason": reason_value,
                "before_tokens": before,
                "after_tokens": after,
                "tokens_reclaimed": reclaimed,
                **dict(metadata or {}),
            },
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable cumulative snapshot."""
        input_tokens = sum(
            bucket.get("input_tokens", 0)
            for kind, bucket in self._by_kind.items()
            if kind != UsageKind.TOOL.value
        )
        output_tokens = sum(
            bucket.get("output_tokens", 0)
            for kind, bucket in self._by_kind.items()
            if kind != UsageKind.TOOL.value
        )
        cached_tokens = sum(
            bucket.get("cached_tokens", 0)
            for kind, bucket in self._by_kind.items()
            if kind != UsageKind.TOOL.value
        )
        return {
            "llm_calls": self._llm_calls,
            "tool_calls": self._tool_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "by_kind": copy.deepcopy(self._by_kind),
        }
