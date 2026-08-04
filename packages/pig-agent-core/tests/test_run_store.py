"""Transactional SQLite run ledger, projection, and replay contracts."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pig_agent_core.run_integrity import (
    AttemptStatus,
    ConcurrencyConflictError,
    EvidenceType,
    IdempotencyConflictError,
    IntegrityVerificationError,
    OperationKind,
    OperationStatus,
    RunStatus,
    SQLiteRunStore,
    content_digest,
    new_evidence_id,
)

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _store(path: Path) -> SQLiteRunStore:
    return SQLiteRunStore(path)


def _running_run(store: SQLiteRunStore) -> str:
    run = store.create_run(session_id="session-1", occurred_at=NOW)
    store.transition_run(run.id, RunStatus.RUNNING, occurred_at=NOW)
    return run.id


def test_append_persists_evidence_and_projection_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as store:
        run_id = _running_run(store)
        expected = store.get_snapshot(run_id)

    with _store(path) as reopened:
        assert reopened.get_snapshot(run_id) == expected
        assert [item.sequence for item in reopened.get_evidence(run_id)] == [1, 2]


def test_append_assigns_monotonic_sequence_and_hash_chain(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        store.record_evidence(
            run_id,
            EvidenceType.USAGE_OBSERVED,
            entity_id=run_id,
            payload={"input_tokens": 4},
            occurred_at=NOW,
        )

        evidence = store.get_evidence(run_id)

    assert [item.sequence for item in evidence] == [1, 2, 3]
    assert evidence[0].previous_digest is None
    assert evidence[1].previous_digest == evidence[0].digest
    assert evidence[2].previous_digest == evidence[1].digest


def test_duplicate_evidence_id_is_rejected_without_partial_append(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        evidence_id = new_evidence_id()
        store.record_evidence(
            run_id,
            EvidenceType.USAGE_OBSERVED,
            entity_id=run_id,
            payload={"calls": 1},
            evidence_id=evidence_id,
            occurred_at=NOW,
        )

        with pytest.raises(sqlite3.IntegrityError):
            store.record_evidence(
                run_id,
                EvidenceType.USAGE_OBSERVED,
                entity_id=run_id,
                payload={"calls": 2},
                evidence_id=evidence_id,
                occurred_at=NOW,
            )

        assert store.event_count(run_id) == 3


def test_event_append_and_projection_update_are_atomic(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as store:
        run = store.create_run(session_id="session-1", occurred_at=NOW)

        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_projection_update
                BEFORE UPDATE ON run_projections
                BEGIN
                    SELECT RAISE(ABORT, 'projection rejected');
                END
                """
            )
            connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="projection rejected"):
            store.transition_run(run.id, RunStatus.RUNNING, occurred_at=NOW)

        assert store.event_count(run.id) == 1
        assert store.get_snapshot(run.id).run.status is RunStatus.PENDING


