"""
Step Dispatcher Service for WindAgent Orchestration Engine V2.
Dispatches workflow steps to workers using atomic execution leases, idempotency keys, and worker registries.
"""

from __future__ import annotations

import logging
from typing import Set, Tuple, Optional, Any

from windagent_core.domain.models import WorkflowStep
from windagent_orchestration.dispatcher.leases import LeaseManager
from windagent_orchestration.dispatcher.worker_registry import WorkerRegistry

logger = logging.getLogger("windagent.orchestration.dispatcher")


class StepDispatcher:
    def __init__(self, lease_manager: Optional[LeaseManager] = None, worker_registry: Optional[WorkerRegistry] = None):
        self.lease_manager = lease_manager or LeaseManager()
        self.worker_registry = worker_registry or WorkerRegistry()
        self._dispatched: Set[Tuple[str, str]] = set()

    def is_dispatched(self, run_id: str, step_id: str) -> bool:
        return (run_id, step_id) in self._dispatched

    def dispatch_step(self, run_id: str, step: WorkflowStep) -> bool:
        """In-memory step dispatch check (backwards compatibility)."""
        key = (run_id, str(step.id))
        if key in self._dispatched:
            logger.warning(f"Prevented duplicate step dispatch for run [{run_id}], step [{step.id}]")
            return False

        self._dispatched.add(key)
        logger.info(f"Dispatched step [{step.name}] (tool: {step.tool_name}) for run [{run_id}]")
        return True

    async def dispatch_step_durable(
        self,
        run_id: str,
        step: WorkflowStep,
        worker_id: str = "default_worker",
        ttl_seconds: float = 30.0,
    ) -> bool:
        """Durable step dispatch check with atomic execution lease acquisition."""
        step_id_str = str(step.id)
        if self.is_dispatched(run_id, step_id_str):
            logger.warning(f"Prevented duplicate step dispatch for run [{run_id}], step [{step_id_str}]")
            return False

        idempotency_key = f"{run_id}:{step_id_str}"
        lease = await self.lease_manager.acquire_lease(
            step_run_id=step_id_str,
            run_id=run_id,
            worker_id=worker_id,
            ttl_seconds=ttl_seconds,
            idempotency_key=idempotency_key,
        )

        if not lease:
            logger.warning(f"Failed to acquire lease for run [{run_id}], step [{step_id_str}]. Dispatch blocked.")
            return False

        self._dispatched.add((run_id, step_id_str))
        logger.info(f"Dispatched step [{step.name}] with lease [{lease.lease_id}] to worker [{worker_id}]")
        return True

    def clear_run(self, run_id: str) -> None:
        self._dispatched = {k for k in self._dispatched if k[0] != run_id}
