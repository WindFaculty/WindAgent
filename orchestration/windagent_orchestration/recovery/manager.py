"""
Startup Recovery Manager for WindAgent Orchestration Engine V2.
Reconciles in-flight runs upon system startup/restart with singleton leader lease, paginated scanning, and UNKNOWN vs MISSING runtime handling.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any, Dict

from windagent_orchestration.state_machine import TaskState, WorkflowState, StepState
from windagent_orchestration.recovery.destructive_guard import DESTRUCTIVE_TOOLS, DestructiveReplayGuard
from windagent_orchestration.recovery.reconciler import InFlightReconciler
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

logger = logging.getLogger("windagent.orchestration.recovery")


@dataclass
class RecoveryReport:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    leader_acquired: bool = True
    tasks_scanned: int = 0
    runs_reconciled: int = 0
    reattached_count: int = 0
    completed_ingested_count: int = 0
    leases_reclaimed_count: int = 0
    destructive_blocked_count: int = 0
    duplicate_executions_count: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)


class RecoveryManager:
    def __init__(self, session_factory: Optional[Any] = None, instance_id: Optional[str] = None):
        self.session_factory = session_factory
        self.instance_id = instance_id or f"node_{uuid.uuid4().hex[:6]}"
        self.reconciler = InFlightReconciler(uow_factory=session_factory)

    async def recover_all_in_flight(self, batch_size: int = 500) -> RecoveryReport:
        """Paginated, leader-leased startup recovery scanning all persisted in-flight records."""
        report = RecoveryReport()
        if not self.session_factory:
            return report

        async with SqlUnitOfWork(self.session_factory) as uow:
            # 1. Acquire singleton leader lease
            is_leader = await uow.recovery_leader_leases.acquire_leader_lease(self.instance_id, ttl_seconds=30.0)
            await uow.commit()

            if not is_leader:
                logger.info(f"Instance [{self.instance_id}] did not acquire recovery leader lease. Skipping recovery.")
                report.leader_acquired = False
                return report

        logger.info(f"Instance [{self.instance_id}] acquired leader lease. Executing in-flight recovery...")
        return await self.reconciler.reconcile_all_in_flight(batch_size=batch_size)
