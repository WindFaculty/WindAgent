"""Claim stage for the Production Worker pipeline (Architecture V3 Phase 9).

Claims the next pending/abandoned task from the durable queue port or the
legacy lease manager and normalizes it into a ``TaskExecutionContext``.
This stage performs no execution and no finalization.
"""

from __future__ import annotations

from typing import Any, Optional

from windagent_worker.pipeline.context import TaskExecutionContext


class ClaimStage:
    """Claims and normalizes the next task; never executes or finalizes."""

    async def claim(
        self,
        *,
        task_queue: Any,
        lease_manager: Any,
        worker_id: str,
    ) -> Optional[TaskExecutionContext]:
        """Claim the next task via the durable queue or legacy lease manager.

        Returns ``None`` when nothing is claimable (idle tick).
        """
        claimed: Any = None
        if task_queue is not None:
            claimed = await task_queue.claim_next(worker_id)
        elif lease_manager is not None:
            claimed = lease_manager.claim_task(worker_id)

        if not claimed:
            return None
        return TaskExecutionContext.from_claim(claimed, worker_id=worker_id)


__all__ = ["ClaimStage"]