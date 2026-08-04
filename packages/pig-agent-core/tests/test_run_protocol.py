"""Versioned run-integrity protocol and transition-kernel contracts."""

from datetime import datetime, timezone

import pytest
from pig_agent_core.run_integrity import (
    Attempt,
    AttemptStatus,
    Evidence,
    EvidenceType,
    Operation,
    OperationKind,
    OperationStatus,
    Run,
    RunStatus,
    Turn,
    apply_evidence,
    new_attempt_id,
    new_evidence_id,
    new_operation_id,
    new_run_id,
    new_turn_id,
    transition_run,
)

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _run(status: RunStatus = RunStatus.PENDING) -> Run:
    return Run(
        id=new_run_id(),
        session_id="session-1",
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RunStatus.PENDING, RunStatus.RUNNING),
        (RunStatus.PENDING, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.WAITING),
        (RunStatus.RUNNING, RunStatus.COMPLETED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.OUTCOME_UNKNOWN),
        (RunStatus.WAITING, RunStatus.RUNNING),
        (RunStatus.WAITING, RunStatus.CANCELLED),
        (RunStatus.WAITING, RunStatus.OUTCOME_UNKNOWN),
    ],
)
def test_transition_kernel_accepts_only_declared_edges(
    source: RunStatus,
    target: RunStatus,
) -> None:
    transitioned = transition_run(_run(source), target, occurred_at=NOW)

    assert transitioned.status is target


@pytest.mark.parametrize("terminal", sorted(RunStatus.terminal(), key=str))
@pytest.mark.parametrize("target", list(RunStatus))
def test_terminal_run_rejects_every_followup_transition(
    terminal: RunStatus,
    target: RunStatus,
) -> None:
    with pytest.raises(ValueError, match="terminal"):
        transition_run(_run(terminal), target, occurred_at=NOW)


def test_invalid_transition_does_not_mutate_original_run() -> None:
    run = _run(RunStatus.PENDING)

    with pytest.raises(ValueError, match="Invalid run transition"):
        transition_run(run, RunStatus.COMPLETED, occurred_at=NOW)

    assert run.status is RunStatus.PENDING


def test_versioned_entity_ids_and_schemas_are_explicit() -> None:
    run = _run()
    turn = Turn(
        id=new_turn_id(),
        run_id=run.id,
        ordinal=1,
        input_digest="sha256:input",
        created_at=NOW,
    )
    operation = Operation(
        id=new_operation_id(),
        run_id=run.id,
        turn_id=turn.id,
        ordinal=1,
        kind=OperationKind.PROVIDER,
        idempotency_key="provider:turn-1",
        created_at=NOW,
        updated_at=NOW,
    )
    attempt = Attempt(
        id=new_attempt_id(),
        run_id=run.id,
        operation_id=operation.id,
        number=1,
        status=AttemptStatus.RUNNING,
        started_at=NOW,
    )

    assert run.schema_version == 1
    assert turn.schema_version == 1
    assert operation.schema_version == 1
    assert attempt.schema_version == 1
    assert run.id.startswith("run_v1_")
    assert turn.id.startswith("turn_v1_")
    assert operation.id.startswith("op_v1_")
    assert attempt.id.startswith("attempt_v1_")


def test_retry_preserves_operation_identity_and_increments_attempt_number() -> None:
    run = _run(RunStatus.RUNNING)
    operation = Operation(
        id=new_operation_id(),
        run_id=run.id,
        ordinal=1,
        kind=OperationKind.PROVIDER,
        idempotency_key="provider:stable",
        created_at=NOW,
        updated_at=NOW,
    )

    first = Attempt(
        id=new_attempt_id(),
        run_id=run.id,
        operation_id=operation.id,
        number=1,
        status=AttemptStatus.FAILED,
        started_at=NOW,
        finished_at=NOW,
    )
    second = Attempt(
        id=new_attempt_id(),
        run_id=run.id,
        operation_id=operation.id,
        number=first.number + 1,
        status=AttemptStatus.RUNNING,
        started_at=NOW,
    )

    assert second.operation_id == first.operation_id
    assert operation.idempotency_key == "provider:stable"
    assert second.number == 2


def test_evidence_digest_is_canonical_and_payload_sensitive() -> None:
    evidence_id = new_evidence_id()
    run_id = new_run_id()

    def create(payload: dict[str, int]) -> Evidence:
        return Evidence.create(
            id=evidence_id,
            run_id=run_id,
            sequence=1,
            type=EvidenceType.RUN_CREATED,
            entity_id="entity-1",
            occurred_at=NOW,
            payload=payload,
            previous_digest=None,
        )

    first = create({"b": 2, "a": 1})
    reordered = create({"a": 1, "b": 2})
    changed = create({"a": 1, "b": 3})

    assert first.payload_digest == reordered.payload_digest
    assert first.digest == reordered.digest
    assert changed.payload_digest != first.payload_digest
    assert changed.digest != first.digest


def test_evidence_chain_rejects_wrong_previous_digest() -> None:
    run_id = new_run_id()
    created = Evidence.create(
        id=new_evidence_id(),
        run_id=run_id,
        sequence=1,
        type=EvidenceType.RUN_CREATED,
        entity_id=run_id,
        occurred_at=NOW,
        payload={"session_id": "session-1"},
        previous_digest=None,
    )
    started = Evidence.create(
        id=new_evidence_id(),
        run_id=run_id,
        sequence=2,
        type=EvidenceType.RUN_TRANSITIONED,
        entity_id=run_id,
        occurred_at=NOW,
        payload={"status": RunStatus.RUNNING.value},
        previous_digest="sha256:wrong",
    )

    snapshot = apply_evidence(None, created)
    with pytest.raises(ValueError, match="previous digest"):
        apply_evidence(snapshot, started)


def test_operation_status_is_not_a_second_run_terminal_authority() -> None:
    assert OperationStatus.COMPLETED.is_terminal
    assert OperationStatus.OUTCOME_UNKNOWN.is_terminal
    assert not OperationStatus.PENDING.is_terminal
