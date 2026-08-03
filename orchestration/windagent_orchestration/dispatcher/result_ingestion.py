"""
Result Ingestion Service for WindAgent Orchestration V2 Dispatcher.
Validates fencing tokens and ingests terminal execution results into durable storage.
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from windagent_orchestration.ports import (
    ExecutionRuntimePort, ExecutionHandle, ExecutionResult, RuntimeStatusEnum
)
from windagent_core.errors.exceptions import DomainError

logger = logging.getLogger("windagent.orchestration.dispatcher.result_ingestion")


class ResultIngestionService:
    def __init__(self, runtime_port: ExecutionRuntimePort, uow_factory: Optional[Any] = None):
        self.runtime_port = runtime_port
        self.uow_factory = uow_factory

    async def ingest_result(
        self,
        handle: ExecutionHandle,
        result: Optional[ExecutionResult] = None,
    ) -> ExecutionResult:
        if result is None:
            result = await self.runtime_port.get_result(handle)

        logger.info(f"Ingesting result for handle [{handle.handle_id}], step [{handle.step_run_id}], status [{result.status}]")

        if self.uow_factory:
            from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
            async with SqlUnitOfWork(self.uow_factory) as uow:
                if hasattr(uow, "runtime_executions"):
                    updated = await uow.runtime_executions.update_status_by_fencing_token(
                        step_run_id=handle.step_run_id,
                        fencing_token=handle.fencing_token,
                        status=result.status.value if isinstance(result.status, RuntimeStatusEnum) else str(result.status),
                        result_ref=result.result_ref,
                        error_metadata=result.error_metadata,
                    )
                    if not updated:
                        logger.warning(f"Rejected stale result submission for step [{handle.step_run_id}] with invalid fencing token [{handle.fencing_token}]")
                        raise DomainError(
                            message=f"Stale result submission rejected for step [{handle.step_run_id}] with fencing token [{handle.fencing_token}]",
                            code="WINDAGENT_ERR_STALE_FENCING_TOKEN",
                        )

                await uow.commit()

        return result
