"""Reconciler stage for the Production Worker pipeline (Architecture V3 Phase 9).

Post-commit Studio DAG reconciliation only.  A reconciliation failure is
recoverable (StudioCompletionRecovery retries on worker start) and must never
roll back the already-committed terminal persistence.
"""

from __future__ import annotations

import logging
from typing import Any

from windagent_worker.pipeline.context import TaskExecutionContext
from windagent_worker.pipeline.result_validator import ProposedOutcome

logger = logging.getLogger("windagent.worker.pipeline.reconciler")


class ReconcilerStage:
    """Advance the Studio DAG after a committed terminal result; never rolls back."""

    async def reconcile(
        self,
        ctx: TaskExecutionContext,
        outcome: ProposedOutcome,
        *,
        studio_reconciler: Any,
    ) -> bool:
        """Reconcile a committed Studio result into the DAG.

        Returns True when reconciliation ran successfully.  Failures are logged
        and swallowed (recoverable) so the terminal persistence stays intact.
        """
        if studio_reconciler is None or outcome.studio_result is None:
            return False
        try:
            await studio_reconciler.reconcile(outcome.studio_result)
            return True
        except Exception as ex:
            logger.warning(
                f"Studio reconcile failed for task [{ctx.task_id}] (recovery will retry): {ex}"
            )
            return False


__all__ = ["ReconcilerStage"]