def test_begin_run_rolls_back_all_initial_evidence_on_projection_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as store:
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_begin_projection_update
                BEFORE UPDATE ON run_projections
                BEGIN
                    SELECT RAISE(ABORT, 'begin projection rejected');
                END
                """
            )
            connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="begin projection rejected"):
            store.begin_run(
                session_id="session-1",
                owner_id="worker-1",
                lease_expires_at=NOW + timedelta(minutes=5),
                input_digest="sha256:input",
                occurred_at=NOW,
            )

        with closing(sqlite3.connect(path)) as connection:
            row = connection.execute("SELECT COUNT(*) FROM run_evidence").fetchone()
            assert row[0] == 0


def test_ledger_rows_are_append_only_at_sql_boundary(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as store:
        run_id = _running_run(store)

    with closing(sqlite3.connect(path)) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only run evidence"):
            connection.execute("UPDATE run_evidence SET sequence = 9 WHERE run_id = ?", (run_id,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only run evidence"):
            connection.execute("DELETE FROM run_evidence WHERE run_id = ?", (run_id,))


def test_second_terminal_transition_is_rejected_and_not_persisted(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        terminal = store.transition_run(run_id, RunStatus.COMPLETED, occurred_at=NOW)

        with pytest.raises(ValueError, match="terminal"):
            store.transition_run(run_id, RunStatus.FAILED, occurred_at=NOW)

        snapshot = store.get_snapshot(run_id)

    assert snapshot.run.status is RunStatus.COMPLETED
    assert snapshot.run.terminal_evidence_id == terminal.id
    assert snapshot.sequence == 3


def test_completed_run_requires_durable_operation_completion(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:turn-1",
            occurred_at=NOW,
        )

        with pytest.raises(ValueError, match="unfinished operations"):
            store.transition_run(run_id, RunStatus.COMPLETED, occurred_at=NOW)

        attempt = store.start_attempt(operation.id, occurred_at=NOW)
        store.dispatch_operation(operation.id, attempt_id=attempt.id, occurred_at=NOW)
        store.finish_attempt(attempt.id, AttemptStatus.SUCCEEDED, occurred_at=NOW)
        store.complete_operation(operation.id, result_digest="sha256:result", occurred_at=NOW)
        store.transition_run(run_id, RunStatus.COMPLETED, occurred_at=NOW)

        assert store.get_snapshot(run_id).run.status is RunStatus.COMPLETED


def test_completed_run_can_contain_a_known_failed_operation(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.TOOL,
            idempotency_key="tool:failed-1",
            occurred_at=NOW,
        )
        attempt = store.start_attempt(operation.id, occurred_at=NOW)
        store.dispatch_operation(operation.id, attempt_id=attempt.id, occurred_at=NOW)
        store.finish_attempt(attempt.id, AttemptStatus.FAILED, occurred_at=NOW)
        store.fail_operation(operation.id, reason_code="tool_result_failed", occurred_at=NOW)

        store.transition_run(run_id, RunStatus.COMPLETED, occurred_at=NOW)
        snapshot = store.get_snapshot(run_id)

    assert snapshot.run.status is RunStatus.COMPLETED
    assert snapshot.operations[operation.id].status is OperationStatus.FAILED
    assert snapshot.operations[operation.id].receipt_recorded is True


def test_terminal_run_rejects_late_child_evidence(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        store.transition_run(run_id, RunStatus.COMPLETED, occurred_at=NOW)
        event_count = store.event_count(run_id)

        with pytest.raises(ValueError, match="terminal run"):
            store.ensure_operation(
                run_id,
                kind=OperationKind.PROVIDER,
                idempotency_key="provider:late",
                occurred_at=NOW,
            )

        assert store.event_count(run_id) == event_count


def test_operation_terminal_event_rejects_a_running_attempt(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:running-attempt",
            occurred_at=NOW,
        )
        store.start_attempt(operation.id, occurred_at=NOW)
        with pytest.raises(ValueError, match="running attempt"):
            store.fail_operation(operation.id, reason_code="provider_error", occurred_at=NOW)


def test_provider_completion_requires_dispatch_and_a_succeeded_attempt(
    tmp_path: Path,
) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:no-dispatch",
            occurred_at=NOW,
        )

        with pytest.raises(ValueError, match="dispatch evidence"):
            store.complete_operation(operation.id, occurred_at=NOW)

        attempt = store.start_attempt(operation.id, occurred_at=NOW)
        store.dispatch_operation(operation.id, attempt_id=attempt.id, occurred_at=NOW)
        store.finish_attempt(attempt.id, AttemptStatus.FAILED, occurred_at=NOW)
        with pytest.raises(ValueError, match="succeeded attempt"):
            store.complete_operation(operation.id, occurred_at=NOW)


def test_succeeded_attempt_requires_its_own_dispatch_receipt(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:success-before-dispatch",
            occurred_at=NOW,
        )
        attempt = store.start_attempt(operation.id, occurred_at=NOW)
        event_count = store.event_count(run_id)

        with pytest.raises(ValueError, match="requires durable dispatch evidence"):
            store.finish_attempt(attempt.id, AttemptStatus.SUCCEEDED, occurred_at=NOW)

        snapshot = store.get_snapshot(run_id)
        assert store.event_count(run_id) == event_count
        assert snapshot.attempts[attempt.id].status is AttemptStatus.RUNNING
        assert snapshot.attempts[attempt.id].dispatch_recorded is False


def test_retry_cannot_borrow_a_previous_attempt_dispatch(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:retry-dispatch",
            occurred_at=NOW,
        )
        first = store.start_attempt(operation.id, occurred_at=NOW)
        store.dispatch_operation(operation.id, attempt_id=first.id, occurred_at=NOW)
        store.finish_attempt(first.id, AttemptStatus.FAILED, occurred_at=NOW)
        second = store.start_attempt(operation.id, occurred_at=NOW)

        with pytest.raises(ValueError, match="requires durable dispatch evidence"):
            store.finish_attempt(second.id, AttemptStatus.SUCCEEDED, occurred_at=NOW)

        snapshot = store.get_snapshot(run_id)
        assert snapshot.operations[operation.id].dispatch_recorded is True
        assert snapshot.attempts[first.id].dispatch_recorded is True
        assert snapshot.attempts[second.id].dispatch_recorded is False
        assert snapshot.attempts[second.id].status is AttemptStatus.RUNNING


def test_partial_provider_attempt_cannot_be_failed_and_retried(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:partial-retry",
            occurred_at=NOW,
        )
        attempt = store.start_attempt(operation.id, occurred_at=NOW)
        store.dispatch_operation(operation.id, attempt_id=attempt.id, occurred_at=NOW)
        store.record_provider_partial_output(
            operation.id,
            attempt_id=attempt.id,
            chunk_digest="sha256:partial",
            occurred_at=NOW,
        )

        with pytest.raises(ValueError, match="unconfirmed effect"):
            store.finish_attempt(attempt.id, AttemptStatus.FAILED, occurred_at=NOW)

        snapshot = store.get_snapshot(run_id)
        assert snapshot.attempts[attempt.id].status is AttemptStatus.RUNNING
        assert snapshot.attempts[attempt.id].partial_output is True


def test_effectful_tool_attempt_cannot_be_failed_and_retried(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.TOOL,
            idempotency_key="tool:effect-retry",
            occurred_at=NOW,
        )
        attempt = store.start_attempt(operation.id, occurred_at=NOW)
        store.dispatch_operation(operation.id, attempt_id=attempt.id, occurred_at=NOW)
        store.record_effect_started(operation.id, attempt_id=attempt.id, occurred_at=NOW)

        with pytest.raises(ValueError, match="unconfirmed effect"):
            store.finish_attempt(attempt.id, AttemptStatus.FAILED, occurred_at=NOW)

        snapshot = store.get_snapshot(run_id)
        assert snapshot.attempts[attempt.id].status is AttemptStatus.RUNNING
        assert snapshot.attempts[attempt.id].effect_started is True


def test_outcome_unknown_attempt_cannot_be_retried_or_downgraded(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:unknown-retry",
            occurred_at=NOW,
        )
        attempt = store.start_attempt(operation.id, occurred_at=NOW)
        store.dispatch_operation(operation.id, attempt_id=attempt.id, occurred_at=NOW)
        store.finish_attempt(attempt.id, AttemptStatus.OUTCOME_UNKNOWN, occurred_at=NOW)

        with pytest.raises(ValueError, match="cannot be retried"):
            store.start_attempt(operation.id, occurred_at=NOW)
        with pytest.raises(ValueError, match="unknown attempt cannot fail"):
            store.fail_operation(operation.id, reason_code="known_failure", occurred_at=NOW)

        store.mark_operation_outcome_unknown(
            operation.id,
            reason_code="provider_outcome_unconfirmed",
            occurred_at=NOW,
        )
        assert store.get_snapshot(run_id).operations[operation.id].status is (
            OperationStatus.OUTCOME_UNKNOWN
        )


def test_terminal_operation_rejects_a_new_attempt(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:terminal",
            occurred_at=NOW,
        )
        store.fail_operation(operation.id, reason_code="preflight_failed", occurred_at=NOW)

        with pytest.raises(ValueError, match="terminal operation"):
            store.start_attempt(operation.id, occurred_at=NOW)


def test_unconfirmed_dispatched_operation_only_allows_outcome_unknown_terminal(
    tmp_path: Path,
) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.TOOL,
            idempotency_key="tool:write-1",
            occurred_at=NOW,
        )
        attempt = store.start_attempt(operation.id, occurred_at=NOW)
        store.dispatch_operation(operation.id, attempt_id=attempt.id, occurred_at=NOW)

        with pytest.raises(ValueError, match="must end as outcome_unknown"):
            store.transition_run(run_id, RunStatus.FAILED, occurred_at=NOW)

        store.finish_attempt(attempt.id, AttemptStatus.OUTCOME_UNKNOWN, occurred_at=NOW)
        store.mark_operation_outcome_unknown(
            operation.id,
            reason_code="receipt_missing",
            occurred_at=NOW,
        )
        store.transition_run(run_id, RunStatus.OUTCOME_UNKNOWN, occurred_at=NOW)

        assert store.get_snapshot(run_id).run.status is RunStatus.OUTCOME_UNKNOWN


def test_stale_terminal_writer_loses_compare_and_swap(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as first, _store(path) as second:
        run_id = _running_run(first)
        expected_sequence = first.get_snapshot(run_id).sequence

        first.transition_run(
            run_id,
            RunStatus.COMPLETED,
            expected_sequence=expected_sequence,
            occurred_at=NOW,
        )
        with pytest.raises(ConcurrencyConflictError):
            second.transition_run(
                run_id,
                RunStatus.FAILED,
                expected_sequence=expected_sequence,
                occurred_at=NOW,
            )

        assert second.get_snapshot(run_id).run.status is RunStatus.COMPLETED
        assert second.event_count(run_id) == 3


def test_finalize_run_atomically_releases_owner_and_writes_terminal(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run, _ = store.begin_run(
            session_id="session-1",
            owner_id="worker-1",
            lease_expires_at=NOW + timedelta(minutes=5),
            occurred_at=NOW,
        )

        terminal = store.finalize_run(
            run.id,
            RunStatus.COMPLETED,
            owner_id="worker-1",
            reason="completed",
            occurred_at=NOW,
        )
        snapshot = store.verify(run.id)

    assert snapshot.run.status is RunStatus.COMPLETED
    assert snapshot.run.owner_id is None
    assert snapshot.run.lease_expires_at is None
    assert snapshot.run.terminal_evidence_id == terminal.id


def test_finalize_run_rolls_back_lease_release_when_terminal_write_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as store:
        run, _ = store.begin_run(
            session_id="session-1",
            owner_id="worker-1",
            lease_expires_at=NOW + timedelta(minutes=5),
            occurred_at=NOW,
        )
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_terminal_projection_update
                BEFORE UPDATE ON run_projections
                WHEN NEW.sequence = 5
                BEGIN
                    SELECT RAISE(ABORT, 'terminal projection rejected');
                END
                """
            )
            connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="terminal projection rejected"):
            store.finalize_run(
                run.id,
                RunStatus.COMPLETED,
                owner_id="worker-1",
                occurred_at=NOW,
            )

        snapshot = store.get_snapshot(run.id)
        assert snapshot.sequence == 3
        assert snapshot.run.status is RunStatus.RUNNING
        assert snapshot.run.owner_id == "worker-1"
        assert store.event_count(run.id) == 3


