"""
Cancellation Manager for WindAgent Orchestration Engine V2.
Manages durable cancellation requests and process tree propagation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Set, Optional

from windagent_core.errors.exceptions import DomainError
from windagent_core.contracts.repositories.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger("windagent.orchestration.cancellation")


class CancellationManager:
    def __init__(self, uow_factory: Optional[UnitOfWorkFactory] = None):
        self.uow_factory = uow_factory
        self._cancelled_runs: Set[str] = set()

    def request_cancellation(self, run_id: str) -> None:
        """Marks a task or workflow run for cancellation in memory."""
        self._cancelled_runs.add(run_id)
        logger.warning(f"Cancellation requested for run [{run_id}]")

    async def request_cancellation_durable(self, target_id: str, target_type: str = "task", reason: str = "user request") -> None:
        """Persists durable cancellation request in database and marks memory token."""
        self._cancelled_runs.add(target_id)
        if self.uow_factory:
            async with self.uow_factory() as uow:
                await uow.cancellations.request_cancellation(
                    req_id=str(uuid.uuid4()),
                    target_id=target_id,
                    target_type=target_type,
                    reason=reason,
                )
                await uow.commit()
        logger.warning(f"Durable cancellation recorded for [{target_type}:{target_id}] - reason: {reason}")

    async def is_cancelled_async(self, run_id: str) -> bool:
        if run_id in self._cancelled_runs:
            return True
        if self.uow_factory:
            async with self.uow_factory() as uow:
                is_canc = await uow.cancellations.is_cancelled(run_id)
                if is_canc:
                    self._cancelled_runs.add(run_id)
                return is_canc
        return False

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
