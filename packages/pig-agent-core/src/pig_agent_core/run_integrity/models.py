"""Versioned data contracts for durable run integrity."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1
SchemaVersion = Literal[1]


def _new_id(prefix: str) -> str:
    return f"{prefix}_v{SCHEMA_VERSION}_{uuid.uuid4().hex}"


def new_run_id() -> str:
    """Create a versioned run identifier."""
    return _new_id("run")


def new_turn_id() -> str:
    """Create a versioned turn identifier."""
    return _new_id("turn")


def new_operation_id() -> str:
    """Create a versioned operation identifier."""
    return _new_id("op")


def new_attempt_id() -> str:
    """Create a versioned attempt identifier."""
    return _new_id("attempt")


def new_evidence_id() -> str:
    """Create a versioned evidence identifier."""
    return _new_id("evidence")


def _validate_id(value: str, prefix: str) -> str:
    expected = f"{prefix}_v{SCHEMA_VERSION}_"
    suffix = value.removeprefix(expected)
    if not value.startswith(expected) or len(suffix) != 32:
        raise ValueError(f"identifier must use the {expected}<uuid-hex> format")
    try:
        uuid.UUID(hex=suffix)
    except ValueError as exc:
        raise ValueError(f"identifier must use the {expected}<uuid-hex> format") from exc
    return value


def canonical_json(value: Any) -> str:
    """Return the canonical JSON encoding used by integrity digests."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("run evidence payload must be canonical JSON data") from exc


def content_digest(value: Any) -> str:
    """Return a content-addressed SHA-256 digest for canonical JSON data."""
    encoded = canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class RunStatus(str, Enum):
    """Governed lifecycle state for one logical run."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown"

    @classmethod
    def terminal(cls) -> frozenset[RunStatus]:
        """Return the states that permanently close a run."""
        return frozenset({cls.COMPLETED, cls.FAILED, cls.CANCELLED, cls.OUTCOME_UNKNOWN})

    @property
    def is_terminal(self) -> bool:
        """Return whether no later run transition is valid."""
        return self in self.terminal()


class OperationKind(str, Enum):
    """Operation categories recorded by the R1 protocol."""

    PROVIDER = "provider"
    TOOL = "tool"
    POLICY = "policy"
    COMPACTION = "compaction"
    ARTIFACT = "artifact"
    EXTENSION = "extension"


class OperationStatus(str, Enum):
    """Durable state of one logical operation across its attempts."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown"

    @property
    def is_terminal(self) -> bool:
        """Return whether the logical operation has a terminal receipt."""
        return self in {
            self.COMPLETED,
            self.FAILED,
            self.CANCELLED,
            self.OUTCOME_UNKNOWN,
        }


class AttemptStatus(str, Enum):
    """State of one concrete execution attempt."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    OUTCOME_UNKNOWN = "outcome_unknown"

    @property
    def is_terminal(self) -> bool:
        """Return whether this attempt has finished."""
        return self is not self.RUNNING


class EvidenceType(str, Enum):
    """Stable append-only facts understood by the R1 projection kernel."""

    RUN_CREATED = "run_created"
    RUN_TRANSITIONED = "run_transitioned"
    LEASE_ACQUIRED = "lease_acquired"
    LEASE_RELEASED = "lease_released"
    OWNERSHIP_EXPIRED = "ownership_expired"
    TURN_CREATED = "turn_created"
    OPERATION_CREATED = "operation_created"
    OPERATION_DISPATCHED = "operation_dispatched"
    OPERATION_EFFECT_STARTED = "operation_effect_started"
    PROVIDER_PARTIAL_OUTPUT = "provider_partial_output"
    OPERATION_COMPLETED = "operation_completed"
    OPERATION_FAILED = "operation_failed"
    OPERATION_CANCELLED = "operation_cancelled"
    OPERATION_OUTCOME_UNKNOWN = "operation_outcome_unknown"
    ATTEMPT_STARTED = "attempt_started"
    ATTEMPT_FINISHED = "attempt_finished"
    TURN_OUTCOME_OBSERVED = "turn_outcome_observed"
    RETRY_OBSERVED = "retry_observed"
    USAGE_OBSERVED = "usage_observed"
    COMPACTION_OBSERVED = "compaction_observed"
    PERMISSION_DENIAL_OBSERVED = "permission_denial_observed"
    TOOL_AUDIT_OBSERVED = "tool_audit_observed"
    RECOVERY_CLASSIFIED = "recovery_classified"


class ProtocolModel(BaseModel):
    """Immutable base for versioned protocol objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: SchemaVersion = 1


class Run(ProtocolModel):
    """One governed request and its single lifecycle authority."""

    _id_prefix: ClassVar[str] = "run"

    id: str
    session_id: str
    status: RunStatus = RunStatus.PENDING
    created_at: datetime
    updated_at: datetime
    owner_id: str | None = None
    lease_expires_at: datetime | None = None
    terminal_evidence_id: str | None = None
    revision: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        return _validate_id(value, cls._id_prefix)


class Turn(ProtocolModel):
    """One model-facing reasoning cycle within a run."""

    id: str
    run_id: str
    ordinal: int = Field(ge=1)
    input_digest: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        return _validate_id(value, "turn")

    @field_validator("run_id")
    @classmethod
    def _valid_run_id(cls, value: str) -> str:
        return _validate_id(value, "run")


