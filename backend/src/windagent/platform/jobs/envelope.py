"""Canonical immutable job envelope and durable read-side state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from windagent.kernel.ids import ActorId, CausationId, CorrelationId, EntityId
from windagent.kernel.time import normalize_utc
from windagent.kernel.types import Version, validate_trace_id
from windagent.kernel.types.json import JSONValue, freeze_json, freeze_json_mapping


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


class JobStatus(StrEnum):
    """Complete durable lifecycle of a platform job."""

    PENDING = "pending"
    RETRY_WAIT = "retry_wait"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}


class JobEventType(StrEnum):
    """Stable event names emitted by atomic job finalization."""

    SUCCEEDED = "platform.job.succeeded"
    FAILED = "platform.job.failed"
    RETRY_SCHEDULED = "platform.job.retry_scheduled"
    CANCELLED = "platform.job.cancelled"


@dataclass(frozen=True, slots=True)
class JobEnvelope:
    """One claimed execution attempt, including its fencing authority."""

    id: EntityId
    job_type: str
    version: Version
    payload: Mapping[str, JSONValue] = field(default_factory=dict)
    priority: int = 0
    attempt: int = 0
    max_attempts: int = 3
    timeout_s: float | None = None
    deadline: datetime | None = None
    correlation_id: CorrelationId | None = None
    causation_id: CausationId | None = None
    trace_id: str | None = None
    actor_id: ActorId | None = None
    fencing_token: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, EntityId):
            raise TypeError("id must be an EntityId")
        object.__setattr__(self, "job_type", _required_text(self.job_type, "job_type"))
        if not isinstance(self.version, Version):
            raise TypeError("version must be a Version")
        if int(self.version) < 1:
            raise ValueError("version must be at least 1")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        object.__setattr__(self, "payload", freeze_json_mapping(self.payload))
        integer_fields = (
            (self.priority, "priority"),
            (self.attempt, "attempt"),
            (self.max_attempts, "max_attempts"),
        )
        for value, name in integer_fields:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.attempt < 0:
            raise ValueError("attempt must be non-negative")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.attempt > self.max_attempts:
            raise ValueError("attempt cannot exceed max_attempts")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self.deadline is not None:
            object.__setattr__(self, "deadline", normalize_utc(self.deadline))
        if self.correlation_id is not None and not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("correlation_id must be a CorrelationId")
        if self.causation_id is not None and not isinstance(self.causation_id, CausationId):
            raise TypeError("causation_id must be a CausationId")
        if self.trace_id is not None:
            object.__setattr__(self, "trace_id", validate_trace_id(self.trace_id))
        if self.actor_id is not None and not isinstance(self.actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId")
        if self.fencing_token is not None:
            object.__setattr__(
                self,
                "fencing_token",
                _required_text(self.fencing_token, "fencing_token"),
            )


@dataclass(frozen=True, slots=True)
class JobRecord:
    """Transport-safe durable snapshot of a job and its latest outcome."""

    envelope: JobEnvelope
    status: JobStatus
    available_at: datetime
    created_at: datetime
    updated_at: datetime
    lease_expires_at: datetime | None = None
    completed_at: datetime | None = None
    cancellation_requested: bool = False
    result: JSONValue | None = None
    error: str | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, JobEnvelope):
            raise TypeError("envelope must be a JobEnvelope")
        if not isinstance(self.status, JobStatus):
            raise TypeError("status must be a JobStatus")
        for field_name in ("available_at", "created_at", "updated_at"):
            object.__setattr__(self, field_name, normalize_utc(getattr(self, field_name)))
        for field_name in ("lease_expires_at", "completed_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, normalize_utc(value))
        if self.result is not None:
            object.__setattr__(self, "result", freeze_json(self.result))
