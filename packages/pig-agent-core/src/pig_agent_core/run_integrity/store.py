"""Transactional SQLite authority for append-only run evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .kernel import apply_evidence, replay
from .models import (
    SCHEMA_VERSION,
    Attempt,
    AttemptStatus,
    Evidence,
    EvidenceType,
    Operation,
    OperationKind,
    Run,
    RunSnapshot,
    RunStatus,
    Turn,
    canonical_json,
    content_digest,
    new_attempt_id,
    new_evidence_id,
    new_operation_id,
    new_run_id,
    new_turn_id,
)


class RunStoreError(RuntimeError):
    """Base class for durable run-store failures."""


class ConcurrencyConflictError(RunStoreError):
    """Raised when a caller's expected sequence is stale."""


class IdempotencyConflictError(RunStoreError):
    """Raised when a stable key is reused for a different operation."""


class IntegrityVerificationError(RunStoreError):
    """Raised when evidence, its hash chain, or a projection was modified."""


_OBSERVATION_TYPES = frozenset(
    {
        EvidenceType.TURN_OUTCOME_OBSERVED,
        EvidenceType.RETRY_OBSERVED,
        EvidenceType.USAGE_OBSERVED,
        EvidenceType.COMPACTION_OBSERVED,
        EvidenceType.PERMISSION_DENIAL_OBSERVED,
        EvidenceType.TOOL_AUDIT_OBSERVED,
        EvidenceType.RECOVERY_CLASSIFIED,
    }
)


def _occurred_at(value: datetime | None) -> datetime:
    occurred_at = value or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("Run evidence timestamps must include a timezone")
    return occurred_at


