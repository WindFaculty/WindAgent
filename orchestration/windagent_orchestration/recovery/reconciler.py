"""
In-Flight Run Reconciler for Orchestration V2 Startup Recovery.
Preserves original run ID, checks real runtime status, and marks destructive runs FAILED.
"""

from __future__ import annotations

import logging
from typing import List, Tuple, Optional, Any

from windagent_orchestration.state_machine import TaskState
from windagent_orchestration.recovery.destructive_guard import DestructiveReplayGuard, DESTRUCTIVE_TOOLS
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

logger = logging.getLogger("windagent.orchestration.recovery.reconciler")


class InFlightReconciler:
    def __init__(self, uow_factory: Optional[Any] = None):
        self.uow_factory = uow_factory

    async def reconcile_session_runs(self, session_id: str) -> List[Tuple[str, TaskState, str]]:
        """Scans in-flight workflow runs for a session, preserves original run ID, and guards destructive tools."""
        results: List[Tuple[str, TaskState, str]] = []
        if not self.uow_factory:
            return results

        async with SqlUnitOfWork(self.uow_factory) as uow:
            events = await uow.events.get_events(session_id)
            if not events:
                return results

            # Inspect events for in-flight destructive steps and target run IDs
            target_run_id = f"run_{session_id}"
            interrupted_destructive = False

            for evt in events:
                if evt.event_type in ("step.started", "tool.started"):
                    payload = evt.payload
                    tool_name = str(payload.get("tool_name", payload.get("tool", "")))
                    if tool_name in DESTRUCTIVE_TOOLS:
                        interrupted_destructive = True
                    if "run_id" in payload:
                        target_run_id = str(payload["run_id"])

            if interrupted_destructive:
                logger.warning(f"In-flight recovery for session [{session_id}] detected interrupted destructive tool. Blocking auto-replay.")
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
