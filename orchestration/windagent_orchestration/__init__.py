"""
WindAgent Orchestration Package (V2 Architecture).
Task state machine, task manager, workflow engine, scheduler, dispatcher, retry policy, recovery manager, and cancellation manager.
"""

from windagent_orchestration.state_machine import (
    TaskState, TaskStateMachine, ALLOWED_TRANSITIONS
)
from windagent_orchestration.retry import RetryPolicy, ErrorClassifier, ExponentialBackoff, TimeoutEvaluator
from windagent_orchestration.scheduler import TaskScheduler, TaskPriority, ScheduledTaskItem, ProjectLockManager, EventDrivenWakeup
from windagent_orchestration.cancellation import CancellationManager
from windagent_orchestration.dispatcher import StepDispatcher, LeaseManager, WorkerRegistry, ExecutionLease, WorkerRegistration
from windagent_orchestration.recovery import RecoveryManager, DESTRUCTIVE_TOOLS, DestructiveReplayGuard, InFlightReconciler
from windagent_orchestration.task_manager import TaskManager, DurableExecutionFacts
from windagent_orchestration.workflow_engine import WorkflowEngine, WorkflowDefinition, WorkflowNode, WorkflowEdge, WorkflowValidator, CheckpointManager
from windagent_orchestration.composition import OrchestrationV2Container

__version__ = "0.3.0"

__all__ = [
    "TaskState", "TaskStateMachine", "ALLOWED_TRANSITIONS",
    "RetryPolicy", "ErrorClassifier", "ExponentialBackoff", "TimeoutEvaluator",
    "TaskScheduler", "TaskPriority", "ScheduledTaskItem", "ProjectLockManager", "EventDrivenWakeup",
    "CancellationManager",
    "StepDispatcher", "LeaseManager", "WorkerRegistry", "ExecutionLease", "WorkerRegistration",
    "RecoveryManager", "DESTRUCTIVE_TOOLS", "DestructiveReplayGuard", "InFlightReconciler",
    "TaskManager", "DurableExecutionFacts",
    "WorkflowEngine", "WorkflowDefinition", "WorkflowNode", "WorkflowEdge", "WorkflowValidator", "CheckpointManager",
    "OrchestrationV2Container",
]
