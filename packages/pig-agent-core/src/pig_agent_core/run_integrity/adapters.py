"""Compatibility adapters from existing runtime receipts into run evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from pig_llm import TurnOutcome

from ..compaction import CompactionCheckpoint
from ..observability.events import AgentEvent
from ..tools.audit import ToolAuditEntry
from ..usage import UsageRecord
from .models import (
    AttemptStatus,
    EvidenceType,
    OperationKind,
    RunStatus,
    content_digest,
)
from .store import SQLiteRunStore


def _safe_error_digest(value: object) -> str | None:
    if value is None or value == "":
        return None
    return content_digest({"value": str(value)})


def turn_outcome_status(outcome: TurnOutcome) -> RunStatus | None:
    """Map a legacy turn receipt to the closest R1 run terminal state."""
    if outcome is TurnOutcome.COMPLETED:
        return RunStatus.COMPLETED
    if outcome is TurnOutcome.TOOL_CALLS:
        return None
    if outcome in {TurnOutcome.ABORTED, TurnOutcome.UNKNOWN}:
        return RunStatus.OUTCOME_UNKNOWN
    return RunStatus.FAILED


def retry_observation_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Allowlist retry lifecycle fields and digest raw error text."""
    payload: dict[str, Any] = {}
    for key in (
        "retry_id",
        "phase",
        "reason",
        "attempt",
        "max_retries",
        "model",
        "partial_output",
        "checkpoint_id",
        "compaction_checkpoint_id",
    ):
        value = data.get(key)
        if isinstance(value, str | int | bool) or value is None:
            payload[key] = value
    error_digest = _safe_error_digest(data.get("error"))
    if error_digest is not None:
        payload["error_digest"] = error_digest
    return payload


def usage_record_payload(record: UsageRecord) -> dict[str, Any]:
    """Project a categorized usage receipt without copying arbitrary metadata."""
    return {
        "usage_record_id": record.id,
        "kind": record.kind.value,
        "model": record.model,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "cached_tokens": record.cached_tokens,
        "chargeable": record.chargeable,
        "metadata_digest": content_digest(record.metadata),
    }


def compaction_payload(checkpoint: CompactionCheckpoint) -> dict[str, Any]:
    """Project the durable compaction checkpoint identity and counts."""
    return checkpoint.to_dict()


def permission_denial_payload(denial: dict[str, str]) -> dict[str, Any]:
    """Keep the stable reason code while digesting target and message text."""
    return {
        "code": denial.get("code", "permission_denied"),
        "action": denial.get("action", "unknown"),
        "target_digest": content_digest({"target": denial.get("target", "")}),
        "message_digest": content_digest({"message": denial.get("message", "")}),
    }


def tool_audit_payload(entry: ToolAuditEntry) -> dict[str, Any]:
    """Project a tool audit without persisting args, user IDs, or raw errors."""
    return {
        "tool_name": entry.tool_name,
        "timestamp": entry.timestamp,
        "user_id_digest": content_digest({"user_id": entry.user_id}),
        "args_digest": content_digest(entry.args),
        "success": entry.success,
        "error_digest": _safe_error_digest(entry.error),
        "duration": entry.duration,
        "result_size": entry.result_size,
        "metadata_digest": content_digest(entry.metadata),
    }


@dataclass
class ActiveRunContext:
    """In-process correlation state; the authoritative facts remain in SQLite."""

    run_id: str
    turn_id: str
    owner_id: str
    provider_operations: dict[str, str] = field(default_factory=dict)
    attempts: dict[tuple[str, int], str] = field(default_factory=dict)
    partial_output: bool = False


