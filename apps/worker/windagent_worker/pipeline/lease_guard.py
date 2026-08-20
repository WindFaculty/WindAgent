"""Lease guard stage for the Production Worker pipeline (Architecture V3 Phase 9).

Renews, releases, and probes the exact task/worker/fencing-token lease.
Supports the async durable queue port and the sync legacy lease manager.
This stage never commits task state.
"""

from __future__ import annotations

import inspect
from typing import Any

from windagent_worker.pipeline.context import TaskExecutionContext


class LeaseGuardStage:
    """Renew/release/probe the exact claimed lease; no task-state commit."""

    async def renew(
        self,
        ctx: TaskExecutionContext,
        *,
        task_queue: Any,
        lease_manager: Any,
    ) -> bool:
        """Renew the exact lease.  Returns False on fencing mismatch/takeover."""
        if task_queue is not None and hasattr(task_queue, "renew"):
            return bool(await task_queue.renew(ctx.raw_task_id, ctx.worker_id, ctx.fencing_token))
        if lease_manager is not None:
            result = lease_manager.renew_lease(
                ctx.raw_task_id,
                ctx.worker_id,
                fencing_token=ctx.fencing_token,
            )
            if inspect.isawaitable(result):
                return bool(await result)
            return bool(result)
        return False

    async def check_authority(
        self,
        ctx: TaskExecutionContext,
        *,
        task_queue: Any,
        lease_manager: Any,
    ) -> bool:
        """Probe whether this worker still holds the current durable lease.

        Uses the exact-token renew as the authority/CAS probe: if the durable
        lease was taken over by another worker (or released/expired), the
        renew is rejected and this worker is no longer the authority for the
        result.  The pipeline runs this immediately after execution returns
        and before result validation/finalization so a late result from a
        stale owner is rejected before any terminal mutation.
        """
        return await self.renew(ctx, task_queue=task_queue, lease_manager=lease_manager)

    async def release(
        self,
        ctx: TaskExecutionContext,
        *,
        task_queue: Any,
        lease_manager: Any,
    ) -> bool:
        """Release the exact lease.  Returns False on fencing mismatch."""
        if task_queue is not None and hasattr(task_queue, "release"):
            return bool(await task_queue.release(ctx.raw_task_id, ctx.worker_id, ctx.fencing_token))
        if lease_manager is not None:
            result = lease_manager.release_lease(
                ctx.raw_task_id,
                ctx.worker_id,
                fencing_token=ctx.fencing_token,
            )
            if inspect.isawaitable(result):
                return bool(await result)
            return bool(result)
        return False


__all__ = ["LeaseGuardStage"]