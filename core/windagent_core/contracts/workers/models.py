"""Framework-free worker process boundary models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional


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
    prompt: str
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    workflow_name: str = "default"
    idempotency_key: Optional[str] = None
    tool_name: str = "read_file"
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerStatus:
    available: bool
    active_workers: int
    active_leases: int
    workers: tuple[WorkerHeartbeat, ...] = ()