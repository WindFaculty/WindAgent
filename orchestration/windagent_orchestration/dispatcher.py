"""
Step Dispatcher for WindAgent Orchestration Engine.
Dispatches workflow steps to workers while preventing duplicate execution.
"""

from __future__ import annotations
import logging
from typing import Set, Tuple

from windagent_core.domain.models import WorkflowStep

logger = logging.getLogger("windagent.orchestration.dispatcher")


class StepDispatcher:
    def __init__(self):
        self._dispatched: Set[Tuple[str, str]] = set()

    def is_dispatched(self, run_id: str, step_id: str) -> bool:
        return (run_id, step_id) in self._dispatched

    def dispatch_step(self, run_id: str, step: WorkflowStep) -> bool:
        """Dispatches a workflow step if it has not already been dispatched."""
        key = (run_id, str(step.id))
        if key in self._dispatched:
            logger.warning(f"Prevented duplicate step dispatch for run [{run_id}], step [{step.id}]")
            return False

        self._dispatched.add(key)
        logger.info(f"Dispatched step [{step.name}] (tool: {step.tool_name}) for run [{run_id}]")
        return True

    def clear_run(self, run_id: str) -> None:
        self._dispatched = {k for k in self._dispatched if k[0] != run_id}
