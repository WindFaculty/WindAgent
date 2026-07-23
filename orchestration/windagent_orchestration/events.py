"""
Domain Events and Outbox Payloads for Orchestration V2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OrchestrationEvent:
    event_id: str
    event_type: str
    aggregate_id: str
    session_id: str
    payload: Dict[str, Any]
    sequence: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


TASK_CREATED = "orchestration.task.created"
TASK_TRANSITIONED = "orchestration.task.transitioned"
TASK_COMPLETED = "orchestration.task.completed"
TASK_FAILED = "orchestration.task.failed"
TASK_CANCELLED = "orchestration.task.cancelled"

WORKFLOW_STARTED = "orchestration.workflow.started"
WORKFLOW_STEP_DISPATCHED = "orchestration.workflow.step_dispatched"
WORKFLOW_STEP_COMPLETED = "orchestration.workflow.step_completed"
WORKFLOW_STEP_FAILED = "orchestration.workflow.step_failed"
WORKFLOW_CHECKPOINTED = "orchestration.workflow.checkpointed"

LEASE_ACQUIRED = "orchestration.lease.acquired"
LEASE_EXPIRED = "orchestration.lease.expired"
LEASE_RELEASED = "orchestration.lease.released"
