"""Pure state-transition and projection kernel for run evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import (
    Attempt,
    AttemptStatus,
    Evidence,
    EvidenceType,
    Operation,
    OperationKind,
    OperationStatus,
    Run,
    RunSnapshot,
    RunStatus,
    Turn,
)

_ALLOWED_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.OUTCOME_UNKNOWN,
        }
    ),
    RunStatus.WAITING: frozenset(
        {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.OUTCOME_UNKNOWN}
    ),
}


def transition_run(run: Run, target: RunStatus, *, occurred_at: datetime) -> Run:
    """Apply one declared lifecycle edge without mutating the source run."""
    if run.status.is_terminal:
        raise ValueError(f"Run {run.id} is already terminal ({run.status.value})")
    if target not in _ALLOWED_RUN_TRANSITIONS.get(run.status, frozenset()):
        raise ValueError(f"Invalid run transition: {run.status.value} -> {target.value}")
    return run.model_copy(update={"status": target, "updated_at": occurred_at})


def _datetime(payload: dict[str, Any], key: str, fallback: datetime) -> datetime:
    value = payload.get(key)
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise ValueError(f"{key} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{key} must include a timezone")
    return parsed


def _create_snapshot(evidence: Evidence) -> RunSnapshot:
    if evidence.type is not EvidenceType.RUN_CREATED:
        raise ValueError("The first run evidence must be run_created")
    if evidence.sequence != 1 or evidence.previous_digest is not None:
        raise ValueError("The first run evidence must start sequence 1 without a previous digest")
    session_id = evidence.payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("run_created evidence requires session_id")
    run = Run(
        id=evidence.run_id,
        session_id=session_id,
        created_at=_datetime(evidence.payload, "created_at", evidence.occurred_at),
        updated_at=evidence.occurred_at,
        owner_id=evidence.payload.get("owner_id"),
        lease_expires_at=(
            _datetime(evidence.payload, "lease_expires_at", evidence.occurred_at)
            if evidence.payload.get("lease_expires_at") is not None
            else None
        ),
        revision=1,
        metadata=dict(evidence.payload.get("metadata", {})),
    )
    return RunSnapshot(run=run, sequence=1, last_digest=evidence.digest)


def _updated_operation(
    snapshot: RunSnapshot,
    evidence: Evidence,
    **updates: Any,
) -> dict[str, Operation]:
    operation = snapshot.operations.get(evidence.entity_id)
    if operation is None:
        raise ValueError(f"Unknown operation {evidence.entity_id}")
    if operation.status.is_terminal:
        raise ValueError(f"Operation {operation.id} is already terminal")
    operations = dict(snapshot.operations)
    operations[operation.id] = operation.model_copy(
        update={"updated_at": evidence.occurred_at, **updates}
    )
    return operations


def apply_evidence(snapshot: RunSnapshot | None, evidence: Evidence) -> RunSnapshot:
    """Validate and apply one fact to a deterministic run projection."""
    evidence.verify()
    if snapshot is None:
        return _create_snapshot(evidence)
    if evidence.run_id != snapshot.run.id:
        raise ValueError("Evidence belongs to a different run")
    if evidence.sequence != snapshot.sequence + 1:
        raise ValueError(
            f"Evidence sequence gap: expected {snapshot.sequence + 1}, got {evidence.sequence}"
        )
    if evidence.previous_digest != snapshot.last_digest:
        raise ValueError("Evidence previous digest does not match the run hash chain")

    run = snapshot.run
    turns = dict(snapshot.turns)
    operations = dict(snapshot.operations)
    attempts = dict(snapshot.attempts)
    payload = evidence.payload

    if evidence.type is EvidenceType.RUN_CREATED:
        raise ValueError("A run can only have one run_created event")
    if run.status.is_terminal:
        raise ValueError(f"Cannot append evidence to terminal run {run.id}")
    if evidence.type is EvidenceType.RUN_TRANSITIONED:
        target = RunStatus(str(payload["status"]))
        if target is RunStatus.COMPLETED and any(
            not item.status.is_terminal or not item.receipt_recorded for item in operations.values()
        ):
            raise ValueError("A completed run cannot contain unfinished operations or receipts")
        uncertain = [
            item
            for item in operations.values()
            if item.status is OperationStatus.OUTCOME_UNKNOWN
            or (item.dispatch_recorded and not item.receipt_recorded)
        ]
        if uncertain and target.is_terminal and target is not RunStatus.OUTCOME_UNKNOWN:
            raise ValueError("A run with unconfirmed operation effects must end as outcome_unknown")
        if target.is_terminal and any(not item.status.is_terminal for item in operations.values()):
            raise ValueError("A terminal run cannot contain nonterminal operations")
        if target.is_terminal and any(not item.status.is_terminal for item in attempts.values()):
            raise ValueError("A terminal run cannot contain running attempts")
        run = transition_run(run, target, occurred_at=evidence.occurred_at)
        if target.is_terminal:
            run = run.model_copy(update={"terminal_evidence_id": evidence.id})
    elif evidence.type is EvidenceType.LEASE_ACQUIRED:
        if run.status.is_terminal:
            raise ValueError("Cannot acquire a lease for a terminal run")
        owner_id = payload.get("owner_id")
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("lease_acquired requires owner_id")
        expires_at = _datetime(payload, "lease_expires_at", evidence.occurred_at)
        run = run.model_copy(
            update={
                "owner_id": owner_id,
                "lease_expires_at": expires_at,
                "updated_at": evidence.occurred_at,
            }
        )
    elif evidence.type in {EvidenceType.LEASE_RELEASED, EvidenceType.OWNERSHIP_EXPIRED}:
        run = run.model_copy(
            update={
                "owner_id": None,
                "lease_expires_at": None,
                "updated_at": evidence.occurred_at,
            }
        )
    elif evidence.type is EvidenceType.TURN_CREATED:
        turn = Turn.model_validate(payload)
        if turn.id != evidence.entity_id or turn.run_id != run.id:
            raise ValueError("turn_created identity does not match its evidence envelope")
        if turn.id in turns:
            raise ValueError(f"Duplicate turn {turn.id}")
        if turn.ordinal != len(turns) + 1:
            raise ValueError("Turn ordinals must be contiguous and 1-based")
        turns[turn.id] = turn
    elif evidence.type is EvidenceType.OPERATION_CREATED:
        operation = Operation.model_validate(payload)
        if operation.id != evidence.entity_id or operation.run_id != run.id:
            raise ValueError("operation_created identity does not match its evidence envelope")
        if operation.id in operations:
            raise ValueError(f"Duplicate operation {operation.id}")
        if operation.turn_id is not None and operation.turn_id not in turns:
            raise ValueError(f"Unknown turn {operation.turn_id}")
        if any(item.idempotency_key == operation.idempotency_key for item in operations.values()):
            raise ValueError(f"Duplicate operation idempotency key {operation.idempotency_key!r}")
        if operation.ordinal != len(operations) + 1:
            raise ValueError("Operation ordinals must be contiguous and 1-based")
        operations[operation.id] = operation
    elif evidence.type is EvidenceType.OPERATION_DISPATCHED:
        attempt_id = payload.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError("operation_dispatched requires attempt_id")
        dispatch_attempt = attempts.get(attempt_id)
        if dispatch_attempt is None:
            raise ValueError(f"Unknown attempt {attempt_id}")
        if dispatch_attempt.operation_id != evidence.entity_id:
            raise ValueError("Dispatch attempt does not belong to the operation")
        if dispatch_attempt.status is not AttemptStatus.RUNNING:
            raise ValueError("Only a running attempt can be dispatched")
        if dispatch_attempt.dispatch_recorded:
            raise ValueError(f"Attempt {attempt_id} is already dispatched")
        attempts[attempt_id] = dispatch_attempt.model_copy(update={"dispatch_recorded": True})
        operations = _updated_operation(
            snapshot,
            evidence,
            status=OperationStatus.RUNNING,
            dispatch_recorded=True,
        )
    elif evidence.type is EvidenceType.OPERATION_WAITING:
        operations = _updated_operation(
            snapshot,
            evidence,
            status=OperationStatus.WAITING,
        )
    elif evidence.type is EvidenceType.OPERATION_EFFECT_STARTED:
        attempt_id = payload.get("attempt_id")
        effect_attempt = attempts.get(attempt_id) if isinstance(attempt_id, str) else None
        if (
            effect_attempt is None
            or effect_attempt.operation_id != evidence.entity_id
            or effect_attempt.status is not AttemptStatus.RUNNING
            or not effect_attempt.dispatch_recorded
        ):
            raise ValueError("An effect requires its running dispatched attempt")
        if effect_attempt.effect_started:
            raise ValueError(f"Attempt {effect_attempt.id} already crossed its effect boundary")
        attempts[effect_attempt.id] = effect_attempt.model_copy(update={"effect_started": True})
        effect_operation = operations.get(evidence.entity_id)
        if effect_operation is None or not effect_operation.dispatch_recorded:
            raise ValueError("An effect cannot start before durable dispatch evidence")
        operations = _updated_operation(snapshot, evidence, effect_started=True)
    elif evidence.type is EvidenceType.PROVIDER_PARTIAL_OUTPUT:
        attempt_id = payload.get("attempt_id")
        partial_attempt = attempts.get(attempt_id) if isinstance(attempt_id, str) else None
        provider_operation = operations.get(evidence.entity_id)
        if (
            provider_operation is None
            or provider_operation.kind is not OperationKind.PROVIDER
            or not provider_operation.dispatch_recorded
            or partial_attempt is None
            or partial_attempt.operation_id != evidence.entity_id
            or partial_attempt.status is not AttemptStatus.RUNNING
            or not partial_attempt.dispatch_recorded
        ):
            raise ValueError("Partial output requires its running dispatched provider attempt")
        attempts[partial_attempt.id] = partial_attempt.model_copy(update={"partial_output": True})
        operations = _updated_operation(snapshot, evidence, partial_output=True)
    elif evidence.type is EvidenceType.OPERATION_COMPLETED:
        completing_operation = operations.get(evidence.entity_id)
        if completing_operation is None:
            raise ValueError(f"Unknown operation {evidence.entity_id}")
        operation_attempts = [
            item for item in attempts.values() if item.operation_id == evidence.entity_id
        ]
        if any(not item.status.is_terminal for item in operation_attempts):
            raise ValueError("An operation cannot complete with a running attempt")
        if any(item.status is AttemptStatus.OUTCOME_UNKNOWN for item in operation_attempts):
            raise ValueError("An operation with an unknown attempt cannot complete")
        if completing_operation.kind in {OperationKind.PROVIDER, OperationKind.TOOL}:
            if not completing_operation.dispatch_recorded:
                raise ValueError("Provider and tool completion requires durable dispatch evidence")
            if not any(
                item.status is AttemptStatus.SUCCEEDED and item.dispatch_recorded
                for item in operation_attempts
            ):
                raise ValueError(
                    "Provider and tool completion requires a dispatched succeeded attempt"
                )
        operations = _updated_operation(
            snapshot,
            evidence,
            status=OperationStatus.COMPLETED,
            receipt_recorded=True,
        )
    elif evidence.type is EvidenceType.OPERATION_FAILED:
        operation_attempts = [
            item for item in attempts.values() if item.operation_id == evidence.entity_id
        ]
        if any(not item.status.is_terminal for item in operation_attempts):
            raise ValueError("An operation cannot fail with a running attempt")
        if any(item.status is AttemptStatus.OUTCOME_UNKNOWN for item in operation_attempts):
            raise ValueError("An operation with an unknown attempt cannot fail")
        operations = _updated_operation(
            snapshot,
            evidence,
            status=OperationStatus.FAILED,
            receipt_recorded=True,
        )
    elif evidence.type is EvidenceType.OPERATION_CANCELLED:
        operation_attempts = [
            item for item in attempts.values() if item.operation_id == evidence.entity_id
        ]
        if any(not item.status.is_terminal for item in operation_attempts):
            raise ValueError("An operation cannot cancel with a running attempt")
        if any(item.status is AttemptStatus.OUTCOME_UNKNOWN for item in operation_attempts):
            raise ValueError("An operation with an unknown attempt cannot cancel")
        operations = _updated_operation(
            snapshot,
            evidence,
            status=OperationStatus.CANCELLED,
            receipt_recorded=True,
        )
    elif evidence.type is EvidenceType.OPERATION_OUTCOME_UNKNOWN:
        if any(
            item.operation_id == evidence.entity_id and not item.status.is_terminal
            for item in attempts.values()
        ):
            raise ValueError("An operation cannot become outcome_unknown with a running attempt")
        operations = _updated_operation(
            snapshot,
            evidence,
            status=OperationStatus.OUTCOME_UNKNOWN,
        )
    elif evidence.type is EvidenceType.ATTEMPT_STARTED:
        attempt = Attempt.model_validate(payload)
        if attempt.id != evidence.entity_id or attempt.run_id != run.id:
            raise ValueError("attempt_started identity does not match its evidence envelope")
        if attempt.operation_id not in operations:
            raise ValueError(f"Unknown operation {attempt.operation_id}")
        if operations[attempt.operation_id].status.is_terminal:
            raise ValueError("Cannot start an attempt for a terminal operation")
        if attempt.status is not AttemptStatus.RUNNING or attempt.finished_at is not None:
            raise ValueError("A new attempt must start in running state")
        operation_attempts = [
            item for item in attempts.values() if item.operation_id == attempt.operation_id
        ]
        if any(not item.status.is_terminal for item in operation_attempts):
            raise ValueError("The previous attempt must finish before retrying")
        if any(
            item.status in {AttemptStatus.SUCCEEDED, AttemptStatus.OUTCOME_UNKNOWN}
            for item in operation_attempts
        ):
            raise ValueError("A succeeded or outcome_unknown attempt cannot be retried")
        if attempt.number != len(operation_attempts) + 1:
            raise ValueError("Attempt numbers must be contiguous and 1-based")
        attempts[attempt.id] = attempt
    elif evidence.type is EvidenceType.ATTEMPT_FINISHED:
        finishing_attempt = attempts.get(evidence.entity_id)
        if finishing_attempt is None:
            raise ValueError(f"Unknown attempt {evidence.entity_id}")
        if finishing_attempt.status.is_terminal:
            raise ValueError(f"Attempt {finishing_attempt.id} is already terminal")
        status = AttemptStatus(str(payload["status"]))
        if not status.is_terminal:
            raise ValueError("attempt_finished requires a terminal attempt status")
        if status in {AttemptStatus.SUCCEEDED, AttemptStatus.OUTCOME_UNKNOWN} and not (
            finishing_attempt.dispatch_recorded
        ):
            raise ValueError(f"Attempt status {status.value} requires durable dispatch evidence")
        if status in {AttemptStatus.FAILED, AttemptStatus.CANCELLED} and (
            finishing_attempt.effect_started or finishing_attempt.partial_output
        ):
            raise ValueError("An attempt with an unconfirmed effect cannot become known terminal")
        attempts[finishing_attempt.id] = finishing_attempt.model_copy(
            update={
                "status": status,
                "finished_at": evidence.occurred_at,
                "metadata": {
                    **finishing_attempt.metadata,
                    **dict(payload.get("metadata", {})),
                },
            }
        )

    run = run.model_copy(update={"revision": evidence.sequence, "updated_at": evidence.occurred_at})
    return RunSnapshot(
        run=run,
        sequence=evidence.sequence,
        last_digest=evidence.digest,
        turns=turns,
        operations=operations,
        attempts=attempts,
    )


def replay(evidence: list[Evidence]) -> RunSnapshot:
    """Rebuild a run projection from a complete ordered event stream."""
    if not evidence:
        raise ValueError("Cannot replay an empty evidence stream")
    snapshot: RunSnapshot | None = None
    for item in evidence:
        snapshot = apply_evidence(snapshot, item)
    if snapshot is None:  # pragma: no cover - guarded by the non-empty check
        raise AssertionError("replay did not produce a snapshot")
    return snapshot
