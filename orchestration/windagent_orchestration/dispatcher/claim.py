"""
Atomic Step Lease Claim Service for WindAgent Orchestration V2 Dispatcher.
"""

from __future__ import annotations

import logging
from typing import Optional

from windagent_orchestration.dispatcher.leases import LeaseManager, ExecutionLease

logger = logging.getLogger("windagent.orchestration.dispatcher.claim")


class StepClaimService:
    def __init__(self, lease_manager: Optional[LeaseManager] = None):
        self.lease_manager = lease_manager or LeaseManager()

    async def claim_step(
        self,
        step_run_id: str,
        run_id: str,
        worker_id: str = "default_worker",
        ttl_seconds: float = 30.0,
        idempotency_key: Optional[str] = None,
    ) -> Optional[ExecutionLease]:
        """Atomically claim step execution lease, acquiring fencing token and generation."""
        key = idempotency_key or f"{run_id}:{step_run_id}"
        lease = await self.lease_manager.acquire_lease(
            step_run_id=step_run_id,
            run_id=run_id,
            worker_id=worker_id,
            ttl_seconds=ttl_seconds,
            idempotency_key=key,
        )

        if not lease:
            logger.warning(f"Failed to acquire atomic lease for run [{run_id}], step [{step_run_id}]")
            return None

        logger.info(f"Step [{step_run_id}] atomically claimed by worker [{worker_id}] with fencing token [{lease.fencing_token}]")
        return lease
