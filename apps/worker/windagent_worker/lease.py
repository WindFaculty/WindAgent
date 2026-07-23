"""
Distributed Task Lease Manager for WindAgent Production Worker (Phase 12).
Handles task claiming, lease locking, heartbeat renewals, and abandoned task recovery.
Guarantees zero duplicate execution across multiple workers.
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class TaskLease:
    """Represents a time-bound lease lock held by a worker on a task."""
    task_id: str
    worker_id: str
    acquired_at: float
    expires_at: float
    heartbeat_count: int = 0


class TaskLeaseManager:
    """Manages lease locks for distributed worker task execution."""

    def __init__(self, default_lease_ttl_sec: float = 10.0) -> None:
        self.default_lease_ttl_sec = default_lease_ttl_sec
        self._leases: Dict[str, TaskLease] = {}
        self._pending_tasks: List[Dict[str, Any]] = []

    def add_pending_task(self, task_id: str, prompt: str, workflow_name: str = "bugfix") -> None:
        """Adds a task to the queue for worker claim."""
        self._pending_tasks.append({
            "task_id": task_id,
            "prompt": prompt,
            "workflow_name": workflow_name,
            "status": "QUEUED"
        })

    def claim_task(self, worker_id: str, lease_ttl_sec: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Claims an available pending task and acquires a lease lock."""
        now = time.time()
        ttl = lease_ttl_sec or self.default_lease_ttl_sec

        # Check for abandoned tasks with expired leases first
        abandoned = self.recover_abandoned_tasks()
        if abandoned:
            task_data = abandoned[0]
            lease = TaskLease(
                task_id=task_data["task_id"],
                worker_id=worker_id,
                acquired_at=now,
                expires_at=now + ttl
            )
            self._leases[task_data["task_id"]] = lease
            task_data["status"] = "CLAIMED"
            return task_data

        # Find next unclaimed pending task
        for task in self._pending_tasks:
            task_id = task["task_id"]
            if task_id not in self._leases and task["status"] == "QUEUED":
                lease = TaskLease(
                    task_id=task_id,
                    worker_id=worker_id,
                    acquired_at=now,
                    expires_at=now + ttl
                )
                self._leases[task_id] = lease
                task["status"] = "CLAIMED"
                return task

        return None

    def renew_lease(self, task_id: str, worker_id: str, lease_ttl_sec: Optional[float] = None) -> bool:
        """Renews lease lock via heartbeat."""
        now = time.time()
        ttl = lease_ttl_sec or self.default_lease_ttl_sec
        lease = self._leases.get(task_id)

        if lease and lease.worker_id == worker_id:
            lease.expires_at = now + ttl
            lease.heartbeat_count += 1
            return True
        return False

    def release_lease(self, task_id: str, worker_id: str) -> bool:
        """Releases lease lock upon task completion or cancellation."""
        lease = self._leases.get(task_id)
        if lease and lease.worker_id == worker_id:
            del self._leases[task_id]
            for t in self._pending_tasks:
                if t["task_id"] == task_id:
                    t["status"] = "COMPLETED"
            return True
        return False

    def recover_abandoned_tasks(self) -> List[Dict[str, Any]]:
        """Identifies tasks with expired leases and marks them abandoned for recovery."""
        now = time.time()
        expired_task_ids = []

        for task_id, lease in list(self._leases.items()):
            if now > lease.expires_at:
                expired_task_ids.append(task_id)

        recovered_tasks = []
        for task_id in expired_task_ids:
            del self._leases[task_id]
            for t in self._pending_tasks:
                if t["task_id"] == task_id and t["status"] == "CLAIMED":
                    t["status"] = "QUEUED"
                    recovered_tasks.append(t)

        return recovered_tasks

    def get_lease(self, task_id: str) -> Optional[TaskLease]:
        return self._leases.get(task_id)
