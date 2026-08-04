"""Fail-closed restart recovery fixtures for the R1 run protocol."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pig_agent_core.run_integrity import (
    AttemptStatus,
    OperationKind,
    OperationStatus,
    RecoveryClassification,
    RunStatus,
    SQLiteRunStore,
)

NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
LEASE_STARTED = NOW - timedelta(minutes=2)
LEASE_EXPIRED = NOW - timedelta(minutes=1)


def _owned_running_run(store: SQLiteRunStore) -> str:
    run = store.create_run(
        session_id="session-1",
        owner_id="worker-1",
        lease_expires_at=LEASE_EXPIRED,
        occurred_at=LEASE_STARTED,
    )
    store.transition_run(run.id, RunStatus.RUNNING, occurred_at=LEASE_STARTED)
    return run.id


def test_recovery_before_dispatch_keeps_stable_operation_waiting(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        run_id = _owned_running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:turn-1",
            occurred_at=LEASE_STARTED,
        )

        decision = store.recover_expired(run_id, now=NOW)
        snapshot = store.get_snapshot(run_id)

    assert decision.classification is RecoveryClassification.BEFORE_DISPATCH
    assert decision.resume_allowed is True
    assert decision.should_redispatch is False
    assert snapshot.run.status is RunStatus.WAITING
    assert snapshot.run.terminal_evidence_id is None
    assert snapshot.operations[operation.id].status is OperationStatus.WAITING
    assert snapshot.operations[operation.id].idempotency_key == "provider:turn-1"


def test_recovery_during_provider_streaming_is_outcome_unknown(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        run_id = _owned_running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:turn-1",
            occurred_at=LEASE_STARTED,
        )
        attempt = store.start_attempt(operation.id, occurred_at=LEASE_STARTED)
        store.dispatch_operation(operation.id, occurred_at=LEASE_STARTED)
        store.record_provider_partial_output(
            operation.id,
            chunk_digest="sha256:partial",
            occurred_at=LEASE_STARTED,
        )

        decision = store.recover_expired(run_id, now=NOW)
        snapshot = store.get_snapshot(run_id)

    assert decision.classification is RecoveryClassification.PROVIDER_OUTCOME_UNKNOWN
    assert decision.should_redispatch is False
    assert snapshot.run.status is RunStatus.OUTCOME_UNKNOWN
    assert snapshot.operations[operation.id].partial_output is True
    assert snapshot.operations[operation.id].status is OperationStatus.OUTCOME_UNKNOWN
    assert snapshot.attempts[attempt.id].status is AttemptStatus.OUTCOME_UNKNOWN


def test_recovery_before_tool_effect_allows_explicit_resume_without_redispatch(
    tmp_path: Path,
) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        run_id = _owned_running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.TOOL,
            idempotency_key="tool:write-1",
            occurred_at=LEASE_STARTED,
        )
        attempt = store.start_attempt(operation.id, occurred_at=LEASE_STARTED)
        store.dispatch_operation(operation.id, occurred_at=LEASE_STARTED)

        decision = store.recover_expired(run_id, now=NOW)
        snapshot = store.get_snapshot(run_id)

    assert decision.classification is RecoveryClassification.BEFORE_TOOL_EFFECT
    assert decision.resume_allowed is True
    assert decision.should_redispatch is False
    assert snapshot.run.status is RunStatus.WAITING
    assert snapshot.operations[operation.id].effect_started is False
    assert snapshot.operations[operation.id].status is OperationStatus.WAITING
    assert snapshot.attempts[attempt.id].status is AttemptStatus.FAILED


def test_recovery_after_unconfirmed_tool_effect_is_outcome_unknown(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        run_id = _owned_running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.TOOL,
            idempotency_key="tool:write-1",
            occurred_at=LEASE_STARTED,
        )
        attempt = store.start_attempt(operation.id, occurred_at=LEASE_STARTED)
        store.dispatch_operation(operation.id, occurred_at=LEASE_STARTED)
        store.record_effect_started(operation.id, occurred_at=LEASE_STARTED)

        decision = store.recover_expired(run_id, now=NOW)
        snapshot = store.get_snapshot(run_id)

    assert decision.classification is RecoveryClassification.TOOL_OUTCOME_UNKNOWN
    assert decision.resume_allowed is False
    assert decision.should_redispatch is False
    assert snapshot.run.status is RunStatus.OUTCOME_UNKNOWN
    assert snapshot.operations[operation.id].status is OperationStatus.OUTCOME_UNKNOWN
    assert snapshot.attempts[attempt.id].status is AttemptStatus.OUTCOME_UNKNOWN


def test_recovery_after_durable_completion_is_a_read_only_noop(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        run_id = _owned_running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:turn-1",
            occurred_at=LEASE_STARTED,
        )
        attempt = store.start_attempt(operation.id, occurred_at=LEASE_STARTED)
        store.dispatch_operation(operation.id, occurred_at=LEASE_STARTED)
        store.finish_attempt(attempt.id, AttemptStatus.SUCCEEDED, occurred_at=LEASE_STARTED)
        store.complete_operation(
            operation.id,
            result_digest="sha256:result",
            occurred_at=LEASE_STARTED,
        )
        store.transition_run(run_id, RunStatus.COMPLETED, occurred_at=LEASE_STARTED)
        event_count = store.event_count(run_id)

        decision = store.recover_expired(run_id, now=NOW)

        assert decision.classification is RecoveryClassification.ALREADY_TERMINAL
        assert decision.status is RunStatus.COMPLETED
        assert decision.should_redispatch is False
        assert store.event_count(run_id) == event_count


def test_repeated_expired_recovery_does_not_append_duplicate_decisions(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        run_id = _owned_running_run(store)

        first = store.recover_expired(run_id, now=NOW)
        event_count = store.event_count(run_id)
        second = store.recover_expired(run_id, now=NOW)

        assert first.classification is RecoveryClassification.BEFORE_DISPATCH
        assert second.classification is RecoveryClassification.UNOWNED
        assert store.event_count(run_id) == event_count


def test_unexpired_lease_is_not_recovered(tmp_path: Path) -> None:
    with SQLiteRunStore(tmp_path / "runs.sqlite3") as store:
        run = store.create_run(
            session_id="session-1",
            owner_id="worker-1",
            lease_expires_at=NOW + timedelta(minutes=1),
            occurred_at=LEASE_STARTED,
        )
        store.transition_run(run.id, RunStatus.RUNNING, occurred_at=LEASE_STARTED)
        event_count = store.event_count(run.id)

        decision = store.recover_expired(run.id, now=NOW)

        assert decision.classification is RecoveryClassification.LEASE_ACTIVE
        assert decision.status is RunStatus.RUNNING
        assert store.event_count(run.id) == event_count
