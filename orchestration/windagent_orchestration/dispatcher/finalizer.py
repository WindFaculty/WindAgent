"""
Lease Finalizer Service for WindAgent Orchestration V2 Dispatcher.
Releases execution leases and notifies WorkflowEngine of step completion.
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from windagent_orchestration.dispatcher.leases import LeaseManager, ExecutionLease

logger = logging.getLogger("windagent.orchestration.dispatcher.finalizer")


class LeaseFinalizerService:
    def __init__(self, lease_manager: Optional[LeaseManager] = None):
        self.lease_manager = lease_manager or LeaseManager()

    async def finalize_step(
        self,
        lease: ExecutionLease,
        workflow_engine: Optional[Any] = None,
        is_success: bool = True,
        result_data: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        logger.info(f"Finalizing lease [{lease.lease_id}] for step [{lease.step_run_id}] (success={is_success})")
        await self.lease_manager.release_lease(lease.lease_id, lease.worker_id)

        if workflow_engine and hasattr(workflow_engine, "complete_node"):
            if is_success:
                await workflow_engine.complete_node(lease.run_id, lease.step_run_id, result_data)
            elif hasattr(workflow_engine, "fail_node"):
                await workflow_engine.fail_node(lease.run_id, lease.step_run_id, error or "Step execution failed")