class Operation(ProtocolModel):
    """A stable logical operation whose retries share one identity."""

    id: str
    run_id: str
    turn_id: str | None = None
    ordinal: int = Field(ge=1)
    kind: OperationKind
    idempotency_key: str = Field(min_length=1)
    status: OperationStatus = OperationStatus.PENDING
    dispatch_recorded: bool = False
    effect_started: bool = False
    partial_output: bool = False
    receipt_recorded: bool = False
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        return _validate_id(value, "op")

    @field_validator("run_id")
    @classmethod
    def _valid_run_id(cls, value: str) -> str:
        return _validate_id(value, "run")

    @field_validator("turn_id")
    @classmethod
    def _valid_turn_id(cls, value: str | None) -> str | None:
        return _validate_id(value, "turn") if value is not None else None


class Attempt(ProtocolModel):
    """One observable execution attempt of a stable operation."""

    id: str
    run_id: str
    operation_id: str
    number: int = Field(ge=1)
    status: AttemptStatus
    started_at: datetime
    finished_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        return _validate_id(value, "attempt")

    @field_validator("run_id")
    @classmethod
    def _valid_run_id(cls, value: str) -> str:
        return _validate_id(value, "run")

    @field_validator("operation_id")
    @classmethod
    def _valid_operation_id(cls, value: str) -> str:
        return _validate_id(value, "op")


class Evidence(ProtocolModel):
    """One content-addressed fact in a run's append-only hash chain."""

    id: str
    run_id: str
    sequence: int = Field(ge=1)
    type: EvidenceType
    entity_id: str
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_digest: str
    previous_digest: str | None
    digest: str

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        return _validate_id(value, "evidence")

    @field_validator("run_id")
    @classmethod
    def _valid_run_id(cls, value: str) -> str:
        return _validate_id(value, "run")

    @classmethod
    def create(
        cls,
        *,
        id: str,
        run_id: str,
        sequence: int,
        type: EvidenceType,
        entity_id: str,
        occurred_at: datetime,
        payload: dict[str, Any],
        previous_digest: str | None,
    ) -> Evidence:
        """Create evidence after deriving canonical payload and chain digests."""
        normalized_payload = json.loads(canonical_json(payload))
        payload_digest = content_digest(normalized_payload)
        digest = content_digest(
            {
                "schema_version": SCHEMA_VERSION,
                "id": id,
                "run_id": run_id,
                "sequence": sequence,
                "type": type.value,
                "entity_id": entity_id,
                "occurred_at": occurred_at.isoformat(),
                "payload_digest": payload_digest,
                "previous_digest": previous_digest,
            }
        )
        return cls(
            id=id,
            run_id=run_id,
            sequence=sequence,
            type=type,
            entity_id=entity_id,
            occurred_at=occurred_at,
            payload=normalized_payload,
            payload_digest=payload_digest,
            previous_digest=previous_digest,
            digest=digest,
        )

    def verify(self) -> None:
        """Fail closed when the evidence payload or envelope was modified."""
        expected = type(self).create(
            id=self.id,
            run_id=self.run_id,
            sequence=self.sequence,
            type=self.type,
            entity_id=self.entity_id,
            occurred_at=self.occurred_at,
            payload=self.payload,
            previous_digest=self.previous_digest,
        )
        if expected.payload_digest != self.payload_digest:
            raise ValueError(f"Evidence {self.id} has an invalid payload digest")
        if expected.digest != self.digest:
            raise ValueError(f"Evidence {self.id} has an invalid chain digest")


class RunSnapshot(ProtocolModel):
    """Deterministic read model derived only from append-only evidence."""

    run: Run
    sequence: int
    last_digest: str
    turns: dict[str, Turn] = Field(default_factory=dict)
    operations: dict[str, Operation] = Field(default_factory=dict)
    attempts: dict[str, Attempt] = Field(default_factory=dict)

    def latest_operation(self) -> Operation | None:
        """Return the last recorded operation in stable ordinal order."""
        if not self.operations:
            return None
        return max(self.operations.values(), key=lambda item: (item.ordinal, item.id))


class RecoveryClassification(str, Enum):
    """Fail-closed recovery result for expired ownership."""

    LEASE_ACTIVE = "lease_active"
    UNOWNED = "unowned"
    BEFORE_DISPATCH = "before_dispatch"
    PROVIDER_OUTCOME_UNKNOWN = "provider_outcome_unknown"
    BEFORE_TOOL_EFFECT = "before_tool_effect"
    TOOL_OUTCOME_UNKNOWN = "tool_outcome_unknown"
    DURABLE_OPERATION_COMPLETION = "durable_operation_completion"
    ALREADY_TERMINAL = "already_terminal"


class RecoveryDecision(ProtocolModel):
    """Recorded recovery classification without implicit redispatch."""

    run_id: str
    classification: RecoveryClassification
    status: RunStatus
    operation_id: str | None = None
    should_redispatch: bool = False
    resume_allowed: bool = False
    evidence_id: str | None = None

    @field_validator("run_id")
    @classmethod
    def _valid_run_id(cls, value: str) -> str:
        return _validate_id(value, "run")
