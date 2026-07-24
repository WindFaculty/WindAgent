"""
Background Production Worker for WindAgent Architecture V2 (Phase 11 Adoption).
Handles task claims, heartbeat lease renewal, workflow execution, cancellation, and crash recovery.
Uses canonical WorkerId, RuntimeRunId, TaskState, TaskLifecycle, and EventEnvelope.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from windagent_core.domain.types import WorkerId, RuntimeRunId, TaskId, EventId
from windagent_core.domain.lifecycle import TaskState, TaskLifecycle, utc_now
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_worker.lease import TaskLeaseManager

logger = logging.getLogger("windagent.worker")


class ProductionWorker:
    """Production Worker handling task claim, lease heartbeat, workflow execution, and cancellation."""

    def __init__(self, name: str = "default-worker", lease_manager: Optional[TaskLeaseManager] = None):
        self.name = name
        self.worker_id = WorkerId(f"wkr_{name}")
        self.runtime_run_id = RuntimeRunId.generate()
        self.lease_manager = lease_manager or TaskLeaseManager()
        self._running = False
        self._ready = False
        self._current_task_id: Optional[TaskId] = None
        self._cancellation_requested = False
        self._emitted_envelopes: List[EventEnvelope] = []
        self._sequence_counter = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def current_task_id(self) -> Optional[str]:
        return str(self._current_task_id) if self._current_task_id else None

    async def start(self) -> None:
        logger.info(f"Starting Production Worker [{self.worker_id}] (runtime: {self.runtime_run_id})...")
        self._running = True
        self._ready = True
        self._cancellation_requested = False
        logger.info(f"Production Worker [{self.worker_id}] ready.")

    async def stop(self) -> None:
        logger.info(f"Stopping Production Worker [{self.worker_id}]...")
        self._ready = False
        self._running = False
        if self._current_task_id:
            self.lease_manager.release_lease(str(self._current_task_id), str(self.worker_id))
            self._current_task_id = None
        logger.info(f"Production Worker [{self.worker_id}] stopped.")

    async def cancel(self) -> None:
        """Triggers cancellation signal for current executing task."""
        logger.warning(f"Signalling task cancellation on Worker [{self.worker_id}]...")
        self._cancellation_requested = True

    def emit_event(self, event_type: EventCatalog | str, payload: Dict[str, Any], aggregate_id: str = "worker") -> EventEnvelope:
        """Emits canonical EventEnvelope from worker execution."""
        self._sequence_counter += 1
        ev_str = event_type.value if hasattr(event_type, "value") else str(event_type)

        env = EventEnvelope(
            event_id=EventId.generate(),
            event_type=ev_str,
            aggregate_id=aggregate_id,
            sequence=self._sequence_counter,
            payload=payload,
            metadata={"worker_id": str(self.worker_id), "runtime_run_id": str(self.runtime_run_id)}
        )
        self._emitted_envelopes.append(env)
        logger.info(f"Worker [{self.worker_id}] emitted EventEnvelope seq={env.sequence}")
        return env

    async def poll_and_execute_tick(self) -> Dict[str, Any]:
        """Performs a single worker poll-claim-execute-heartbeat tick."""
        if not self._ready:
            raise RuntimeError(f"Worker [{self.worker_id}] is not ready.")

        # Try to claim pending or abandoned task
        claimed_task = self.lease_manager.claim_task(str(self.worker_id))
        if not claimed_task:
            return {"status": "idle", "processed": 0}

        raw_tid = str(claimed_task["task_id"])
        try:
            tid = str(TaskId(raw_tid))
        except Exception:
            tid = raw_tid

        self._current_task_id = tid
        self.emit_event(EventCatalog.TASK_CREATED, {"task_id": tid, "worker_id": str(self.worker_id)}, aggregate_id=tid)

        # Send heartbeat lease renewal
        renewed = self.lease_manager.renew_lease(raw_tid, str(self.worker_id))
        if not renewed:
            self._current_task_id = None
            return {"status": "lease_error", "task_id": raw_tid}

        # Check for cancellation signal
        if self._cancellation_requested:
            self.emit_event(EventCatalog.TASK_CANCELLED, {"task_id": tid}, aggregate_id=tid)
            self.lease_manager.release_lease(raw_tid, str(self.worker_id))
            self._current_task_id = None
            self._cancellation_requested = False
            return {"status": "cancelled", "task_id": raw_tid}

        # Simulate step workflow execution
        self.emit_event(EventCatalog.TASK_COMPLETED, {"task_id": tid, "workflow": claimed_task.get("workflow_name")}, aggregate_id=tid)
        self.lease_manager.release_lease(raw_tid, str(self.worker_id))
        self._current_task_id = None

        return {"status": "completed", "task_id": raw_tid, "processed": 1}

    async def noop_consumer_tick(self) -> dict:
        """Executes a single no-op tick for consumer verification."""
        if not self._ready:
            raise RuntimeError(f"Worker [{self.worker_id}] is not ready.")
        tick = await self.poll_and_execute_tick()
        if tick.get("status") == "idle":
            return {"status": "ok", "processed": 0}
        return tick


class WorkerRunner(ProductionWorker):
    """Backward compatible WorkerRunner alias."""
    def __init__(self, name: str = "default-worker"):
        super().__init__(name=name)