class SQLiteRunStore:
    """Dependency-light local Run authority backed by stdlib SQLite.

    ``run_evidence`` is the source of truth. ``run_projections`` is a
    transactionally maintained, disposable read model that can be rebuilt from
    the evidence stream at any time.
    """

    def __init__(self, path: str | Path, *, timeout: float = 5.0) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.path,
            timeout=timeout,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute(f"PRAGMA busy_timeout = {max(0, int(timeout * 1000))}")
        self._initialize_schema()
        self._closed = False

    def _initialize_schema(self) -> None:
        self._connection.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS run_evidence (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence >= 1),
                schema_version INTEGER NOT NULL CHECK (schema_version = {SCHEMA_VERSION}),
                evidence_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                digest TEXT NOT NULL,
                UNIQUE (run_id, sequence)
            );

            CREATE INDEX IF NOT EXISTS run_evidence_run_sequence
            ON run_evidence (run_id, sequence);

            CREATE INDEX IF NOT EXISTS run_evidence_entity
            ON run_evidence (entity_id, evidence_type);

            CREATE TABLE IF NOT EXISTS run_projections (
                run_id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL CHECK (sequence >= 1),
                snapshot_json TEXT NOT NULL,
                snapshot_digest TEXT NOT NULL
            );

            CREATE TRIGGER IF NOT EXISTS run_evidence_no_update
            BEFORE UPDATE ON run_evidence
            BEGIN
                SELECT RAISE(ABORT, 'append-only run evidence');
            END;

            CREATE TRIGGER IF NOT EXISTS run_evidence_no_delete
            BEFORE DELETE ON run_evidence
            BEGIN
                SELECT RAISE(ABORT, 'append-only run evidence');
            END;
            """
        )

    def close(self) -> None:
        """Close the SQLite connection."""
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> SQLiteRunStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def _snapshot_locked(self, run_id: str) -> RunSnapshot | None:
        row = self._connection.execute(
            "SELECT snapshot_json, snapshot_digest FROM run_projections WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        snapshot = RunSnapshot.model_validate_json(str(row["snapshot_json"]))
        actual_digest = content_digest(snapshot.model_dump(mode="json"))
        if actual_digest != row["snapshot_digest"]:
            raise IntegrityVerificationError(
                f"Materialized projection for {run_id} has an invalid digest"
            )
        return snapshot

    def _write_projection_locked(self, snapshot: RunSnapshot) -> None:
        value = snapshot.model_dump(mode="json")
        serialized = canonical_json(value)
        digest = content_digest(value)
        self._connection.execute(
            """
            INSERT INTO run_projections (run_id, sequence, snapshot_json, snapshot_digest)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                sequence = excluded.sequence,
                snapshot_json = excluded.snapshot_json,
                snapshot_digest = excluded.snapshot_digest
            """,
            (snapshot.run.id, snapshot.sequence, serialized, digest),
        )

    def _append_locked(
        self,
        snapshot: RunSnapshot | None,
        *,
        run_id: str,
        evidence_type: EvidenceType,
        entity_id: str,
        payload: dict[str, Any],
        occurred_at: datetime,
        expected_sequence: int | None = None,
        evidence_id: str | None = None,
    ) -> tuple[Evidence, RunSnapshot]:
        current_sequence = snapshot.sequence if snapshot is not None else 0
        if expected_sequence is not None and current_sequence != expected_sequence:
            raise ConcurrencyConflictError(
                f"Run {run_id} is at sequence {current_sequence}, expected {expected_sequence}"
            )
        evidence = Evidence.create(
            id=evidence_id or new_evidence_id(),
            run_id=run_id,
            sequence=current_sequence + 1,
            type=evidence_type,
            entity_id=entity_id,
            occurred_at=occurred_at,
            payload=payload,
            previous_digest=snapshot.last_digest if snapshot is not None else None,
        )
        updated = apply_evidence(snapshot, evidence)
        self._connection.execute(
            """
            INSERT INTO run_evidence (
                event_id,
                run_id,
                sequence,
                schema_version,
                evidence_type,
                entity_id,
                evidence_json,
                digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence.id,
                evidence.run_id,
                evidence.sequence,
                evidence.schema_version,
                evidence.type.value,
                evidence.entity_id,
                canonical_json(evidence.model_dump(mode="json")),
                evidence.digest,
            ),
        )
        self._write_projection_locked(updated)
        return evidence, updated

    def _append(
        self,
        run_id: str,
        evidence_type: EvidenceType,
        *,
        entity_id: str,
        payload: dict[str, Any],
        occurred_at: datetime | None,
        expected_sequence: int | None = None,
        evidence_id: str | None = None,
    ) -> tuple[Evidence, RunSnapshot]:
        timestamp = _occurred_at(occurred_at)
        with self._transaction():
            snapshot = self._snapshot_locked(run_id)
            if snapshot is None and evidence_type is not EvidenceType.RUN_CREATED:
                raise KeyError(f"Unknown run {run_id}")
            return self._append_locked(
                snapshot,
                run_id=run_id,
                evidence_type=evidence_type,
                entity_id=entity_id,
                payload=payload,
                occurred_at=timestamp,
                expected_sequence=expected_sequence,
                evidence_id=evidence_id,
            )

    def create_run(
        self,
        *,
        session_id: str,
        metadata: dict[str, Any] | None = None,
        owner_id: str | None = None,
        lease_expires_at: datetime | None = None,
        run_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> Run:
        """Create a pending run with optional initial ownership."""
        timestamp = _occurred_at(occurred_at)
        resolved_run_id = run_id or new_run_id()
        if (owner_id is None) != (lease_expires_at is None):
            raise ValueError("owner_id and lease_expires_at must be provided together")
        if lease_expires_at is not None:
            _occurred_at(lease_expires_at)
        payload: dict[str, Any] = {
            "session_id": session_id,
            "created_at": timestamp.isoformat(),
            "metadata": dict(metadata or {}),
        }
        if owner_id is not None and lease_expires_at is not None:
            payload.update(
                {
                    "owner_id": owner_id,
                    "lease_expires_at": lease_expires_at.isoformat(),
                }
            )
        _, snapshot = self._append(
            resolved_run_id,
            EvidenceType.RUN_CREATED,
            entity_id=resolved_run_id,
            payload=payload,
            occurred_at=timestamp,
        )
        return snapshot.run

    def transition_run(
        self,
        run_id: str,
        target: RunStatus,
        *,
        reason: str | None = None,
        expected_sequence: int | None = None,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Commit one validated run-state transition."""
        payload = {"status": target.value}
        if reason is not None:
            payload["reason"] = reason
        evidence, _ = self._append(
            run_id,
            EvidenceType.RUN_TRANSITIONED,
            entity_id=run_id,
            payload=payload,
            occurred_at=occurred_at,
            expected_sequence=expected_sequence,
        )
        return evidence

    def acquire_lease(
        self,
        run_id: str,
        *,
        owner_id: str,
        lease_expires_at: datetime,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Acquire or renew time-bounded ownership for a nonterminal run."""
        timestamp = _occurred_at(occurred_at)
        expires_at = _occurred_at(lease_expires_at)
        if expires_at <= timestamp:
            raise ValueError("A run lease must expire after it is acquired")
        with self._transaction():
            snapshot = self._snapshot_locked(run_id)
            if snapshot is None:
                raise KeyError(f"Unknown run {run_id}")
            run = snapshot.run
            if (
                run.owner_id is not None
                and run.owner_id != owner_id
                and run.lease_expires_at is not None
                and run.lease_expires_at > timestamp
            ):
                raise ConcurrencyConflictError(
                    f"Run {run_id} is leased by {run.owner_id} until "
                    f"{run.lease_expires_at.isoformat()}"
                )
            evidence, _ = self._append_locked(
                snapshot,
                run_id=run_id,
                evidence_type=EvidenceType.LEASE_ACQUIRED,
                entity_id=run_id,
                payload={
                    "owner_id": owner_id,
                    "lease_expires_at": expires_at.isoformat(),
                },
                occurred_at=timestamp,
            )
            return evidence

    def release_lease(
        self,
        run_id: str,
        *,
        owner_id: str,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Release only the matching run owner's lease."""
        timestamp = _occurred_at(occurred_at)
        with self._transaction():
            snapshot = self._snapshot_locked(run_id)
            if snapshot is None:
                raise KeyError(f"Unknown run {run_id}")
            if snapshot.run.owner_id != owner_id:
                raise ConcurrencyConflictError(f"Run {run_id} is not leased by {owner_id}")
            evidence, _ = self._append_locked(
                snapshot,
                run_id=run_id,
                evidence_type=EvidenceType.LEASE_RELEASED,
                entity_id=run_id,
                payload={"owner_id": owner_id},
                occurred_at=timestamp,
            )
            return evidence

    def create_turn(
        self,
        run_id: str,
        *,
        input_digest: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> Turn:
        """Create the next 1-based turn in a run."""
        timestamp = _occurred_at(occurred_at)
        with self._transaction():
            snapshot = self._snapshot_locked(run_id)
            if snapshot is None:
                raise KeyError(f"Unknown run {run_id}")
            turn = Turn(
                id=new_turn_id(),
                run_id=run_id,
                ordinal=len(snapshot.turns) + 1,
                input_digest=input_digest,
                created_at=timestamp,
                metadata=dict(metadata or {}),
            )
            _, updated = self._append_locked(
                snapshot,
                run_id=run_id,
                evidence_type=EvidenceType.TURN_CREATED,
                entity_id=turn.id,
                payload=turn.model_dump(mode="json"),
                occurred_at=timestamp,
            )
            return updated.turns[turn.id]

    def ensure_operation(
        self,
        run_id: str,
        *,
        kind: OperationKind,
        idempotency_key: str,
        turn_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> Operation:
        """Return the stable operation for a key, rejecting semantic key reuse."""
        timestamp = _occurred_at(occurred_at)
        with self._transaction():
            snapshot = self._snapshot_locked(run_id)
            if snapshot is None:
                raise KeyError(f"Unknown run {run_id}")
            for existing in snapshot.operations.values():
                if existing.idempotency_key != idempotency_key:
                    continue
                if existing.kind is kind and existing.turn_id == turn_id:
                    return existing
                raise IdempotencyConflictError(
                    f"Operation key {idempotency_key!r} already identifies {existing.id}"
                )
            operation = Operation(
                id=new_operation_id(),
                run_id=run_id,
                turn_id=turn_id,
                ordinal=len(snapshot.operations) + 1,
                kind=kind,
                idempotency_key=idempotency_key,
                created_at=timestamp,
                updated_at=timestamp,
                metadata=dict(metadata or {}),
            )
            _, updated = self._append_locked(
                snapshot,
                run_id=run_id,
                evidence_type=EvidenceType.OPERATION_CREATED,
                entity_id=operation.id,
                payload=operation.model_dump(mode="json"),
                occurred_at=timestamp,
            )
            return updated.operations[operation.id]

    def _run_for_entity(self, entity_id: str, evidence_type: EvidenceType) -> str:
        row = self._connection.execute(
            """
            SELECT run_id FROM run_evidence
            WHERE entity_id = ? AND evidence_type = ?
            ORDER BY sequence ASC
            LIMIT 1
            """,
            (entity_id, evidence_type.value),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown entity {entity_id}")
        return str(row["run_id"])

    def start_attempt(
        self,
        operation_id: str,
        *,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> Attempt:
        """Start the next durable attempt for a stable operation."""
        timestamp = _occurred_at(occurred_at)
        run_id = self._run_for_entity(operation_id, EvidenceType.OPERATION_CREATED)
        with self._transaction():
            snapshot = self._snapshot_locked(run_id)
            if snapshot is None or operation_id not in snapshot.operations:
                raise KeyError(f"Unknown operation {operation_id}")
            operation_attempts = [
                item for item in snapshot.attempts.values() if item.operation_id == operation_id
            ]
            attempt = Attempt(
                id=new_attempt_id(),
                run_id=run_id,
                operation_id=operation_id,
                number=len(operation_attempts) + 1,
                status=AttemptStatus.RUNNING,
                started_at=timestamp,
                metadata=dict(metadata or {}),
            )
            _, updated = self._append_locked(
                snapshot,
                run_id=run_id,
                evidence_type=EvidenceType.ATTEMPT_STARTED,
                entity_id=attempt.id,
                payload=attempt.model_dump(mode="json"),
                occurred_at=timestamp,
            )
            return updated.attempts[attempt.id]

    def finish_attempt(
        self,
        attempt_id: str,
        status: AttemptStatus,
        *,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Finish one running attempt with an explicit terminal receipt."""
        if not status.is_terminal:
            raise ValueError("finish_attempt requires a terminal attempt status")
        run_id = self._run_for_entity(attempt_id, EvidenceType.ATTEMPT_STARTED)
        evidence, _ = self._append(
            run_id,
            EvidenceType.ATTEMPT_FINISHED,
            entity_id=attempt_id,
            payload={"status": status.value, "metadata": dict(metadata or {})},
            occurred_at=occurred_at,
        )
        return evidence

    def _operation_event(
        self,
        operation_id: str,
        evidence_type: EvidenceType,
        *,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        run_id = self._run_for_entity(operation_id, EvidenceType.OPERATION_CREATED)
        evidence, _ = self._append(
            run_id,
            evidence_type,
            entity_id=operation_id,
            payload=dict(payload or {}),
            occurred_at=occurred_at,
        )
        return evidence

    def dispatch_operation(
        self,
        operation_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Durably mark an operation before its dispatch boundary."""
        return self._operation_event(
            operation_id,
            EvidenceType.OPERATION_DISPATCHED,
            occurred_at=occurred_at,
        )

    def record_effect_started(
        self,
        operation_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Record that a tool side-effect boundary has been crossed."""
        return self._operation_event(
            operation_id,
            EvidenceType.OPERATION_EFFECT_STARTED,
            occurred_at=occurred_at,
        )

    def record_provider_partial_output(
        self,
        operation_id: str,
        *,
        chunk_digest: str,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Record only a digest for partial provider output."""
        return self._operation_event(
            operation_id,
            EvidenceType.PROVIDER_PARTIAL_OUTPUT,
            payload={"chunk_digest": chunk_digest},
            occurred_at=occurred_at,
        )

    def complete_operation(
        self,
        operation_id: str,
        *,
        result_digest: str | None = None,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Commit a durable successful operation receipt."""
        payload = {"result_digest": result_digest} if result_digest is not None else {}
        return self._operation_event(
            operation_id,
            EvidenceType.OPERATION_COMPLETED,
            payload=payload,
            occurred_at=occurred_at,
        )

    def fail_operation(
        self,
        operation_id: str,
        *,
        reason_code: str,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Commit a known operation failure without raw error text."""
        return self._operation_event(
            operation_id,
            EvidenceType.OPERATION_FAILED,
            payload={"reason_code": reason_code},
            occurred_at=occurred_at,
        )

    def cancel_operation(
        self,
        operation_id: str,
        *,
        reason_code: str,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Commit a confirmed operation cancellation."""
        return self._operation_event(
            operation_id,
            EvidenceType.OPERATION_CANCELLED,
            payload={"reason_code": reason_code},
            occurred_at=occurred_at,
        )

    def mark_operation_outcome_unknown(
        self,
        operation_id: str,
        *,
        reason_code: str,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Fail closed when an external operation result cannot be proven."""
        return self._operation_event(
            operation_id,
            EvidenceType.OPERATION_OUTCOME_UNKNOWN,
            payload={"reason_code": reason_code},
            occurred_at=occurred_at,
        )

    def record_evidence(
        self,
        run_id: str,
        evidence_type: EvidenceType,
        *,
        entity_id: str,
        payload: dict[str, Any],
        occurred_at: datetime | None = None,
        evidence_id: str | None = None,
    ) -> Evidence:
        """Record one allowlisted compatibility observation."""
        if evidence_type not in _OBSERVATION_TYPES:
            raise ValueError(f"{evidence_type.value} requires a typed store command")
        evidence, _ = self._append(
            run_id,
            evidence_type,
            entity_id=entity_id,
            payload=payload,
            occurred_at=occurred_at,
            evidence_id=evidence_id,
        )
        return evidence

    def get_snapshot(self, run_id: str) -> RunSnapshot:
        """Read the materialized projection for one run."""
        snapshot = self._snapshot_locked(run_id)
        if snapshot is None:
            raise KeyError(f"Unknown run {run_id}")
        return snapshot

    def get_evidence(self, run_id: str) -> list[Evidence]:
        """Return the authoritative evidence stream in run-local order."""
        rows = self._connection.execute(
            """
            SELECT evidence_json FROM run_evidence
            WHERE run_id = ?
            ORDER BY sequence ASC
            """,
            (run_id,),
        ).fetchall()
        return [Evidence.model_validate_json(str(row["evidence_json"])) for row in rows]

    def event_count(self, run_id: str) -> int:
        """Return the number of authoritative facts for a run."""
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM run_evidence WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return int(row["count"] if row is not None else 0)

    def replay(self, run_id: str) -> RunSnapshot:
        """Rebuild a read model without mutating durable state."""
        evidence = self.get_evidence(run_id)
        if not evidence:
            raise KeyError(f"Unknown run {run_id}")
        return replay(evidence)

    def rebuild_projection(self, run_id: str) -> RunSnapshot:
        """Replace a disposable projection from the authoritative log."""
        rebuilt = self.replay(run_id)
        with self._transaction():
            self._write_projection_locked(rebuilt)
        return rebuilt

    def verify(self, run_id: str) -> RunSnapshot:
        """Verify evidence digests, sequence, replay, and projection equality."""
        try:
            materialized = self.get_snapshot(run_id)
            rebuilt = self.replay(run_id)
        except (ValueError, sqlite3.DatabaseError) as exc:
            raise IntegrityVerificationError(str(exc)) from exc
        if rebuilt != materialized:
            raise IntegrityVerificationError(
                f"Materialized projection for {run_id} does not match replay"
            )
        return rebuilt
