"""Framework-free worker process boundary models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class WorkerHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class WorkerHeartbeat:
    worker_id: str
    runtime_type: str
    health: WorkerHealth
    active_leases: int
    last_heartbeat_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkSubmission:
    task_id: str
    session_id: str
    prompt: str
    workflow_name: str
    idempotency_key: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerStatus:
    available: bool
    active_workers: int
    active_leases: int
    workers: tuple[WorkerHeartbeat, ...] = ()