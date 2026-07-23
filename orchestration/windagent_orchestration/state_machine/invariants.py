"""
Invariant Checks for Task and Workflow State Machines.
Ensures terminal states cannot be mutated and invalid states raise DomainErrors.
"""

from __future__ import annotations

from windagent_core.errors.exceptions import DomainError
from windagent_orchestration.state_machine.task import TaskState


def assert_non_terminal(state: TaskState, action: str) -> None:
    if state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
        raise DomainError(
            message=f"Cannot execute [{action}] on task in terminal state [{state.value}].",
            code="WINDAGENT_ERR_TERMINAL_STATE_MUTATION",
            details={"state": state.value, "action": action},
        )
