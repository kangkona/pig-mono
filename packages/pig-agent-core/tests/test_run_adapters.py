"""Compatibility adapters and direct provider-boundary run authority tests."""

from datetime import datetime, timedelta, timezone
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
    RecoveryClassification,
    RunAuthority,
    RunStatus,
    SQLiteRunStore,
    ToolOutcomeUnknownError,
    canonical_json,
    compaction_payload,
    permission_denial_payload,
    retry_observation_payload,
    tool_audit_payload,
    turn_outcome_status,
    usage_record_payload,
)
from pig_agent_core.tools.audit import ToolAuditEntry
from pig_agent_core.tools.registry import ToolRegistry
from pig_agent_core.usage import UsageKind, UsageRecord
from pig_llm import Response, TurnOutcome

NOW = datetime.now(timezone.utc)


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


def test_provider_retries_share_one_operation_and_use_distinct_attempts(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="hello",
            occurred_at=NOW,
        )
        for phase, attempt in (("started", 1), ("failed", 1), ("started", 2), ("succeeded", 2)):
            authority.record_provider_attempt(
                {
                    "retry_id": "retry-1",
                    "phase": phase,
                    "attempt": attempt,
                    "max_retries": 1,
                    "model": "test-model",
                    "reason": "transport" if phase == "failed" else None,
                }
            )
        run_id = authority.finish_turn(
            context,
            outcome=TurnOutcome.COMPLETED,
            raw_finish_reason="stop",
        )
        snapshot = store.verify(run_id)

    assert len(snapshot.operations) == 1
    assert [item.status for item in snapshot.attempts.values()] == [
        AttemptStatus.FAILED,
        AttemptStatus.SUCCEEDED,
    ]


def test_tool_execution_records_effect_and_durable_receipt(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="write a file",
            occurred_at=NOW,
        )
        common = {
            "execution_id": "call-1:write_file",
            "tool_name": "write_file",
            "args": {"path": "/private/file", "content": "secret"},
        }
        authority.record_tool_execution({**common, "phase": "created"})
        authority.record_tool_execution({**common, "phase": "started", "attempt": 1})
        authority.record_tool_execution({**common, "phase": "succeeded", "attempt": 1})
        authority.record_tool_execution({**common, "phase": "completed", "ok": True})
        run_id = authority.finish_turn(
            context,
            outcome=TurnOutcome.COMPLETED,
            raw_finish_reason="stop",
        )
        snapshot = store.verify(run_id)
        evidence_json = canonical_json(
            [item.model_dump(mode="json") for item in store.get_evidence(run_id)]
        )

    operation = next(iter(snapshot.operations.values()))
    assert operation.status is OperationStatus.COMPLETED
    assert operation.effect_started is True
    assert operation.receipt_recorded is True
    assert "/private/file" not in evidence_json
    assert '"content":"secret"' not in evidence_json


def test_known_tool_failure_stays_failed_while_run_can_complete(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="try a tool and recover",
            occurred_at=NOW,
        )
        common = {
            "execution_id": "call-1:failing_tool",
            "tool_name": "failing_tool",
            "args": {},
        }
        authority.record_tool_execution({**common, "phase": "created"})
        authority.record_tool_execution({**common, "phase": "started", "attempt": 1})
        authority.record_tool_execution({**common, "phase": "succeeded", "attempt": 1, "ok": False})
        authority.record_tool_execution(
            {**common, "phase": "completed", "ok": False, "error": "known failure"}
        )

        run_id = authority.finish_turn(
            context,
            outcome=TurnOutcome.COMPLETED,
            raw_finish_reason="stop",
        )
        snapshot = store.verify(run_id)

    operation = next(iter(snapshot.operations.values()))
    assert snapshot.run.status is RunStatus.COMPLETED
    assert operation.status is OperationStatus.FAILED
    assert operation.receipt_recorded is True


def test_known_provider_failure_is_not_downgraded_to_outcome_unknown(
    tmp_path: Path,
) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="hello",
            occurred_at=NOW,
        )
        common = {
            "retry_id": "retry-1",
            "attempt": 1,
            "max_retries": 0,
            "model": "test-model",
        }
        authority.record_provider_attempt({**common, "phase": "started"})
        authority.record_provider_attempt({**common, "phase": "failed", "reason": "provider_error"})

        run_id = authority.fail_turn(context, RuntimeError("provider rejected request"))
        snapshot = store.verify(run_id)

    operation = next(iter(snapshot.operations.values()))
    assert snapshot.run.status is RunStatus.FAILED
    assert operation.status is OperationStatus.FAILED
    assert operation.receipt_recorded is True


def test_fail_turn_does_not_borrow_dispatch_from_a_failed_retry_attempt(
    tmp_path: Path,
) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="hello",
            occurred_at=NOW,
        )
        common = {
            "retry_id": "retry-1",
            "attempt": 1,
            "max_retries": 2,
            "model": "test-model",
        }
        authority.record_provider_attempt({**common, "phase": "started"})
        authority.record_provider_attempt({**common, "phase": "failed", "reason": "transport"})
        operation_id = context.provider_operations["retry-1"]
        second = store.start_attempt(operation_id, occurred_at=NOW)

        run_id = authority.fail_turn(context, RuntimeError("before retry dispatch"))
        snapshot = store.verify(run_id)

    operation = snapshot.operations[operation_id]
    assert snapshot.run.status is RunStatus.FAILED
    assert operation.status is OperationStatus.FAILED
    assert operation.receipt_recorded is True
    assert snapshot.attempts[second.id].status is AttemptStatus.FAILED
    assert snapshot.attempts[second.id].dispatch_recorded is False


