"""Task execution pipeline for the Production Worker (Architecture V3 Phase 9).

``TaskExecutionPipeline`` explicitly orchestrates the independently testable
stages:

    claim -> lease_guard -> executor -> result_validator -> finalizer
          -> reconciler -> release

It owns stage ordering, diagnostic events, current-task clearing before the
atomic lease release, the fallback manual release (only when no UoW exists),
and the exact external response/metrics compatibility of the legacy
``poll_and_execute_tick``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from windagent_core.events.catalog import EventCatalog

from windagent_worker.pipeline.claim import ClaimStage
from windagent_worker.pipeline.context import TaskExecutionContext
from windagent_worker.pipeline.executor import ExecutorStage
from windagent_worker.pipeline.finalizer import FinalizerStage
from windagent_worker.pipeline.lease_guard import LeaseGuardStage
from windagent_worker.pipeline.reconciler import ReconcilerStage
from windagent_worker.pipeline.result_validator import ResultValidatorStage

logger = logging.getLogger("windagent.worker.pipeline")


class TaskExecutionPipeline:
    """Orchestrates one worker poll-claim-execute-finalize tick."""

    def __init__(
        self,
        *,
        worker_id: str,
        task_queue: Any = None,
        lease_manager: Any = None,
        execution_registry: Any = None,
        cancellation_broadcaster: Any = None,
        uow_factory: Any = None,
        studio_reconciler: Any = None,
        emit_event: Optional[Callable[..., Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        set_current_task: Optional[Callable[[str, str], None]] = None,
        clear_current_task: Optional[Callable[[], None]] = None,
        cancellation_requested: Optional[Callable[[], bool]] = None,
        reset_cancellation: Optional[Callable[[], None]] = None,
    ) -> None:
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.lease_manager = lease_manager
        self.execution_registry = execution_registry
        self.cancellation_broadcaster = cancellation_broadcaster
        self.uow_factory = uow_factory
        self.studio_reconciler = studio_reconciler
        self._emit_event = emit_event or (lambda *args, **kwargs: None)
        self.metrics = metrics if metrics is not None else {
            "tasks": {},
            "totals": {"processed": 0, "failed": 0},
        }
        self._set_current_task = set_current_task or (lambda task_id, token: None)
        self._clear_current_task = clear_current_task or (lambda: None)
        self._cancellation_requested = cancellation_requested or (lambda: False)
        self._reset_cancellation = reset_cancellation or (lambda: None)

        self.claim_stage = ClaimStage()
        self.lease_guard = LeaseGuardStage()
        self.executor = ExecutorStage()
        self.result_validator = ResultValidatorStage()
        self.finalizer = FinalizerStage(uow_factory)
        self.reconciler = ReconcilerStage()

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _queue_wait_ms(ctx: TaskExecutionContext) -> int:
        if ctx.claimed_at is None:
            return 0
        return max(
            0,
            int((datetime.now(timezone.utc) - ctx.claimed_at).total_seconds() * 1000),
        )

    @staticmethod
    def _elapsed_ms(started_at: datetime) -> int:
        return max(0, int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000))

    # ------------------------------------------------------------------ #
    # tick
    # ------------------------------------------------------------------ #

    async def run_tick(self) -> Dict[str, Any]:
        """Run one full poll-claim-execute-finalize tick."""
        ctx = await self.claim_stage.claim(
            task_queue=self.task_queue,
            lease_manager=self.lease_manager,
            worker_id=self.worker_id,
        )
        if ctx is None:
            return {"status": "idle", "processed": 0}

        self._set_current_task(ctx.task_id, ctx.fencing_token)
        self._emit_event(
            EventCatalog.TASK_CREATED,
            {"task_id": ctx.task_id, "worker_id": self.worker_id},
            aggregate_id=ctx.task_id,
        )

        # Redaction-safe metric capture (ids/durations/status only).
        ctx.started_at = datetime.now(timezone.utc)
        ctx.metric = {
            "task_id": ctx.task_id,
            "task_type": ctx.tool_name,
            "attempt": ctx.attempt,
            "queue_wait_ms": self._queue_wait_ms(ctx),
            "status": "claimed",
        }

        # Heartbeat lease renewal with fencing token validation.
        renewed = await self.lease_guard.renew(
            ctx,
            task_queue=self.task_queue,
            lease_manager=self.lease_manager,
        )
        if not renewed:
            self._clear_current_task()
            return {"status": "lease_error", "task_id": ctx.raw_task_id}

        # Check for cancellation signal.
        if self._cancellation_requested():
            self._emit_event(
                EventCatalog.TASK_CANCELLED,
                {"task_id": ctx.task_id},
                aggregate_id=ctx.task_id,
            )
            await self.lease_guard.release(
                ctx,
                task_queue=self.task_queue,
                lease_manager=self.lease_manager,
            )
            self._clear_current_task()
            self._reset_cancellation()
            return {"status": "cancelled", "task_id": ctx.raw_task_id}

        # Execute step via ExecutionRuntimeRegistry.
        await self.executor.execute(
            ctx,
            execution_registry=self.execution_registry,
            cancellation_broadcaster=self.cancellation_broadcaster,
        )
        ctx.metric["execution_ms"] = self._elapsed_ms(ctx.started_at)

        # Current-lease authority check: the already-dispatched handle still
        # carries A's original token, so the handle-token validator below
        # cannot detect a durable takeover.  Probe the durable lease with the
        # exact token (renew as the authority/CAS probe) immediately after
        # execution returns and before result validation/finalization.  If A's
        # exact task/worker/fencing token is no longer current, the late result
        # is rejected BEFORE any terminal event, validator, finalizer,
        # reconciler, or terminal metric mutation.
        if not await self.lease_guard.check_authority(
            ctx,
            task_queue=self.task_queue,
            lease_manager=self.lease_manager,
        ):
            # A stale-token release attempt stays harmless/fail-closed: the
            # durable lease is owned by the new worker (or already released),
            # so releasing with A's token is a no-op that never touches the
            # current owner's lease.
            await self.lease_guard.release(
                ctx,
                task_queue=self.task_queue,
                lease_manager=self.lease_manager,
            )
            self._clear_current_task()
            return {
                "status": "fencing_violation",
                "task_id": ctx.raw_task_id,
                "error": (
                    f"LEASE_TAKEOVER: worker [{self.worker_id}] no longer holds "
                    f"the current durable lease for task [{ctx.raw_task_id}] "
                    f"(fencing token {ctx.fencing_token} is stale)"
                ),
            }

        # Validate fencing token before committing result.
        outcome = await self.result_validator.validate(ctx)
        if outcome.fencing_rejected:
            logger.error(
                f"Late result rejected due to fencing token error: {outcome.rejection_error}"
            )
            await self.lease_guard.release(
                ctx,
                task_queue=self.task_queue,
                lease_manager=self.lease_manager,
            )
            self._clear_current_task()
            return {
                "status": "fencing_violation",
                "task_id": ctx.raw_task_id,
                "error": outcome.rejection_error,
            }

        terminal_event = (
            EventCatalog.TASK_COMPLETED
            if outcome.terminal_state == "completed"
            else EventCatalog.TASK_FAILED
        )

        # Diagnostic emit: records intent in the in-memory observer list ONLY.
        # The durable terminal event is written atomically by the finalizer stage.
        self._emit_event(
            terminal_event,
            {"task_id": ctx.task_id, "status": outcome.terminal_state},
            aggregate_id=ctx.task_id,
        )

        # Execution is over. Stop advertising/renewing the active lease before
        # atomic finalization releases it, otherwise a concurrent heartbeat can
        # observe the intentional release as a fencing takeover and poison the
        # next task with a spurious cancellation request.
        self._clear_current_task()

        # ------------------------------------------------------------------ #
        # Atomic Task Finalization (Phase 2 — ban_ke_hoach.md §2.1):
        # Task state CAS, result, artifact refs, terminal event, transactional
        # outbox, AND lease release all commit in ONE database transaction.
        # Lease MUST NOT be released separately after this block — doing so
        # would be a double release violating §2.1 and §2.3.
        # ------------------------------------------------------------------ #
        finalized_via_uow = False
        if self.uow_factory is not None:
            await self.finalizer.finalize(ctx, outcome)
            finalized_via_uow = True
            ctx.metric["finalize_ms"] = self._elapsed_ms(ctx.started_at)
            ctx.metric["status"] = outcome.terminal_state
            self.metrics["tasks"][ctx.task_id] = ctx.metric
            if outcome.terminal_state == "failed":
                self.metrics["totals"]["failed"] = self.metrics["totals"].get("failed", 0) + 1
            else:
                self.metrics["totals"]["processed"] = self.metrics["totals"].get("processed", 0) + 1

            # Studio completion: advance the DAG ONLY through the reconciler.
            # A crash between the finalizer commit above and this call is
            # covered by StudioCompletionRecovery on worker start.
            reconciled = await self.reconciler.reconcile(
                ctx,
                outcome,
                studio_reconciler=self.studio_reconciler,
            )
            if reconciled:
                ctx.metric["reconciled"] = True

        if not finalized_via_uow:
            # Fallback: no UoW factory configured (e.g. test/legacy mode without
            # persistent DB). Release lease manually only when atomic
            # finalization was NOT used.
            await self.lease_guard.release(
                ctx,
                task_queue=self.task_queue,
                lease_manager=self.lease_manager,
            )

        self._clear_current_task()

        response = {"status": outcome.terminal_state, "task_id": ctx.raw_task_id, "processed": 1}
        if outcome.terminal_error:
            response["error"] = outcome.terminal_error
        return response


__all__ = ["TaskExecutionPipeline"]