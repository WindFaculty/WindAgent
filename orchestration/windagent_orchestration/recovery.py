"""
Startup Recovery Manager for WindAgent Orchestration Engine.
Reconciles in-flight runs upon system startup/restart and protects against automatic re-execution of destructive tools.
"""

from __future__ import annotations
import logging
from typing import List, Tuple

from windagent_core.domain.types import SessionId, RunId
from windagent_core.domain.models import WorkflowRun, WorkflowStatus, StepStatus
from windagent_core.errors.exceptions import DomainError
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_orchestration.state_machine import TaskState, TaskStateMachine

logger = logging.getLogger("windagent.orchestration.recovery")

DESTRUCTIVE_TOOLS = {"write_file", "exec_shell", "git_commit", "git_push", "delete_file"}


class RecoveryManager:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def scan_and_reconcile_in_flight_runs(self, session_id: SessionId) -> List[Tuple[RunId, TaskState, str]]:
        """Scans in-flight workflow runs for a session and reconciles their state upon startup."""
        reconciled_results: List[Tuple[RunId, TaskState, str]] = []

        async with SqlUnitOfWork(self.session_factory) as uow:
            # Query stored events or session tasks
            events = await uow.events.get_events(session_id)
            if not events:
                return reconciled_results

            # Check if there are uncompleted destructive tools in progress
            interrupted_destructive = False
            for evt in events:
                if evt.event_type in ("step.started", "tool.started"):
                    tool_name = str(evt.payload.get("tool_name", ""))
                    if tool_name in DESTRUCTIVE_TOOLS:
                        interrupted_destructive = True

            if interrupted_destructive:
                logger.warning(f"In-flight recovery for session [{session_id}] detected interrupted destructive tool. Blocking auto-replay.")
                reconciled_results.append((
                    RunId.generate(),
                    TaskState.FAILED,
                    "Recovery blocked: Interrupted destructive tool cannot be automatically re-executed."
                ))
            else:
                logger.info(f"In-flight recovery for session [{session_id}] safe to reconcile.")
                reconciled_results.append((
                    RunId.generate(),
                    TaskState.READY,
                    "Recovery successful: Safe to resume."
                ))

        return reconciled_results
