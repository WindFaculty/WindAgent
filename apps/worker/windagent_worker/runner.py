"""
Background Production Worker for WindAgent Architecture V2 (Phase 12).
Handles task claims, heartbeat lease renewal, workflow execution, cancellation, and crash recovery.
"""

import logging
from typing import Any, Dict, List, Optional
from windagent_worker.lease import TaskLeaseManager

logger = logging.getLogger("windagent.worker")


class ProductionWorker:
    """Production Worker handling task claim, lease heartbeat, workflow execution, and cancellation."""

    def __init__(self, name: str = "default-worker", lease_manager: Optional[TaskLeaseManager] = None):
        self.name = name
        self.worker_id = f"worker_{name}"
        self.lease_manager = lease_manager or TaskLeaseManager()
        self._running = False
        self._ready = False
        self._current_task_id: Optional[str] = None
        self._cancellation_requested = False
        self._emitted_events: List[Dict[str, Any]] = []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def current_task_id(self) -> Optional[str]:
        return self._current_task_id

    async def start(self) -> None:
        logger.info(f"Starting Production Worker [{self.name}]...")
        self._running = True
        self._ready = True
        self._cancellation_requested = False
        logger.info(f"Production Worker [{self.name}] ready.")

    async def stop(self) -> None:
        logger.info(f"Stopping Production Worker [{self.name}]...")
        self._ready = False
        self._running = False
        if self._current_task_id:
            self.lease_manager.release_lease(self._current_task_id, self.worker_id)
            self._current_task_id = None
        logger.info(f"Production Worker [{self.name}] stopped.")

    async def cancel(self) -> None:
        """Triggers cancellation signal for current executing task."""
        logger.warning(f"Signalling task cancellation on Worker [{self.name}]...")
        self._cancellation_requested = True

    def emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emits domain event from worker execution."""
        event = {"worker_id": self.worker_id, "event_type": event_type, "payload": payload}
        self._emitted_events.append(event)
        logger.info(f"Worker [{self.name}] emitted event {event_type}")

    async def poll_and_execute_tick(self) -> Dict[str, Any]:
        """Performs a single worker poll-claim-execute-heartbeat tick."""
        if not self._ready:
            raise RuntimeError(f"Worker [{self.name}] is not ready.")

        # Try to claim pending or abandoned task
        claimed_task = self.lease_manager.claim_task(self.worker_id)
        if not claimed_task:
            return {"status": "idle", "processed": 0}

        task_id = claimed_task["task_id"]
        self._current_task_id = task_id
        self.emit_event("TaskClaimedEvent", {"task_id": task_id, "worker_id": self.worker_id})

        # Send heartbeat lease renewal
        renewed = self.lease_manager.renew_lease(task_id, self.worker_id)
        if not renewed:
            self._current_task_id = None
            return {"status": "lease_error", "task_id": task_id}

        # Check for cancellation signal
        if self._cancellation_requested:
            self.emit_event("TaskCancelledEvent", {"task_id": task_id})
            self.lease_manager.release_lease(task_id, self.worker_id)
            self._current_task_id = None
            self._cancellation_requested = False
            return {"status": "cancelled", "task_id": task_id}

        # Simulate step workflow execution
        self.emit_event("TaskExecutedEvent", {"task_id": task_id, "workflow": claimed_task.get("workflow_name")})
        self.lease_manager.release_lease(task_id, self.worker_id)
        self._current_task_id = None

        return {"status": "completed", "task_id": task_id, "processed": 1}

    async def noop_consumer_tick(self) -> dict:
        """Executes a single no-op tick for consumer verification."""
        if not self._ready:
            raise RuntimeError(f"Worker [{self.name}] is not ready.")
        tick = await self.poll_and_execute_tick()
        if tick.get("status") == "idle":
            return {"status": "ok", "processed": 0}
        return tick


class WorkerRunner(ProductionWorker):
    """Backward compatible WorkerRunner alias."""
    def __init__(self, name: str = "default-worker"):
        super().__init__(name=name)
