"""
High-Level Task Manager & Coordinator for WindAgent Architecture V2.
Links TaskStateMachine, TaskScheduler, StepDispatcher, RetryPolicy, and CancellationManager.
Manages durable execution facts and computes derived UI status.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_core.domain.types import TaskId, SessionId, RunId
from windagent_core.domain.models import Task, SessionStatus
from windagent_orchestration.state_machine import TaskState, TaskStateMachine
from windagent_orchestration.scheduler import TaskScheduler, TaskPriority
from windagent_orchestration.dispatcher import StepDispatcher
from windagent_orchestration.retry_policy import RetryPolicy
from windagent_orchestration.cancellation import CancellationManager

logger = logging.getLogger("windagent.orchestration.task_manager")


@dataclass
class DurableExecutionFacts:
    task_id: TaskId
    session_id: SessionId
    current_state: TaskState = TaskState.RECEIVED
    current_step: int = 0
    total_steps: int = 0
    last_sequence: int = 0
    pending_permission: bool = False
    retry_count: int = 0
    last_error: Optional[str] = None
    verification_state: str = "none"
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def derive_ui_status(self) -> str:
        """Derives UI display status deterministically from durable execution facts."""
        if self.current_state == TaskState.WAITING_PERMISSION or self.pending_permission:
            return "waiting_permission"
        if self.current_state == TaskState.PAUSED:
            return "paused"
        if self.current_state == TaskState.RETRY_WAIT:
            return f"retrying (attempt {self.retry_count})"
        if self.current_state == TaskState.VERIFYING:
            return "verifying"
        if self.current_state == TaskState.COMPLETED:
            return "completed"
        if self.current_state in (TaskState.FAILED, TaskState.CANCELLED):
            return self.current_state.value
        return "running"


class TaskManager:
    def __init__(
        self,
        scheduler: Optional[TaskScheduler] = None,
        dispatcher: Optional[StepDispatcher] = None,
        retry_policy: Optional[RetryPolicy] = None,
        cancellation_manager: Optional[CancellationManager] = None,
    ):
        self.scheduler = scheduler or TaskScheduler()
        self.dispatcher = dispatcher or StepDispatcher()
        self.retry_policy = retry_policy or RetryPolicy()
        self.cancellation_manager = cancellation_manager or CancellationManager()
        self.state_machine = TaskStateMachine()
        self._facts: Dict[str, DurableExecutionFacts] = {}

    def get_or_create_facts(self, task_id: TaskId, session_id: SessionId) -> DurableExecutionFacts:
        tid_str = str(task_id)
        if tid_str not in self._facts:
            self._facts[tid_str] = DurableExecutionFacts(task_id=task_id, session_id=session_id)
        return self._facts[tid_str]

    def transition_task(self, task_id: TaskId, session_id: SessionId, target_state: TaskState) -> DurableExecutionFacts:
        facts = self.get_or_create_facts(task_id, session_id)
        new_state = self.state_machine.transition(facts.current_state, target_state)
        facts.current_state = new_state
        facts.updated_at = datetime.now(timezone.utc)
        return facts