def test_raw_finish_reason_is_only_persisted_as_a_digest(tmp_path: Path) -> None:
    secret_reason = "sk-sensitive-finish-reason"
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="hello",
            occurred_at=NOW,
        )
        run_id = authority.finish_turn(
            context,
            outcome=TurnOutcome.COMPLETED,
            raw_finish_reason=secret_reason,
        )
        evidence_json = canonical_json(
            [item.model_dump(mode="json") for item in store.get_evidence(run_id)]
        )

    assert secret_reason not in evidence_json


def test_interruption_between_tool_dispatch_and_effect_rolls_back_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="write a file",
            occurred_at=NOW,
        )
        common = {
            "execution_id": "call-1:write_file",
            "tool_name": "write_file",
            "args": {"path": "file.txt"},
        }
        authority.record_tool_execution({**common, "phase": "created"})
        original = store.record_effect_started

        def interrupt_before_effect(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("simulated process interruption")

        monkeypatch.setattr(store, "record_effect_started", interrupt_before_effect)
        with pytest.raises(RuntimeError, match="simulated process interruption"):
            authority.record_tool_execution({**common, "phase": "started", "attempt": 1})
        monkeypatch.setattr(store, "record_effect_started", original)

        before_recovery = store.get_snapshot(context.run_id)
        assert before_recovery.run.lease_expires_at is not None
        decision = store.recover_expired(
            context.run_id,
            now=before_recovery.run.lease_expires_at + timedelta(seconds=1),
        )

    operation = next(iter(before_recovery.operations.values()))
    assert operation.dispatch_recorded is False
    assert operation.effect_started is False
    assert decision.classification is RecoveryClassification.BEFORE_DISPATCH
    assert decision.resume_allowed is True
    assert decision.should_redispatch is False


def test_tool_ledger_failure_prevents_handler_effect() -> None:
    handler = Mock(return_value="written")

    def ledger_unavailable(data: dict[str, object]) -> None:
        if data["phase"] == "started":
            raise RuntimeError("ledger unavailable")

    registry = ToolRegistry(execution_callback=ledger_unavailable)
    registry.register(
        "write_file",
        handler,
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "write",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    )

    with pytest.raises(RuntimeError, match="ledger unavailable"):
        registry.execute_sync("write_file", execution_id="call-1:write_file")

    handler.assert_not_called()


@pytest.mark.asyncio
async def test_unconfirmed_tool_exception_blocks_retry_and_fallback(tmp_path: Path) -> None:
    effects: list[str] = []
    fallback = Mock(return_value="fallback")

    async def raises_after_effect() -> None:
        effects.append("primary")
        raise RuntimeError("connection lost after write")

    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store)
        context = authority.begin_turn(
            session_id="session-1",
            user_input="write",
            occurred_at=NOW,
        )
        registry = ToolRegistry(execution_callback=authority.record_tool_execution)
        schema = {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "write",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        registry.register("write_file", raises_after_effect, schema, max_retries=2)
        registry.register(
            "fallback_write",
            fallback,
            {
                "type": "function",
                "function": {
                    "name": "fallback_write",
                    "description": "fallback write",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )
        registry.set_fallback_tools("write_file", ["fallback_write"])
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="write_file", arguments="{}"),
        )

        with pytest.raises(ToolOutcomeUnknownError, match="automatic retry") as raised:
            await registry.execute(tool_call, user_id="user-1", meta={})

        run_id = authority.fail_turn(context, raised.value)
        snapshot = store.verify(run_id)

    operation = next(iter(snapshot.operations.values()))
    attempt = next(iter(snapshot.attempts.values()))
    assert effects == ["primary"]
    fallback.assert_not_called()
    assert attempt.status is AttemptStatus.OUTCOME_UNKNOWN
    assert operation.status is OperationStatus.OUTCOME_UNKNOWN
    assert snapshot.run.status is RunStatus.OUTCOME_UNKNOWN


def test_expired_run_owner_cannot_reach_tool_handler(tmp_path: Path) -> None:
    handler = Mock(return_value="written")
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store, owner_id="worker-1")
        authority.begin_turn(
            session_id="session-1",
            user_input="write",
            occurred_at=NOW - timedelta(minutes=6),
        )
        registry = ToolRegistry(execution_callback=authority.record_tool_execution)
        registry.register(
            "write_file",
            handler,
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "write",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        with pytest.raises(RuntimeError, match="lease has expired"):
            registry.execute_sync("write_file", execution_id="call-1:write_file")

    handler.assert_not_called()


def test_stale_run_owner_cannot_reach_tool_handler(tmp_path: Path) -> None:
    handler = Mock(return_value="written")
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        authority = RunAuthority(store, owner_id="worker-1")
        context = authority.begin_turn(
            session_id="session-1",
            user_input="write",
            occurred_at=NOW,
        )
        takeover_at = NOW + timedelta(minutes=6)
        store.acquire_lease(
            context.run_id,
            owner_id="worker-2",
            lease_expires_at=takeover_at + timedelta(minutes=5),
            occurred_at=takeover_at,
        )
        registry = ToolRegistry(execution_callback=authority.record_tool_execution)
        registry.register(
            "write_file",
            handler,
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "write",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )

        with pytest.raises(RuntimeError, match="not leased by worker-1"):
            registry.execute_sync("write_file", execution_id="call-1:write_file")

    handler.assert_not_called()


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
