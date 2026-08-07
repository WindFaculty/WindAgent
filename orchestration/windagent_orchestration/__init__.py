"""
WindAgent Orchestration Package (V2 Architecture).
Task state machine, task manager, workflow engine, scheduler, dispatcher, retry policy, recovery manager, and cancellation manager.
"""

from windagent_core.version import PRODUCT_VERSION

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
from windagent_orchestration.production import (
    ProductionRunState, ProductionStepState, ProductionRunStateMachine,
    ProductionApprovalGate, ApprovalLedger, ProductionApproval,
    ProductionCheckpoint, WorkerLease, PendingExternalOperation,
    OutboxEvent, OutboxJournal, new_event,
    ProductionStepNode, SchedulerFacts, ScheduleDecision, ProductionScheduler,
    ProductionRecovery, ProviderJobState, RecoveryAction, RecoveryDecision,
    ProductionCancellation, CancelAuditEntry, CancellationAuditLog,
    ProductionRun, ProductionRunStore, ProductionUnitOfWork,
    ProductionWorkflowEngine, StepExecutionResult, StepExecutorPort,
    # VP3D Stage A — engine-neutral consumer seam
    ProductionEngineExecutor, ProductionStepExecutor,
    # plan 05 Phase 19 — cost, credits and quota control
    COST_CATALOG_SCHEMA_VERSION, CostCatalog, CostCatalogEntry,
    ESTIMATE_SCHEMA_VERSION, ESTIMATE_STATUS_KNOWN, ESTIMATE_STATUS_UNKNOWN,
    CostEstimate, CreditEstimator, EstimateLine,
    QUOTA_LEDGER_SCHEMA_VERSION, QuotaEntryType, QuotaLedger, QuotaLedgerEntry,
    BUDGET_POLICY_SCHEMA_VERSION, BudgetApproval, DailyLimit,
    GenerationBudgetPolicy, MonthlyLimit, ProjectLimit, RetryBudget,
    SubmitDecision, SubmitVerdict,
    CIRCUIT_BREAKER_SCHEMA_VERSION, CircuitEvent, CircuitState,
    ProviderCircuitBreaker, TripReason,
)

__version__ = PRODUCT_VERSION
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
    "ProductionRunState", "ProductionStepState", "ProductionRunStateMachine",
    "ProductionApprovalGate", "ApprovalLedger", "ProductionApproval",
    "ProductionCheckpoint", "WorkerLease", "PendingExternalOperation",
    "OutboxEvent", "OutboxJournal", "new_event",
    "ProductionStepNode", "SchedulerFacts", "ScheduleDecision", "ProductionScheduler",
    "ProductionRecovery", "ProviderJobState", "RecoveryAction", "RecoveryDecision",
    "ProductionCancellation", "CancelAuditEntry", "CancellationAuditLog",
    "ProductionRun", "ProductionRunStore", "ProductionUnitOfWork",
    "ProductionWorkflowEngine", "StepExecutionResult", "StepExecutorPort",
    "ProductionEngineExecutor", "ProductionStepExecutor",
    # plan 05 Phase 19 — cost, credits and quota control
    "COST_CATALOG_SCHEMA_VERSION", "CostCatalog", "CostCatalogEntry",
    "ESTIMATE_SCHEMA_VERSION", "ESTIMATE_STATUS_KNOWN", "ESTIMATE_STATUS_UNKNOWN",
    "CostEstimate", "CreditEstimator", "EstimateLine",
    "QUOTA_LEDGER_SCHEMA_VERSION", "QuotaEntryType", "QuotaLedger", "QuotaLedgerEntry",
    "BUDGET_POLICY_SCHEMA_VERSION", "BudgetApproval", "DailyLimit",
    "GenerationBudgetPolicy", "MonthlyLimit", "ProjectLimit", "RetryBudget",
    "SubmitDecision", "SubmitVerdict",
    "CIRCUIT_BREAKER_SCHEMA_VERSION", "CircuitEvent", "CircuitState",
    "ProviderCircuitBreaker", "TripReason",
]