class RunAuthority:
    """Fail-closed collaborator bridging current Agent turns to the R1 ledger."""

    def __init__(
        self,
        store: SQLiteRunStore,
        *,
        owner_id: str = "python-embedder",
        lease_duration: timedelta = timedelta(minutes=5),
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self.store = store
        self.owner_id = owner_id
        self.lease_duration = lease_duration
        self._active: ActiveRunContext | None = None
        self.last_run_id: str | None = None

    @property
    def is_active(self) -> bool:
        """Return whether one serialized host turn owns this authority."""
        return self._active is not None

    def begin_turn(
        self,
        *,
        session_id: str,
        user_input: str,
        occurred_at: datetime | None = None,
    ) -> ActiveRunContext:
        """Create durable run/turn identity before host or provider work begins."""
        if self._active is not None:
            raise RuntimeError("RunAuthority already has an active turn")
        timestamp = occurred_at or datetime.now(timezone.utc)
        run = self.store.create_run(
            session_id=session_id,
            owner_id=self.owner_id,
            lease_expires_at=timestamp + self.lease_duration,
            occurred_at=timestamp,
        )
        self.store.transition_run(run.id, RunStatus.RUNNING, occurred_at=timestamp)
        turn = self.store.create_turn(
            run.id,
            input_digest=content_digest({"input": user_input}),
            occurred_at=timestamp,
        )
        context = ActiveRunContext(
            run_id=run.id,
            turn_id=turn.id,
            owner_id=self.owner_id,
        )
        self._active = context
        self.last_run_id = run.id
        return context

    def _require_active(self) -> ActiveRunContext:
        context = self._active
        if context is None:
            raise RuntimeError("RunAuthority has no active turn")
        return context

    def record_provider_attempt(self, data: dict[str, Any]) -> None:
        """Persist provider attempt boundaries synchronously and fail closed."""
        context = self._active
        if context is None:
            return
        retry_id = data.get("retry_id")
        phase = data.get("phase")
        attempt_number = data.get("attempt")
        if not isinstance(retry_id, str) or not retry_id:
            raise ValueError("Provider attempt evidence requires retry_id")
        if phase not in {"started", "succeeded", "failed"}:
            raise ValueError("Provider attempt evidence has an invalid phase")
        if not isinstance(attempt_number, int) or attempt_number < 1:
            raise ValueError("Provider attempt evidence requires a 1-based attempt")

        operation_id = context.provider_operations.get(retry_id)
        if operation_id is None:
            operation = self.store.ensure_operation(
                context.run_id,
                turn_id=context.turn_id,
                kind=OperationKind.PROVIDER,
                idempotency_key=f"provider:{context.turn_id}:{retry_id}",
            )
            operation_id = operation.id
            context.provider_operations[retry_id] = operation_id

        key = (retry_id, attempt_number)
        attempt_id = context.attempts.get(key)
        if phase == "started":
            if attempt_id is not None:
                raise ValueError(f"Provider attempt {retry_id}/{attempt_number} already started")
            attempt = self.store.start_attempt(
                operation_id,
                metadata={"retry_id": retry_id},
            )
            if attempt.number != attempt_number:
                raise ValueError(
                    f"Provider attempt sequence mismatch: {attempt.number} != {attempt_number}"
                )
            context.attempts[key] = attempt.id
            self.store.dispatch_operation(operation_id)
        else:
            if attempt_id is None:
                raise ValueError(f"Provider attempt {retry_id}/{attempt_number} was not started")
            if phase == "succeeded":
                self.store.finish_attempt(attempt_id, AttemptStatus.SUCCEEDED)
                self.store.complete_operation(operation_id)
            else:
                partial_output = bool(data.get("partial_output", False))
                if partial_output:
                    context.partial_output = True
                    self.store.record_provider_partial_output(
                        operation_id,
                        chunk_digest=content_digest(
                            {"retry_id": retry_id, "attempt": attempt_number}
                        ),
                    )
                    self.store.finish_attempt(attempt_id, AttemptStatus.OUTCOME_UNKNOWN)
                    self.store.mark_operation_outcome_unknown(
                        operation_id,
                        reason_code="partial_provider_output",
                    )
                else:
                    self.store.finish_attempt(
                        attempt_id,
                        AttemptStatus.FAILED,
                        metadata={"reason": str(data.get("reason", "provider_error"))},
                    )
                    max_retries = data.get("max_retries")
                    if isinstance(max_retries, int) and attempt_number >= max_retries + 1:
                        self.store.fail_operation(
                            operation_id,
                            reason_code=str(data.get("reason", "provider_error")),
                        )

        self.store.record_evidence(
            context.run_id,
            EvidenceType.RETRY_OBSERVED,
            entity_id=operation_id,
            payload=retry_observation_payload(data),
        )

    def record_agent_event(self, event: AgentEvent) -> None:
        """Project legacy retry observations; never use this as a dispatch boundary."""
        context = self._active
        if context is None:
            return
        if "retry_id" not in event.data:
            return
        self.store.record_evidence(
            context.run_id,
            EvidenceType.RETRY_OBSERVED,
            entity_id=context.run_id,
            payload=retry_observation_payload(event.data),
            occurred_at=datetime.fromtimestamp(event.timestamp, tz=timezone.utc),
        )

    def record_usage_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Record cumulative usage as a digest-backed compatibility observation."""
        context = self._require_active()
        safe_counts: dict[str, Any] = {
            key: int(value)
            for key, value in snapshot.items()
            if key in {"llm_calls", "tool_calls", "input_tokens", "output_tokens", "cached_tokens"}
            and isinstance(value, int | float)
        }
        safe_counts["by_kind_digest"] = content_digest(snapshot.get("by_kind", {}))
        self.store.record_evidence(
            context.run_id,
            EvidenceType.USAGE_OBSERVED,
            entity_id=context.turn_id,
            payload=safe_counts,
        )

    def record_compaction(self, checkpoint: CompactionCheckpoint) -> None:
        """Record an existing durable compaction checkpoint by identity."""
        context = self._require_active()
        self.store.record_evidence(
            context.run_id,
            EvidenceType.COMPACTION_OBSERVED,
            entity_id=checkpoint.id,
            payload=compaction_payload(checkpoint),
        )

    def record_permission_denial(self, denial: dict[str, str]) -> None:
        """Record a redacted compatibility view of one permission denial."""
        context = self._require_active()
        self.store.record_evidence(
            context.run_id,
            EvidenceType.PERMISSION_DENIAL_OBSERVED,
            entity_id=context.turn_id,
            payload=permission_denial_payload(denial),
        )

    def record_tool_audit(self, entry: ToolAuditEntry) -> None:
        """Record a redacted compatibility view of an existing tool audit."""
        context = self._require_active()
        self.store.record_evidence(
            context.run_id,
            EvidenceType.TOOL_AUDIT_OBSERVED,
            entity_id=context.turn_id,
            payload=tool_audit_payload(entry),
            occurred_at=datetime.fromtimestamp(entry.timestamp, tz=timezone.utc),
        )

    def _finish_open_operations(
        self,
        context: ActiveRunContext,
        *,
        status: RunStatus,
        reason_code: str,
    ) -> RunStatus:
        snapshot = self.store.get_snapshot(context.run_id)
        open_operations = [
            item for item in snapshot.operations.values() if not item.status.is_terminal
        ]
        dispatched_open = [item for item in open_operations if item.dispatch_recorded]
        if status is RunStatus.COMPLETED and open_operations:
            status = RunStatus.OUTCOME_UNKNOWN
        if status is RunStatus.CANCELLED and dispatched_open:
            status = RunStatus.OUTCOME_UNKNOWN
        if context.partial_output:
            status = RunStatus.OUTCOME_UNKNOWN

        for operation in open_operations:
            refreshed = self.store.get_snapshot(context.run_id)
            active_attempts = [
                item
                for item in refreshed.attempts.values()
                if item.operation_id == operation.id and not item.status.is_terminal
            ]
            if status is RunStatus.OUTCOME_UNKNOWN:
                for attempt in active_attempts:
                    self.store.finish_attempt(attempt.id, AttemptStatus.OUTCOME_UNKNOWN)
                self.store.mark_operation_outcome_unknown(
                    operation.id,
                    reason_code=reason_code,
                )
            elif status is RunStatus.CANCELLED:
                for attempt in active_attempts:
                    self.store.finish_attempt(attempt.id, AttemptStatus.CANCELLED)
                self.store.cancel_operation(operation.id, reason_code=reason_code)
            else:
                for attempt in active_attempts:
                    self.store.finish_attempt(attempt.id, AttemptStatus.FAILED)
                self.store.fail_operation(operation.id, reason_code=reason_code)
        return status

    def finish_turn(
        self,
        context: ActiveRunContext,
        *,
        outcome: TurnOutcome,
        raw_finish_reason: str | None,
        permission_denials: tuple[dict[str, str], ...] = (),
        usage_snapshot: dict[str, Any] | None = None,
        compaction_checkpoint: CompactionCheckpoint | None = None,
    ) -> str:
        """Commit current receipts, release ownership, and write one run terminal."""
        if context is not self._require_active():
            raise RuntimeError("Cannot finish a stale run context")
        self.store.record_evidence(
            context.run_id,
            EvidenceType.TURN_OUTCOME_OBSERVED,
            entity_id=context.turn_id,
            payload={
                "outcome": outcome.value,
                "raw_finish_reason_digest": _safe_error_digest(raw_finish_reason),
            },
        )
        if usage_snapshot is not None:
            self.record_usage_snapshot(usage_snapshot)
        if compaction_checkpoint is not None:
            self.record_compaction(compaction_checkpoint)
        for denial in permission_denials:
            self.record_permission_denial(denial)

        status = turn_outcome_status(outcome) or RunStatus.FAILED
        status = self._finish_open_operations(
            context,
            status=status,
            reason_code=raw_finish_reason or outcome.value,
        )
        self.store.release_lease(context.run_id, owner_id=context.owner_id)
        self.store.transition_run(
            context.run_id,
            status,
            reason=raw_finish_reason or outcome.value,
        )
        self._active = None
        return context.run_id

    def fail_turn(self, context: ActiveRunContext, error: BaseException) -> str:
        """Fail closed after an exception, using outcome_unknown past dispatch."""
        if context is not self._require_active():
            raise RuntimeError("Cannot fail a stale run context")
        snapshot = self.store.get_snapshot(context.run_id)
        status = (
            RunStatus.OUTCOME_UNKNOWN
            if any(item.dispatch_recorded for item in snapshot.operations.values())
            else RunStatus.FAILED
        )
        status = self._finish_open_operations(
            context,
            status=status,
            reason_code="unhandled_exception",
        )
        self.store.record_evidence(
            context.run_id,
            EvidenceType.TURN_OUTCOME_OBSERVED,
            entity_id=context.turn_id,
            payload={
                "outcome": status.value,
                "error_digest": _safe_error_digest(error),
            },
        )
        self.store.release_lease(context.run_id, owner_id=context.owner_id)
        self.store.transition_run(
            context.run_id,
            status,
            reason="unhandled_exception",
        )
        self._active = None
        return context.run_id
