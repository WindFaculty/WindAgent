"""Canonical worker process boundary contracts."""

from windagent_core.contracts.workers.submission import WorkSubmissionPort
from windagent_core.contracts.workers.queue import DurableTaskQueuePort, ClaimedTask
from windagent_core.contracts.workers.leases import TaskLeasePort
from windagent_core.contracts.workers.control import WorkerStatusQueryPort
from windagent_core.contracts.workers.heartbeat import WorkerHeartbeatRepository
from windagent_core.contracts.workers.models import (
    WorkerHealth,
    WorkerHeartbeat,
    WorkerStatus,
    WorkSubmission,
)

__all__ = [
    "WorkSubmissionPort",
    "DurableTaskQueuePort",
    "ClaimedTask",
    "TaskLeasePort",
    "WorkerHealth",
    "WorkerHeartbeat",
    "WorkerHeartbeatRepository",
    "WorkerStatus",
    "WorkerStatusQueryPort",
    "WorkSubmission",
]