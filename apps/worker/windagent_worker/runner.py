"""
Background Production Worker for WindAgent Architecture V2 (Phase 7 - Process-specific composition).
Handles task claims, heartbeat lease renewal with fencing tokens, execution dispatch via ExecutionRuntimeRegistry,
cancellation propagation, step checkpointing, and deterministic crash recovery.
Uses canonical WorkerId, RuntimeRunId, TaskState, TaskLifecycle, and EventEnvelope.

Worker runs as INDEPENDENT process with its own composition root.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncio
from windagent_core.contracts.workers import WorkerHeartbeat, WorkerHealth
from windagent_core.domain.types import WorkerId, RuntimeRunId, TaskId, EventId
from windagent_core.domain.lifecycle import TaskState, TaskLifecycle, utc_now
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.contracts.execution import ExecutionRequest, RuntimeStatusEnum
from windagent_core.errors.exceptions import DomainError
from windagent_worker.composition import WorkerContainer
from windagent_worker.lease import DurableTaskLeaseManager
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_execution.results import ExecutionResultHandler
from windagent_execution.cancellation import CancellationBroadcaster

logger = logging.getLogger("windagent.worker")


class ProductionWorker:
    """Production Worker handling durable task claim, lease heartbeat, execution dispatch, fencing, and cancellation.

    Uses WorkerContainer for process-specific composition (PHASE 7).
    Worker runs INDEPENDENTLY from API and Desktop processes.
    """

    def __init__(
        self,
        name: str = "default-worker",
        worker_container: Optional[WorkerContainer] = None,
        lease_manager: Optional[DurableTaskLeaseManager] = None,
        task_queue: Optional[Any] = None,
        heartbeat_repo: Optional[Any] = None,
        execution_registry: Optional[ExecutionRuntimeRegistry] = None,
        uow_factory: Optional[Any] = None,
        heartbeat_interval_sec: float = 5.0,
    ):
        self.name = name
        self.worker_id = WorkerId(f"wkr_{name}")
        self.runtime_run_id = RuntimeRunId.generate()
        self.worker_container = worker_container
        self.task_queue = task_queue or (worker_container.task_queue if worker_container else None)
        self.lease_manager = lease_manager or (worker_container.lease_manager if worker_container else None)
        self.heartbeat_repo = heartbeat_repo or (worker_container.heartbeat_repo if worker_container else None)
        self.execution_registry = execution_registry or (worker_container.execution_registry if worker_container else ExecutionRuntimeRegistry())
        self.cancellation_broadcaster = CancellationBroadcaster()
        self.uow_factory = uow_factory or (worker_container.uow_factory if worker_container else None)
        self.heartbeat_interval_sec = heartbeat_interval_sec
        self._running = False
        self._ready = False
        self._heartbeat_task: Optional[asyncio.Task] = None
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
        if self.worker_container and self.worker_container.outbox_publisher:
            if not self.worker_container.outbox_publisher.is_running:
                raise RuntimeError("Outbox publisher must be running before worker becomes ready.")
        if self.worker_container and self.worker_container.orchestration_container:
            await self.worker_container.orchestration_container.recovery_manager.recover_all_in_flight()
        self._running = True
        self._ready = True
        self._cancellation_requested = False
        await self.record_heartbeat()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Production Worker [{self.worker_id}] ready.")

    async def stop(self) -> None:
        logger.info(f"Stopping Production Worker [{self.worker_id}]...")
        self._ready = False
        self._running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._current_task_id:
            if self.task_queue is not None and hasattr(self.task_queue, "release"):
                await self.task_queue.release(str(self._current_task_id), str(self.worker_id), self._current_fencing_token)
            elif self.lease_manager is not None:
                await self.lease_manager.release_lease(
                    str(self._current_task_id),
                    str(self.worker_id),
                    fencing_token=self._current_fencing_token,
                )
            self._current_task_id = None
            self._current_fencing_token = None
        logger.info(f"Production Worker [{self.worker_id}] stopped.")

    async def record_heartbeat(self) -> None:
        """Records worker heartbeat into SQL repository and renews active task lease."""
        active_leases = 1 if self._current_task_id else 0
        hb = WorkerHeartbeat(
            worker_id=str(self.worker_id),
            runtime_type="production_worker",
            health=WorkerHealth.HEALTHY,
            active_leases=active_leases,
            last_heartbeat_at=datetime.now(timezone.utc),
            metadata={"runtime_run_id": str(self.runtime_run_id)},
        )
        if self.heartbeat_repo is not None and hasattr(self.heartbeat_repo, "record_heartbeat"):
            try:
                await self.heartbeat_repo.record_heartbeat(hb)
            except Exception as ex:
                logger.warning(f"Error recording worker heartbeat: {ex}")

        if self._current_task_id and self._current_fencing_token:
            renewed = False
            if self.task_queue is not None and hasattr(self.task_queue, "renew"):
                renewed = await self.task_queue.renew(
                    str(self._current_task_id),
                    str(self.worker_id),
                    self._current_fencing_token,
                )
            elif self.lease_manager is not None:
                renewed = await self.lease_manager.renew_lease(
                    str(self._current_task_id),
                    str(self.worker_id),
                    fencing_token=self._current_fencing_token,
                )

            if not renewed:
                logger.warning(
                    f"Heartbeat lease renewal failed for task [{self._current_task_id}]: "
                    "fencing token mismatch or takeover. Cancelling task execution."
                )
                await self.cancel()

    async def _heartbeat_loop(self) -> None:
        """Background periodic heartbeat execution loop."""
        while self._running:
            try:
                await self.record_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.warning(f"Error in worker heartbeat loop: {ex}")
            try:
                await asyncio.sleep(self.heartbeat_interval_sec)
            except asyncio.CancelledError:
                break

    async def cancel(self) -> None:
        """Triggers cancellation signal for current executing task."""
        logger.warning(f"Signalling task cancellation on Worker [{self.worker_id}]...")
        self._cancellation_requested = True
        if self._current_task_id:
            await self.cancellation_broadcaster.cancel_step(str(self._current_task_id))

    def emit_event(self, event_type: EventCatalog | str, payload: Dict[str, Any], aggregate_id: str = "worker") -> EventEnvelope:
        """Creates a diagnostic / domain-intent EventEnvelope stored in the in-memory observer list.

        DURABILITY SEPARATION (ban_ke_hoach.md §2.4):
        - ``_emitted_envelopes`` is a **diagnostic observer** — NOT a durable source of truth.
        - This method is safe to call for in-process event intent signaling and test observation.
        - Terminal task events (task_completed, task_failed) MUST be written atomically through
          ``SqlUnitOfWork.finalize_task_execution()``, which persists them in the EventStore and
          Outbox within a single database transaction.
        - Calling ``emit_event()`` alone does NOT guarantee durability of the event.
        """
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
        self._emitted_envelopes.append(env)  # diagnostic observer only — not durable
        logger.info(f"Worker [{self.worker_id}] emitted EventEnvelope seq={env.sequence}")
        return env

    async def poll_and_execute_tick(self) -> Dict[str, Any]:
        """Performs a single worker poll-claim-execute-heartbeat tick with fencing token check."""
        if not self._ready:
            raise RuntimeError(f"Worker [{self.worker_id}] is not ready.")

        # Try to claim pending or abandoned task via durable queue port or lease manager
        claimed: Any = None
        if self.task_queue is not None:
            claimed = await self.task_queue.claim_next(str(self.worker_id))
        elif self.lease_manager is not None:
            claimed = self.lease_manager.claim_task(str(self.worker_id))

        if not claimed:
            return {"status": "idle", "processed": 0}

        if hasattr(claimed, "task_id"):
            raw_tid = str(claimed.task_id)
            fencing_token = claimed.fencing_token
            tool_name = claimed.tool_name
            prompt = claimed.prompt
        else:
            raw_tid = str(claimed["task_id"])
            fencing_token = claimed.get("fencing_token", f"fence_{raw_tid}_gen_1")
            tool_name = claimed.get("tool_name", "read_file")
            prompt = claimed.get("prompt", "")

        try:
            tid = str(TaskId(raw_tid))
        except Exception:
            tid = raw_tid

        self._current_task_id = tid
        self._current_fencing_token = fencing_token
        self.emit_event(EventCatalog.TASK_CREATED, {"task_id": tid, "worker_id": str(self.worker_id)}, aggregate_id=tid)

        # Heartbeat lease renewal with fencing token validation
        renewed = False
        if self.task_queue is not None and hasattr(self.task_queue, "renew"):
            renewed = await self.task_queue.renew(raw_tid, str(self.worker_id), fencing_token)
        elif self.lease_manager is not None:
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
            if self.task_queue is not None and hasattr(self.task_queue, "release"):
                await self.task_queue.release(raw_tid, str(self.worker_id), fencing_token)
            elif self.lease_manager is not None:
                self.lease_manager.release_lease(raw_tid, str(self.worker_id), fencing_token=fencing_token)
            self._current_task_id = None
            self._current_fencing_token = None
            self._cancellation_requested = False
            return {"status": "cancelled", "task_id": raw_tid}

        # Execute step via ExecutionRuntimeRegistry
        exec_req = ExecutionRequest(
            step_run_id=tid,
            workflow_run_id=f"wf_{tid}",
            tool_name=tool_name,
            parameters={"task_id": tid, "prompt": prompt},
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
            if self.task_queue is not None and hasattr(self.task_queue, "release"):
                await self.task_queue.release(raw_tid, str(self.worker_id), fencing_token)
            elif self.lease_manager is not None:
                self.lease_manager.release_lease(raw_tid, str(self.worker_id), fencing_token=fencing_token)
            self._current_task_id = None
            self._current_fencing_token = None
            return {"status": "fencing_violation", "task_id": raw_tid, "error": str(err)}

        # Diagnostic emit: records intent in the in-memory observer list ONLY.
        # The durable terminal event is written atomically inside finalize_task_execution() below.
        self.emit_event(
            EventCatalog.TASK_COMPLETED,
            {"task_id": tid, "status": validated_result.status.value},
            aggregate_id=tid,
        )

        # ------------------------------------------------------------------ #
        # Atomic Task Finalization (Phase 2 — ban_ke_hoach.md §2.1):
        # Task state CAS, result, artifact refs, terminal event, transactional
        # outbox, AND lease release all commit in ONE database transaction.
        # Lease MUST NOT be released separately after this block — doing so
        # would be a double release violating §2.1 and §2.3.
        # ------------------------------------------------------------------ #
        finalized_via_uow = False
        if self.uow_factory is not None:
            from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
            from windagent_core.contracts.finalization import FinalizeTaskExecutionRequest

            async with SqlUnitOfWork(self.uow_factory) as uow:
                existing = await uow.task_runs.get_by_id(tid)
                expected_version = (existing or {}).get("version", 0) or 1

                req = FinalizeTaskExecutionRequest(
                    task_id=tid,
                    worker_id=str(self.worker_id),
                    lease_id=str(self._current_task_id),
                    fencing_token=fencing_token,
                    expected_task_version=expected_version,
                    execution_result=dict(validated_result.result_data or {}),
                    result_artifacts=[],
                    terminal_event={
                        "event_type": EventCatalog.TASK_COMPLETED.value if hasattr(EventCatalog.TASK_COMPLETED, "value") else "task_completed",
                        "task_id": tid,
                        "status": validated_result.status.value,
                    },
                    attempt_id="att_1",
                    fencing_generation=1,
                    terminal_state="completed",
                )
                fin_res = await uow.finalize_task_execution(req)
                if fin_res.status != "COMPLETED":
                    raise RuntimeError(f"Task finalization rejected: {fin_res.error_message}")

            # Lease was released atomically inside the transaction above.
            # Do NOT call task_queue.release() again — that would be a double release.
            finalized_via_uow = True

        if not finalized_via_uow:
            # Fallback: no UoW factory configured (e.g. test/legacy mode without persistent DB).
            # Release lease manually only when atomic finalization was NOT used.
            if self.task_queue is not None and hasattr(self.task_queue, "release"):
                await self.task_queue.release(raw_tid, str(self.worker_id), fencing_token)
            elif self.lease_manager is not None:
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
