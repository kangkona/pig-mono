"""Compatibility adapters and direct provider-boundary run authority tests."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pig_agent_core.compaction import CompactionCheckpoint, CompactionReason
from pig_agent_core.resilience.retry import resilient_sync_call
from pig_agent_core.run_integrity import (
    AttemptStatus,
    EvidenceType,
    OperationStatus,
    RunAuthority,
    RunStatus,
    SQLiteRunStore,
    canonical_json,
    compaction_payload,
    permission_denial_payload,
    retry_observation_payload,
    tool_audit_payload,
    turn_outcome_status,
    usage_record_payload,
)
from pig_agent_core.tools.audit import ToolAuditEntry
from pig_agent_core.usage import UsageKind, UsageRecord
from pig_llm import Response, TurnOutcome

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def test_compatibility_payloads_digest_untrusted_content() -> None:
    secret = "sk-secret-provider-token"
    usage = UsageRecord(
        kind=UsageKind.ASSISTANT,
        model="test-model",
        input_tokens=3,
        output_tokens=2,
        chargeable=True,
        metadata={"authorization": secret},
    )
    checkpoint = CompactionCheckpoint(
        reason=CompactionReason.OVERFLOW,
        original_count=12,
        compacted_count=5,
        before_root_id="before-root",
        before_current_id="before-current",
        after_root_id="after-root",
        after_current_id="after-current",
    )
    audit = ToolAuditEntry(
        tool_name="write_file",
        timestamp=NOW.timestamp(),
        user_id="private-user",
        args={"path": "/private/file", "content": secret},
        success=False,
        error=f"provider rejected {secret}",
        metadata={"authorization": secret},
    )

    payloads = {
        "retry": retry_observation_payload(
            {
                "retry_id": "retry-1",
                "phase": "failed",
                "attempt": 1,
                "error": f"provider rejected {secret}",
            }
        ),
        "usage": usage_record_payload(usage),
        "compaction": compaction_payload(checkpoint),
        "denial": permission_denial_payload(
            {
                "code": "permission_denied",
                "action": "write_file",
                "target": "/private/file",
                "message": f"do not expose {secret}",
            }
        ),
        "audit": tool_audit_payload(audit),
    }
    encoded = canonical_json(payloads)

    assert secret not in encoded
    assert "/private/file" not in encoded
    assert "private-user" not in encoded
    assert payloads["compaction"] == checkpoint.to_dict()


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (TurnOutcome.COMPLETED, RunStatus.COMPLETED),
        (TurnOutcome.TOOL_CALLS, None),
        (TurnOutcome.ABORTED, RunStatus.OUTCOME_UNKNOWN),
        (TurnOutcome.UNKNOWN, RunStatus.OUTCOME_UNKNOWN),
        (TurnOutcome.PROVIDER_ERROR, RunStatus.FAILED),
    ],
)
def test_turn_outcome_status(outcome: TurnOutcome, expected: RunStatus | None) -> None:
    assert turn_outcome_status(outcome) is expected


def test_run_authority_records_one_completed_provider_operation(tmp_path: Path) -> None:
    secret_input = "do not persist this prompt token"
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store, owner_id="test-owner")
        context = authority.begin_turn(
            session_id="session-1",
            user_input=secret_input,
            occurred_at=NOW,
        )
        authority.record_provider_attempt(
            {
                "retry_id": "retry-1",
                "phase": "started",
                "attempt": 1,
                "max_retries": 2,
                "model": "test-model",
            }
        )
        authority.record_provider_attempt(
            {
                "retry_id": "retry-1",
                "phase": "succeeded",
                "attempt": 1,
                "max_retries": 2,
                "model": "test-model",
            }
        )

        run_id = authority.finish_turn(
            context,
            outcome=TurnOutcome.COMPLETED,
            raw_finish_reason="stop",
            usage_snapshot={"llm_calls": 1, "input_tokens": 3, "output_tokens": 2},
        )
        snapshot = store.verify(run_id)
        evidence_json = canonical_json(
            [item.model_dump(mode="json") for item in store.get_evidence(run_id)]
        )

    operation = next(iter(snapshot.operations.values()))
    attempt = next(iter(snapshot.attempts.values()))
    assert snapshot.run.status is RunStatus.COMPLETED
    assert operation.status is OperationStatus.COMPLETED
    assert operation.receipt_recorded is True
    assert attempt.status is AttemptStatus.SUCCEEDED
    assert secret_input not in evidence_json
    assert authority.last_run_id == run_id
    assert authority.is_active is False


def test_partial_provider_failure_forces_outcome_unknown(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="hello",
            occurred_at=NOW,
        )
        authority.record_provider_attempt(
            {
                "retry_id": "retry-1",
                "phase": "started",
                "attempt": 1,
                "max_retries": 2,
                "model": "test-model",
            }
        )
        authority.record_provider_attempt(
            {
                "retry_id": "retry-1",
                "phase": "failed",
                "attempt": 1,
                "max_retries": 2,
                "model": "test-model",
                "partial_output": True,
                "error": "stream reset",
            }
        )
        run_id = authority.finish_turn(
            context,
            outcome=TurnOutcome.PROVIDER_ERROR,
            raw_finish_reason="provider_error",
        )
        snapshot = store.verify(run_id)
        evidence_types = {item.type for item in store.get_evidence(run_id)}

    assert snapshot.run.status is RunStatus.OUTCOME_UNKNOWN
    assert next(iter(snapshot.operations.values())).status is OperationStatus.OUTCOME_UNKNOWN
    assert next(iter(snapshot.attempts.values())).status is AttemptStatus.OUTCOME_UNKNOWN
    assert EvidenceType.PROVIDER_PARTIAL_OUTPUT in evidence_types


def test_provider_attempt_callback_failure_prevents_dispatch() -> None:
    llm = Mock()
    llm.config = SimpleNamespace(model="test-model", provider="openai")
    llm.chat.return_value = Response(content="ok", model="test-model", finish_reason="stop")

    def ledger_unavailable(data: dict[str, object]) -> None:
        assert data["phase"] == "started"
        raise RuntimeError("ledger unavailable")

    with pytest.raises(RuntimeError, match="ledger unavailable"):
        resilient_sync_call(llm, [], max_retries=0, attempt_callback=ledger_unavailable)

    llm.chat.assert_not_called()
