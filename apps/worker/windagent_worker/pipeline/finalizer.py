"""Finalizer stage for the Production Worker pipeline (Architecture V3 Phase 9).

The ONLY production authority that imports/uses ``SqlUnitOfWork``,
``FinalizeTaskExecutionRequest``, or calls ``finalize_task_execution``.  It
atomically persists task CAS/result/event/outbox/exact lease release in one
database transaction.  Runtime adapters and all other pipeline stages must not
commit task terminal state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from windagent_core.contracts.finalization import FinalizeTaskExecutionRequest
from windagent_core.events.catalog import EventCatalog
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

from windagent_worker.pipeline.context import TaskExecutionContext
from windagent_worker.pipeline.result_validator import ProposedOutcome


@dataclass
class FinalizeOutcome:
    """Result of the atomic finalization attempt."""

    finalized: bool
    request: Optional[Any] = None
    result: Optional[Any] = None


class FinalizerStage:
    """Atomic terminal persistence authority (Phase 2 / Phase 5 semantics)."""

    def __init__(self, uow_factory: Any = None) -> None:
        self.uow_factory = uow_factory

    async def finalize(
        self,
        ctx: TaskExecutionContext,
        outcome: ProposedOutcome,
    ) -> FinalizeOutcome:
        """Atomically persist task CAS/result/event/outbox/exact lease release.

        Raises ``RuntimeError`` when the finalizer rejects the request (stale
        CAS / wrong lease identity), propagating the rejection to the pipeline.
        """
        terminal_event = (
            EventCatalog.TASK_COMPLETED
            if outcome.terminal_state == "completed"
            else EventCatalog.TASK_FAILED
        )

        async with SqlUnitOfWork(self.uow_factory) as uow:
            existing = await uow.task_runs.get_by_id(ctx.task_id)
            expected_version = (existing or {}).get("version", 0) or 1

            req = FinalizeTaskExecutionRequest(
                task_id=ctx.task_id,
                worker_id=ctx.worker_id,
                lease_id=ctx.lease_id,
                fencing_token=ctx.fencing_token,
                expected_task_version=expected_version,
                execution_result=outcome.result_payload,
                result_artifacts=[],
                terminal_event={
                    "event_type": terminal_event.value
                    if hasattr(terminal_event, "value")
                    else terminal_event,
                    "task_id": ctx.task_id,
                    "status": outcome.terminal_state,
                    "error": outcome.terminal_error,
                },
                attempt_id=ctx.attempt_id,
                fencing_generation=ctx.lease_generation,
                terminal_state=outcome.terminal_state,
            )
            fin_res = await uow.finalize_task_execution(req)
            if fin_res.status != "COMPLETED":
                raise RuntimeError(f"Task finalization rejected: {fin_res.error_message}")

        ctx.finalized_at = datetime.now(timezone.utc)
        return FinalizeOutcome(finalized=True, request=req, result=fin_res)


__all__ = ["FinalizeOutcome", "FinalizerStage"]