"""
Step Dispatcher Orchestrator for WindAgent Orchestration Engine V2.
Coordinates atomic step claim, runtime dispatch, execution monitoring, result ingestion, and lease finalization.
"""

from __future__ import annotations

import logging
from typing import Set, Tuple, Optional, Any, Dict

from windagent_core.domain.models import WorkflowStep
from windagent_orchestration.ports import ExecutionRuntimePort, ExecutionHandle, ExecutionResult, RuntimeStatusEnum
from windagent_orchestration.dispatcher.leases import LeaseManager, ExecutionLease
from windagent_orchestration.dispatcher.worker_registry import WorkerRegistry
from windagent_orchestration.dispatcher.claim import StepClaimService
from windagent_orchestration.dispatcher.dispatch import StepDispatchService
from windagent_orchestration.dispatcher.monitor import ExecutionMonitorService
from windagent_orchestration.dispatcher.result_ingestion import ResultIngestionService
from windagent_orchestration.dispatcher.finalizer import LeaseFinalizerService
from windagent_execution.adapters.fake_runtime_adapter import FakeRuntimeAdapter

logger = logging.getLogger("windagent.orchestration.dispatcher")


class StepDispatcher:
    def __init__(
        self,
        lease_manager: Optional[LeaseManager] = None,
        worker_registry: Optional[WorkerRegistry] = None,
        runtime_port: Optional[ExecutionRuntimePort] = None,
        uow_factory: Optional[Any] = None,
    ):
        self.lease_manager = lease_manager or LeaseManager(uow_factory=uow_factory)
        self.worker_registry = worker_registry or WorkerRegistry()
        self.runtime_port = runtime_port or FakeRuntimeAdapter()
        self.uow_factory = uow_factory

        self.claim_service = StepClaimService(self.lease_manager)
        self.dispatch_service = StepDispatchService(self.runtime_port, uow_factory=self.uow_factory)
        self.monitor_service = ExecutionMonitorService(self.runtime_port)
        self.ingestion_service = ResultIngestionService(self.runtime_port, uow_factory=self.uow_factory)
        self.finalizer_service = LeaseFinalizerService(self.lease_manager)

    async def dispatch_step_durable(
        self,
        run_id: str,
        step: WorkflowStep,
        worker_id: str = "default_worker",
        ttl_seconds: float = 30.0,
        workflow_engine: Optional[Any] = None,
    ) -> bool:
        """Durable step dispatch pipeline executing:
        claim -> dispatch -> monitor/ingest -> finalize
        """
        step_id_str = str(step.id)

        # 1. Claim step atomically
        lease = await self.claim_service.claim_step(
            step_run_id=step_id_str,
            run_id=run_id,
            worker_id=worker_id,
            ttl_seconds=ttl_seconds,
        )
        if not lease:
            logger.warning(f"Failed to claim lease for run [{run_id}], step [{step_id_str}]")
            return False

        # 2. Dispatch to execution runtime
        tool_name = getattr(step, "tool_name", "noop")
        parameters = getattr(step, "parameters", {})
        handle = await self.dispatch_service.dispatch_to_runtime(
            lease=lease,
            tool_name=tool_name,
            parameters=parameters,
        )

        # 3. Ingest terminal result
        result = await self.ingestion_service.ingest_result(handle)

        # 4. Finalize lease and notify engine
        is_success = result.status == RuntimeStatusEnum.COMPLETED
        await self.finalizer_service.finalize_step(
            lease=lease,
            workflow_engine=workflow_engine,
            is_success=is_success,
            result_data=result.result_data,
            error=result.error,
        )

        return is_success
