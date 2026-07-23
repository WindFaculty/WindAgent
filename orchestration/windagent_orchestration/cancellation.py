"""
Cancellation Manager for WindAgent Orchestration Engine.
Manages graceful and immediate cancellation tokens for running tasks and workflow steps.
"""

from __future__ import annotations
import logging
from typing import Set

from windagent_core.errors.exceptions import DomainError

logger = logging.getLogger("windagent.orchestration.cancellation")


class CancellationManager:
    def __init__(self):
        self._cancelled_runs: Set[str] = set()

    def request_cancellation(self, run_id: str) -> None:
        """Marks a task or workflow run for cancellation."""
        self._cancelled_runs.add(run_id)
        logger.warning(f"Cancellation requested for run [{run_id}]")

    def is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled_runs

    def raise_if_cancelled(self, run_id: str) -> None:
        if self.is_cancelled(run_id):
            raise DomainError(
                message=f"Execution of run [{run_id}] was cancelled by user or system.",
                code="WINDAGENT_ERR_TASK_CANCELLED",
                details={"run_id": run_id},
            )

    def clear(self, run_id: str) -> None:
        self._cancelled_runs.discard(run_id)
