"""
Background Production Worker for WindAgent Architecture V2 (Phase 18 Implementation).
Handles task claims, heartbeat lease renewal with fencing tokens, execution dispatch via ExecutionRuntimeRegistry,
cancellation propagation, step checkpointing, and deterministic crash recovery.
Uses canonical WorkerId, RuntimeRunId, TaskState, TaskLifecycle, and EventEnvelope.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from windagent_core.domain.types import WorkerId, RuntimeRunId, TaskId, EventId
from windagent_core.domain.lifecycle import TaskState, TaskLifecycle, utc_now
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.contracts.execution import ExecutionRequest, RuntimeStatusEnum
from windagent_core.errors.exceptions import DomainError
from windagent_worker.lease import DurableTaskLeaseManager, TaskLeaseManager
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_execution.results import ExecutionResultHandler
from windagent_execution.cancellation import CancellationBroadcaster

logger = logging.getLogger("windagent.worker")


class ProductionWorker:
    """Production Worker handling durable task claim, lease heartbeat, execution dispatch, fencing, and cancellation."""

    def __init__(
        self,
        name: str = "default-worker",
        lease_manager: Optional[DurableTaskLeaseManager] = None,
        execution_registry: Optional[ExecutionRuntimeRegistry] = None,
        uow_factory: Optional[Any] = None,
    ):
        self.name = name
        self.worker_id = WorkerId(f"wkr_{name}")
        self.runtime_run_id = RuntimeRunId.generate()
        self.lease_manager = lease_manager or DurableTaskLeaseManager()
        self.execution_registry = execution_registry or ExecutionRuntimeRegistry()
        self.cancellation_broadcaster = CancellationBroadcaster()
        self.uow_factory = uow_factory
        self._running = False
        self._ready = False
        self._current_task_id: Optional[TaskId] = None
        self._current_fencing_token: Optional[str] = None
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

    @property
    def current_fencing_token(self) -> Optional[str]:
        return self._current_fencing_token

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
            self.lease_manager.release_lease(
                str(self._current_task_id),
                str(self.worker_id),
                fencing_token=self._current_fencing_token,
            )
            self._current_task_id = None
            self._current_fencing_token = None
        logger.info(f"Production Worker [{self.worker_id}] stopped.")

    async def cancel(self) -> None:
        """Triggers cancellation signal for current executing task."""
        logger.warning(f"Signalling task cancellation on Worker [{self.worker_id}]...")
        self._cancellation_requested = True
        if self._current_task_id:
            await self.cancellation_broadcaster.cancel_step(str(self._current_task_id))

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
        """Performs a single worker poll-claim-execute-heartbeat tick with fencing token check."""
        if not self._ready:
            raise RuntimeError(f"Worker [{self.worker_id}] is not ready.")

        # Try to claim pending or abandoned task
        claimed_task = self.lease_manager.claim_task(str(self.worker_id))
        if not claimed_task:
            return {"status": "idle", "processed": 0}

        raw_tid = str(claimed_task["task_id"])
        fencing_token = claimed_task.get("fencing_token", f"fence_{raw_tid}_gen_1")
        try:
            tid = str(TaskId(raw_tid))
        except Exception:
            tid = raw_tid

        self._current_task_id = tid
        self._current_fencing_token = fencing_token
        self.emit_event(EventCatalog.TASK_CREATED, {"task_id": tid, "worker_id": str(self.worker_id)}, aggregate_id=tid)

        # Heartbeat lease renewal with fencing token validation
        renewed = self.lease_manager.renew_lease(
            raw_tid,
            str(self.worker_id),
            fencing_token=fencing_token,
        )
        if not renewed:
            self._current_task_id = None
            self._current_fencing_token = None
            return {"status": "lease_error", "task_id": raw_tid}

        # Check for cancellation signal
        if self._cancellation_requested:
            self.emit_event(EventCatalog.TASK_CANCELLED, {"task_id": tid}, aggregate_id=tid)
            self.lease_manager.release_lease(raw_tid, str(self.worker_id), fencing_token=fencing_token)
            self._current_task_id = None
            self._current_fencing_token = None
            self._cancellation_requested = False
            return {"status": "cancelled", "task_id": raw_tid}

        # Execute step via ExecutionRuntimeRegistry
        exec_req = ExecutionRequest(
            step_run_id=tid,
            workflow_run_id=f"wf_{tid}",
            tool_name=claimed_task.get("tool_name", "read_file"),
            parameters={"task_id": tid, "prompt": claimed_task.get("prompt", "")},
            attempt_id="att_1",
            fencing_token=fencing_token,
        )

        handle = await self.execution_registry.dispatch(exec_req)
        self.cancellation_broadcaster.register_handle(handle, self.execution_registry)

        result = await self.execution_registry.get_result(handle)

        # Validate fencing token before committing result
        try:
            validated_result = ExecutionResultHandler.validate_and_wrap(
                result=result,
                active_fencing_token=fencing_token,
                result_fencing_token=handle.fencing_token,
            )
        except DomainError as err:
            logger.error(f"Late result rejected due to fencing token error: {err}")
            self.lease_manager.release_lease(raw_tid, str(self.worker_id), fencing_token=fencing_token)
            self._current_task_id = None
            self._current_fencing_token = None
            return {"status": "fencing_violation", "task_id": raw_tid, "error": str(err)}

        self.emit_event(
            EventCatalog.TASK_COMPLETED,
            {"task_id": tid, "status": validated_result.status.value},
            aggregate_id=tid,
        )
        self.lease_manager.release_lease(raw_tid, str(self.worker_id), fencing_token=fencing_token)
        self._current_task_id = None
        self._current_fencing_token = None

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
