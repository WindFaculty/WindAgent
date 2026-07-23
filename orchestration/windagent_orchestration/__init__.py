"""
WindAgent Orchestration Package (V2 Architecture).
Task state machine, task manager, scheduler, dispatcher, retry policy, recovery manager, and cancellation manager.
"""

from windagent_orchestration.state_machine import (
    TaskState, TaskStateMachine, ALLOWED_TRANSITIONS
)
from windagent_orchestration.retry_policy import RetryPolicy
from windagent_orchestration.scheduler import TaskScheduler, TaskPriority, ScheduledTaskItem
from windagent_orchestration.cancellation import CancellationManager
from windagent_orchestration.dispatcher import StepDispatcher
from windagent_orchestration.recovery import RecoveryManager, DESTRUCTIVE_TOOLS
from windagent_orchestration.task_manager import (
    TaskManager, DurableExecutionFacts
)

__version__ = "0.3.0"

__all__ = [
    "TaskState", "TaskStateMachine", "ALLOWED_TRANSITIONS",
    "RetryPolicy",
    "TaskScheduler", "TaskPriority", "ScheduledTaskItem",
    "CancellationManager",
    "StepDispatcher",
    "RecoveryManager", "DESTRUCTIVE_TOOLS",
    "TaskManager", "DurableExecutionFacts",
]