def test_stale_owner_cannot_enter_an_owned_write_transaction(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run, _ = store.begin_run(
            session_id="session-1",
            owner_id="worker-1",
            lease_expires_at=NOW + timedelta(minutes=1),
            occurred_at=NOW,
        )
        takeover_at = NOW + timedelta(minutes=2)
        store.acquire_lease(
            run.id,
            owner_id="worker-2",
            lease_expires_at=takeover_at + timedelta(minutes=5),
            occurred_at=takeover_at,
        )

        with pytest.raises(ConcurrencyConflictError, match="not leased by worker-1"):
            with store.owned_transaction(
                run.id,
                owner_id="worker-1",
                lease_expires_at=takeover_at + timedelta(minutes=5),
                occurred_at=takeover_at,
            ):
                store.record_evidence(
                    run.id,
                    EvidenceType.USAGE_OBSERVED,
                    entity_id=run.id,
                    payload={"llm_calls": 1},
                    occurred_at=takeover_at,
                )


def test_operation_idempotency_key_returns_same_logical_operation(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        turn = store.create_turn(run_id, input_digest="sha256:input", occurred_at=NOW)
        first = store.ensure_operation(
            run_id,
            turn_id=turn.id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:turn-1",
            occurred_at=NOW,
        )
        second = store.ensure_operation(
            run_id,
            turn_id=turn.id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:turn-1",
            occurred_at=NOW + timedelta(seconds=1),
        )

        assert first == second
        assert len(store.get_snapshot(run_id).operations) == 1


def test_operation_idempotency_key_rejects_conflicting_shape(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="logical-key",
            occurred_at=NOW,
        )

        with pytest.raises(IdempotencyConflictError):
            store.ensure_operation(
                run_id,
                kind=OperationKind.TOOL,
                idempotency_key="logical-key",
                occurred_at=NOW,
            )


def test_attempt_numbers_are_derived_from_durable_operation_history(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        operation = store.ensure_operation(
            run_id,
            kind=OperationKind.PROVIDER,
            idempotency_key="provider:turn-1",
            occurred_at=NOW,
        )
        first = store.start_attempt(operation.id, occurred_at=NOW)
        store.finish_attempt(first.id, AttemptStatus.FAILED, occurred_at=NOW)
        second = store.start_attempt(operation.id, occurred_at=NOW)

        assert first.number == 1
        assert second.number == 2
        assert second.operation_id == first.operation_id


def test_replay_matches_transactional_projection_and_is_deterministic(tmp_path: Path) -> None:
    with _store(tmp_path / "runs.sqlite3") as store:
        run_id = _running_run(store)
        store.create_turn(run_id, input_digest="sha256:input", occurred_at=NOW)
        online = store.get_snapshot(run_id)

        first_replay = store.replay(run_id)
        second_replay = store.replay(run_id)

    assert first_replay == online
    assert second_replay == first_replay


def test_projection_can_be_deleted_and_rebuilt_from_authoritative_log(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as store:
        run_id = _running_run(store)
        expected = store.get_snapshot(run_id)

    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DELETE FROM run_projections WHERE run_id = ?", (run_id,))
        connection.commit()

    with _store(path) as store:
        with pytest.raises(KeyError):
            store.get_snapshot(run_id)
        rebuilt = store.rebuild_projection(run_id)

    assert rebuilt == expected


def test_verify_detects_tampered_evidence_even_if_projection_still_exists(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as store:
        run_id = _running_run(store)

    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DROP TRIGGER run_evidence_no_update")
        raw = connection.execute(
            "SELECT evidence_json FROM run_evidence WHERE run_id = ? AND sequence = 1",
            (run_id,),
        ).fetchone()[0]
        document = json.loads(raw)
        document["payload"]["session_id"] = "tampered-session"
        connection.execute(
            "UPDATE run_evidence SET evidence_json = ? WHERE run_id = ? AND sequence = 1",
            (json.dumps(document), run_id),
        )
        connection.commit()

    with _store(path) as store:
        with pytest.raises(IntegrityVerificationError, match="invalid payload digest"):
            store.verify(run_id)


def test_verify_detects_materialized_projection_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    with _store(path) as store:
        run_id = _running_run(store)

    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT snapshot_json FROM run_projections WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        snapshot = json.loads(row)
        snapshot["run"]["metadata"]["forged"] = True
        serialized = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        connection.execute(
            """
            UPDATE run_projections
            SET snapshot_json = ?, snapshot_digest = ?
            WHERE run_id = ?
            """,
            (serialized, content_digest(snapshot), run_id),
        )
        connection.commit()

    with _store(path) as store:
        with pytest.raises(IntegrityVerificationError, match="does not match replay"):
            store.verify(run_id)
