"""Commands and queries for the debug job transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from windagent.platform.commands import Command
from windagent.platform.queries import Query

if TYPE_CHECKING:
    from windagent.platform.jobs import JobRecord  # noqa: F401  (forward ref)


@dataclass(frozen=True, slots=True)
class SubmitDebugJob(Command["SubmitDebugJobResult"]):
    """Accept one debug job into the durable queue."""

    job_type: str
    payload: dict[str, object]
    priority: int = 0
    max_attempts: int = 3
    timeout_s: float | None = None
    deadline: datetime | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    trace_id: str | None = None
    actor_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class SubmitDebugJobResult:
    """Durable identity of an accepted debug job."""

    job_id: str
    deduplicated: bool


@dataclass(frozen=True, slots=True)
class GetDebugJob(Query["JobRecord"]):
    """Resolve one debug job's durable record."""

    job_id: str


@dataclass(frozen=True, slots=True)
class CancelDebugJob(Command["bool"]):
    """Request durable cancellation of one debug job."""

    job_id: str
