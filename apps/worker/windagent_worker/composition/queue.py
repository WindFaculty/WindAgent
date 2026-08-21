"""Durable Worker queue/lease composition (Architecture V3 Phase 8)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from windagent_storage.factory import create_sql_execution_lease_repository
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue
from windagent_storage.repositories.worker_status import SqlWorkerHeartbeatRepository
from windagent_worker.lease import DurableTaskLeaseManager


@dataclass(frozen=True)
class QueueBundle:
    task_queue: SqlDurableTaskQueue
    lease_manager: DurableTaskLeaseManager
    heartbeat_repo: SqlWorkerHeartbeatRepository


class QueueComposer:
    """Compose the Worker-only durable claim and heartbeat authorities."""

    @staticmethod
    def compose(session_factory: Any) -> QueueBundle:
        return QueueBundle(
            task_queue=SqlDurableTaskQueue(session_factory),
            lease_manager=DurableTaskLeaseManager(
                session_factory=session_factory,
                lease_repository_factory=create_sql_execution_lease_repository,
            ),
            heartbeat_repo=SqlWorkerHeartbeatRepository(session_factory),
        )


__all__ = ["QueueBundle", "QueueComposer"]
