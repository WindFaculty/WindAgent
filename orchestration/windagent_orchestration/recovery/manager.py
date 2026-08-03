"""
Startup Recovery Manager for WindAgent Orchestration Engine V2.
Reconciles in-flight runs upon system startup/restart with singleton leader lease, paginated scanning, and UNKNOWN vs MISSING runtime handling.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, List, Tuple, Optional, Any, Dict

from windagent_orchestration.state_machine import TaskState
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


@dataclass
class ProductionRecoveryReport(RecoveryReport):
    """Ordered recovery outcome used by API/worker startup paths."""

    reattached_agent_run_ids: tuple[str, ...] = ()
    orphaned_agent_run_ids: tuple[str, ...] = ()
    unavailable_agent_run_ids: tuple[str, ...] = ()
    route_lock_ids: tuple[str, ...] = ()
    reconciled_worktree_ids: tuple[str, ...] = ()
    published_approval_count: int = 0


class RecoveryManager:
    def __init__(
        self,
        session_factory: Optional[Any] = None,
        instance_id: Optional[str] = None,
        release_telemetry: Any | None = None,
    ):
        self.session_factory = session_factory
        self.instance_id = instance_id or f"node_{uuid.uuid4().hex[:6]}"
        self.reconciler = InFlightReconciler(uow_factory=session_factory)
        self._release_telemetry = release_telemetry

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

    async def recover_production(
        self,
        orchestrator: Any,
        *,
        publish_pending_approvals: Callable[[], Awaitable[int] | int] | None = None,
    ) -> ProductionRecoveryReport:
        """Recover the production control plane in the required durable order.

        The leader lease is acquired before any side effect.  Worktree cleanup
        deliberately happens after route-lock rehydration, avoiding a second
        scheduler authority or an in-memory reconstruction of a plan.
        """
        started = time.perf_counter()
        report = ProductionRecoveryReport()
        if not self.session_factory:
            self._record_recovery_duration(started)
            return report

        async with SqlUnitOfWork(self.session_factory) as uow:
            is_leader = await uow.recovery_leader_leases.acquire_leader_lease(
                self.instance_id, ttl_seconds=30.0
            )
            await uow.commit()
            if not is_leader:
                report.leader_acquired = False
                report.details.append({"phase": "leader_lease", "action": "not_acquired"})
                self._record_recovery_duration(started)
                return report
            report.details.append({"phase": "leader_lease", "action": "acquired"})

            expired = await uow.leases.reclaim_expired_leases()
            report.leases_reclaimed_count = len(expired)
            await uow.commit()
            report.details.append({"phase": "leases", "reclaimed": len(expired)})

        reattach = await orchestrator.reattach_live_runs(
            reconcile_worktrees=False,
            resume_scheduler=False,
        )
        report.reattached_agent_run_ids = reattach.reattached_agent_run_ids
        report.orphaned_agent_run_ids = reattach.orphaned_agent_run_ids
        report.unavailable_agent_run_ids = tuple(
            getattr(reattach, "unavailable_agent_run_ids", ())
        )
        report.reattached_count = len(reattach.reattached_agent_run_ids)
        report.details.append(
            {
                "phase": "runtime",
                "reattached": len(reattach.reattached_agent_run_ids),
                "orphaned_stopped": len(reattach.orphaned_agent_run_ids),
                "unavailable": len(report.unavailable_agent_run_ids),
            }
        )

        completed = await orchestrator.reconcile_runtime_completions()
        scheduled = await orchestrator.schedule_due_nodes()
        report.completed_ingested_count = len(completed)
        report.details.append(
            {"phase": "dag", "completed": len(completed), "scheduled": len(scheduled)}
        )

        report.route_lock_ids = await orchestrator.reconcile_route_locks()
        report.details.append({"phase": "route_locks", "reconciled": len(report.route_lock_ids)})

        worktrees = await orchestrator.reconcile_worktrees()
        report.reconciled_worktree_ids = (
            worktrees.reattached_worktree_ids + worktrees.cleaned_worktree_ids
        )
        report.details.append(
            {
                "phase": "worktrees",
                "reattached": len(worktrees.reattached_worktree_ids),
                "cleaned": len(worktrees.cleaned_worktree_ids),
            }
        )

        if publish_pending_approvals is not None:
            published = publish_pending_approvals()
            if hasattr(published, "__await__"):
                published = await published
            report.published_approval_count = int(published)
        report.details.append(
            {"phase": "pending_approvals", "published": report.published_approval_count}
        )
        self._record_recovery_duration(started)
        return report

    def _record_recovery_duration(self, started: float) -> None:
        if self._release_telemetry is not None:
            self._release_telemetry.record_recovery_duration(time.perf_counter() - started)

    async def scan_and_reconcile_in_flight_runs(self, session_id: str) -> List[Tuple[str, TaskState, str]]:
        """Adapter method for session-specific event stream recovery compatibility."""
        return await self.reconciler.reconcile_session_runs(str(session_id))
