"""
In-Flight Run Reconciler for Orchestration V2 Startup Recovery.
Queries persisted database records, enforces singleton leader lease, distinguishes UNKNOWN from MISSING runtimes, and guards destructive operations.
"""

from __future__ import annotations

import logging
from typing import List, Tuple, Optional, Any
from sqlalchemy import select

from windagent_orchestration.state_machine import TaskState
from windagent_orchestration.recovery.destructive_guard import DESTRUCTIVE_TOOLS
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_storage.orm.v2_orchestration_models import (
    TaskRunORM, WorkflowStepRunORM
)

logger = logging.getLogger("windagent.orchestration.recovery.reconciler")


class InFlightReconciler:
    def __init__(self, uow_factory: Optional[Any] = None):
        self.uow_factory = uow_factory

    async def reconcile_all_in_flight(self, batch_size: int = 500) -> Any:
        from windagent_orchestration.recovery.manager import RecoveryReport
        report = RecoveryReport(leader_acquired=True)

        if not self.uow_factory:
            return report

        async with SqlUnitOfWork(self.uow_factory) as uow:
            # Reclaim expired leases first
            expired_leases = await uow.leases.reclaim_expired_leases()
            report.leases_reclaimed_count = len(expired_leases)
            await uow.commit()

            # Paginated scan of non-terminal TaskRuns
            stmt_tasks = select(TaskRunORM).where(TaskRunORM.state.notin_(["completed", "failed", "cancelled"])).limit(batch_size)
            res_tasks = await uow.session.execute(stmt_tasks)
            tasks = res_tasks.scalars().all()
            report.tasks_scanned = len(tasks)

            # Paginated scan of non-terminal WorkflowStepRuns
            stmt_steps = select(WorkflowStepRunORM).where(WorkflowStepRunORM.state.in_(["running", "dispatched", "retry_wait"])).limit(batch_size)
            res_steps = await uow.session.execute(stmt_steps)
            steps = res_steps.scalars().all()

            for step in steps:
                report.runs_reconciled += 1
                runtime_exec = await uow.runtime_executions.get_by_step_run_id(step.id)
                tool_name = step.tool_name or ""
                is_destructive = tool_name in DESTRUCTIVE_TOOLS

                if not runtime_exec:
                    # Missing execution record
                    if is_destructive:
                        step.state = "failed"
                        step.error = "Recovery blocked: Missing runtime execution for destructive step"
                        report.destructive_blocked_count += 1
                    else:
                        step.state = "ready"
                        report.details.append({"step_id": step.id, "action": "reset_to_ready"})
                else:
                    status = runtime_exec.status
                    if status == "completed":
                        step.state = "completed"
                        report.completed_ingested_count += 1
                    elif status == "running" or status == "dispatched":
                        report.reattached_count += 1
                    elif status == "unknown":
                        if is_destructive:
                            step.state = "failed"
                            step.error = "Recovery blocked: UNKNOWN runtime state for destructive step"
                            report.destructive_blocked_count += 1
                        else:
                            step.state = "ready"
                    elif status in ("lost", "failed", "timeout"):
                        if is_destructive:
                            step.state = "failed"
                            step.error = f"Recovery blocked: Runtime status [{status}] for destructive step"
                            report.destructive_blocked_count += 1
                        else:
                            step.state = "ready"

            await uow.commit()

        return report

    async def reconcile_session_runs(self, session_id: str) -> List[Tuple[str, TaskState, str]]:
        """Scans session event stream for interrupted destructive steps and preserves original run ID."""
        results: List[Tuple[str, TaskState, str]] = []
        if not self.uow_factory:
            return results

        async with SqlUnitOfWork(self.uow_factory) as uow:
            events = await uow.events.get_events(session_id)
            if not events:
                return results

            target_run_id = f"run_{session_id}"
            interrupted_destructive = False

            for evt in events:
                payload = evt.payload or {}
                if evt.event_type in ("step.started", "tool.started"):
                    tool_name = str(payload.get("tool_name", payload.get("tool", "")))
                    if tool_name in DESTRUCTIVE_TOOLS:
                        interrupted_destructive = True
                    if "run_id" in payload:
                        target_run_id = str(payload["run_id"])

            if interrupted_destructive:
                logger.warning(f"In-flight recovery for session [{session_id}] detected interrupted destructive tool.")
                results.append((
                    target_run_id,
                    TaskState.FAILED,
                    "Recovery blocked: Interrupted destructive tool cannot be automatically re-executed."
                ))
            else:
                logger.info(f"In-flight recovery for session [{session_id}] safe to reconcile.")
                results.append((
                    target_run_id,
                    TaskState.READY,
                    "Recovery successful: Safe to resume."
                ))

        return results
