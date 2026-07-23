"""
Startup Recovery Manager for WindAgent Orchestration Engine V2.
Reconciles in-flight runs upon system startup/restart and protects against automatic re-execution of destructive tools.
"""

from __future__ import annotations

import logging
from typing import List, Tuple, Optional, Any

from windagent_orchestration.state_machine import TaskState
from windagent_orchestration.recovery.destructive_guard import DESTRUCTIVE_TOOLS, DestructiveReplayGuard
from windagent_orchestration.recovery.reconciler import InFlightReconciler

logger = logging.getLogger("windagent.orchestration.recovery")


class RecoveryManager:
    def __init__(self, session_factory: Optional[Any] = None):
        self.session_factory = session_factory
        self.reconciler = InFlightReconciler(uow_factory=session_factory)

    async def scan_and_reconcile_in_flight_runs(self, session_id: str) -> List[Tuple[str, TaskState, str]]:
        """Scans in-flight workflow runs for a session and reconciles their state upon startup."""
        return await self.reconciler.reconcile_session_runs(str(session_id))
