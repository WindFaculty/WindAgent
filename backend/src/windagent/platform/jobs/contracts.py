"""Domain-neutral job submission, scheduling, and worker contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from windagent.kernel.ids import ActorId, CausationId, CorrelationId, EntityId
from windagent.kernel.time import normalize_utc
from windagent.kernel.types import Version, validate_trace_id
from windagent.kernel.types.json import JSONValue, freeze_json_mapping

from .envelope import JobEnvelope, JobRecord, JobStatus


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


def _optional_text(value: str | None, field: str) -> str | None:
    return None if value is None else _required_text(value, field)


@dataclass(frozen=True, slots=True, init=False)
class JobSubmission:
    """A portable, immutable request for one durable background operation."""

    job_type: str
    payload: Mapping[str, JSONValue]
    version: Version
    priority: int
    max_attempts: int
    timeout_s: float | None
    deadline: datetime | None
    correlation_id: CorrelationId | None
    causation_id: CausationId | None
    trace_id: str | None
    actor_id: ActorId | None
    idempotency_key: str | None

    def __init__(
        self,
        job_type: str,
        payload: Mapping[str, object] | None = None,
        *,
        version: Version | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        timeout_s: float | None = None,
        deadline: datetime | None = None,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationId | None = None,
        trace_id: str | None = None,
        actor_id: ActorId | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TypeError("priority must be an integer")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise TypeError("max_attempts must be an integer")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if timeout_s is not None:
            if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
                raise TypeError("timeout_s must be a number")
            if timeout_s <= 0:
                raise ValueError("timeout_s must be positive")
        if version is not None and not isinstance(version, Version):
            raise TypeError("version must be a Version")
        if correlation_id is not None and not isinstance(correlation_id, CorrelationId):
            raise TypeError("correlation_id must be a CorrelationId")
        if causation_id is not None and not isinstance(causation_id, CausationId):
            raise TypeError("causation_id must be a CausationId")
        if actor_id is not None and not isinstance(actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId")

        raw_payload: Mapping[str, object] = {} if payload is None else payload
        if not isinstance(raw_payload, Mapping):
            raise TypeError("payload must be a mapping")

        object.__setattr__(self, "job_type", _required_text(job_type, "job_type"))
        object.__setattr__(self, "payload", freeze_json_mapping(raw_payload))
        object.__setattr__(self, "version", version or Version(1))
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "max_attempts", max_attempts)
        object.__setattr__(self, "timeout_s", float(timeout_s) if timeout_s is not None else None)
        object.__setattr__(
            self,
            "deadline",
            normalize_utc(deadline) if deadline is not None else None,
        )
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "causation_id", causation_id)
        object.__setattr__(
            self,
            "trace_id",
            validate_trace_id(trace_id) if trace_id is not None else None,
        )
        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(
            self,
            "idempotency_key",
            _optional_text(idempotency_key, "idempotency_key"),
        )


@dataclass(frozen=True, slots=True)
class JobReceipt:
    """The durable identity returned after a submission is accepted."""

    job_id: EntityId
    deduplicated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, EntityId):
            raise TypeError("job_id must be an EntityId")


@dataclass(frozen=True, slots=True)
class JobLeaseState:
    """Outcome of an exact-token lease authority probe/renewal."""

    authoritative: bool
    cancellation_requested: bool = False
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class JobFinalization:
    """Outcome of a fencing-protected atomic finalization attempt."""

    accepted: bool
    status: JobStatus
    retry_scheduled: bool = False


@runtime_checkable
class JobHandler(Protocol):
    """Executes the immutable payload for one declared ``job_type``."""

    @property
    def job_type(self) -> str:
        """Return the stable type name this handler owns."""

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        """Execute a claimed job payload and return a JSON-compatible result."""


@runtime_checkable
class JobQueue(Protocol):
    """Accepts work for a later worker runtime to execute."""

    async def submit(self, job: JobSubmission) -> JobReceipt:
        """Persist and accept a background job request."""


@runtime_checkable
class JobScheduler(Protocol):
    """Accepts work that must not run before a timestamp."""

    async def schedule(self, job: JobSubmission, *, run_at: datetime) -> JobReceipt:
        """Persist a scheduled job request."""


@runtime_checkable
class DurableJobQueue(JobQueue, JobScheduler, Protocol):
    """Worker-facing reliability surface implemented by the SQL adapter."""

    async def claim_next(self, *, worker_id: str, lease_s: float) -> JobEnvelope | None:
        """Atomically claim the highest-priority available job."""

    async def heartbeat(
        self,
        job: JobEnvelope,
        *,
        worker_id: str,
        lease_s: float,
    ) -> JobLeaseState:
        """Renew the exact lease and expose a durable cancellation request."""

    async def complete(
        self, job: JobEnvelope, *, worker_id: str, result: object
    ) -> JobFinalization:
        """Atomically persist success, release the lease, and write its outbox event."""

    async def fail(
        self,
        job: JobEnvelope,
        *,
        worker_id: str,
        error: str,
        retryable: bool,
        retry_delay_s: float,
    ) -> JobFinalization:
        """Atomically fail or schedule retry under the exact fencing token."""

    async def cancel_claim(
        self, job: JobEnvelope, *, worker_id: str
    ) -> JobFinalization:
        """Finalize a claimed job whose durable cancellation was observed."""

    async def request_cancel(self, job_id: EntityId) -> bool:
        """Cancel queued work immediately or flag running work for its owner."""

    async def get(self, job_id: EntityId) -> JobRecord | None:
        """Return the durable read model for one job."""

    async def recover_expired(self, *, limit: int = 100) -> int:
        """Finalize cancelled or exhausted expired claims after a crash."""
