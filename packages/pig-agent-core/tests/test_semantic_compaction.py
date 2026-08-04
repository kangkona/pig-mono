"""Semantic compaction keeps branch meaning without weakening tree guarantees."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from pig_agent_core import Agent, CompactionReason, Session, UsageKind
from pig_agent_core.resilience.retry import ResilienceExhaustedError
from pig_agent_core.tools import ToolResult
from pig_llm import LLM, Response


class SummaryLLM:
    """Minimal synchronous LLM used by the semantic compaction boundary."""

    def __init__(
        self,
        content: str = "Semantic summary",
        *,
        finish_reason: str = "stop",
    ) -> None:
        self.config = SimpleNamespace(model="summary-model", max_retries=0)
        self.content = content
        self.finish_reason = finish_reason
        self.calls: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        return Response(
            content=self.content,
            model="summary-model",
            usage={"input_tokens": 80, "output_tokens": 12},
            finish_reason=self.finish_reason,
        )


class FailingSummaryLLM(SummaryLLM):
    def chat(self, **kwargs: Any) -> Response:
        self.calls.append(kwargs)
        raise RuntimeError("summary provider unavailable")


def _session_with_long_branch() -> Session:
    session = Session(name="semantic", auto_save=False)
    session.add_message("user", "Keep the deployment on port 4312")
    session.add_tool_result(
        ToolResult(ok=True, data={"matches": ["alpha"]}, added_tool_names=["late_search"]),
        name="discover_tools",
    )
    for index in range(10):
        role = "assistant" if index % 2 else "user"
        session.add_message(role, f"branch message {index}")
    return session


def test_semantic_compaction_commits_summary_recent_tail_and_separate_usage() -> None:
    session = _session_with_long_branch()
    llm = SummaryLLM("Port 4312 is required; late_search was activated.")
    agent = Agent(llm=cast(LLM, llm), session=session)
    agent.usage = session.usage_ledger
    recent_before = [
        (entry.role, entry.content, dict(entry.metadata))
        for entry in session.get_current_conversation()[-5:]
    ]

    compacted = agent.compact_session(
        "Preserve operational constraints",
        reason=CompactionReason.THRESHOLD,
        before_tokens=1_200,
    )

    assert len(llm.calls) == 1
    prompt = llm.calls[0]["messages"][-1].content
    assert "Keep the deployment on port 4312" in prompt
    assert "Preserve operational constraints" in prompt
    assert compacted[0].content == "Port 4312 is required; late_search was activated."
    assert compacted[0].metadata["semantic_summary"] is True
    assert [
        (entry.role, entry.content, dict(entry.metadata)) for entry in compacted[1:]
    ] == recent_before
    assert session.available_tool_names_at() == {"late_search"}

    checkpoint = session.last_compaction_checkpoint
    assert checkpoint is not None
    assert checkpoint.reason is CompactionReason.THRESHOLD
    assert checkpoint.before_tokens == 1_200
    usage = session.usage_ledger.snapshot()["by_kind"]
    assert usage[UsageKind.BRANCH_SUMMARY.value]["calls"] == 1
    assert usage[UsageKind.BRANCH_SUMMARY.value]["input_tokens"] == 80
    assert usage[UsageKind.COMPACTION.value]["calls"] == 1


def test_semantic_compaction_failure_leaves_session_and_usage_unchanged() -> None:
    session = _session_with_long_branch()
    agent = Agent(llm=cast(LLM, FailingSummaryLLM()), session=session)
    agent.usage = session.usage_ledger
    tree_before = session.tree.to_jsonl()
    metadata_before = dict(session.metadata)
    usage_before = session.usage_ledger.snapshot()
    root_before = session.tree.root_id
    current_before = session.tree.current_id

    with pytest.raises(ResilienceExhaustedError):
        agent.compact_session(reason=CompactionReason.MANUAL)

    assert session.tree.to_jsonl() == tree_before
    assert session.metadata == metadata_before
    assert session.usage_ledger.snapshot() == usage_before
    assert session.tree.root_id == root_before
    assert session.tree.current_id == current_before
    assert session.last_compaction_checkpoint is None


def test_truncated_semantic_summary_never_replaces_the_branch() -> None:
    session = _session_with_long_branch()
    llm = SummaryLLM("Plausible but truncated summary", finish_reason="length")
    agent = Agent(llm=cast(LLM, llm), session=session)
    agent.usage = session.usage_ledger
    tree_before = session.tree.to_jsonl()
    usage_before = session.usage_ledger.snapshot()

    with pytest.raises(RuntimeError, match="did not complete: length"):
        agent.compact_session(reason=CompactionReason.MANUAL)

    assert session.tree.to_jsonl() == tree_before
    assert session.usage_ledger.snapshot() == usage_before
    assert session.last_compaction_checkpoint is None


def test_semantic_compaction_short_session_is_a_noop_without_llm_call() -> None:
    session = Session(name="short", auto_save=False)
    session.add_message("user", "hello")
    llm = SummaryLLM()
    agent = Agent(llm=cast(LLM, llm), session=session)

    compacted = agent.compact_session()

    assert [entry.content for entry in compacted] == ["hello"]
    assert llm.calls == []
    assert session.last_compaction_checkpoint is None


def test_semantic_compaction_save_failure_rolls_back_memory_and_preserves_file(
    tmp_path: Any,
) -> None:
    session = _session_with_long_branch()
    durable_path = session.save(tmp_path / "semantic.jsonl")
    session.auto_save = True
    durable_bytes = durable_path.read_bytes()
    tree_before = session.tree.to_jsonl()
    root_before = session.tree.root_id
    current_before = session.tree.current_id
    compactions_before = session.usage_ledger.snapshot()["by_kind"][UsageKind.COMPACTION.value][
        "calls"
    ]
    agent = Agent(llm=cast(LLM, SummaryLLM()), session=session)
    agent.usage = session.usage_ledger

    with (
        patch("pig_agent_core.session.os.replace", side_effect=OSError("disk unavailable")),
        pytest.raises(OSError, match="disk unavailable"),
    ):
        agent.compact_session(reason=CompactionReason.MANUAL)

    assert session.tree.to_jsonl() == tree_before
    assert session.tree.root_id == root_before
    assert session.tree.current_id == current_before
    assert session.last_compaction_checkpoint is None
    assert durable_path.read_bytes() == durable_bytes
    usage = session.usage_ledger.snapshot()["by_kind"]
    assert usage[UsageKind.COMPACTION.value]["calls"] == compactions_before
    # The provider summary call really happened and remains separately accounted.
    assert usage[UsageKind.BRANCH_SUMMARY.value]["calls"] == 1
