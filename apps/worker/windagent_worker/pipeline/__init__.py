"""Production Worker execution pipeline (Architecture V3 Phase 9).

Decomposes the monolithic ``poll_and_execute_tick`` into independently
testable stages:

    claim -> lease_guard -> executor -> result_validator -> finalizer
          -> reconciler -> release

``TaskExecutionPipeline`` is the explicit orchestrator; the runner only
enforces readiness and delegates.
"""

from windagent_worker.pipeline.claim import ClaimStage
from windagent_worker.pipeline.context import TaskExecutionContext
from windagent_worker.pipeline.executor import ExecutorStage
from windagent_worker.pipeline.finalizer import FinalizeOutcome, FinalizerStage
from windagent_worker.pipeline.lease_guard import LeaseGuardStage
from windagent_worker.pipeline.pipeline import TaskExecutionPipeline
from windagent_worker.pipeline.reconciler import ReconcilerStage
from windagent_worker.pipeline.result_validator import ProposedOutcome, ResultValidatorStage

__all__ = [
    "ClaimStage",
    "TaskExecutionContext",
    "ExecutorStage",
    "FinalizeOutcome",
    "FinalizerStage",
    "LeaseGuardStage",
    "TaskExecutionPipeline",
    "ReconcilerStage",
    "ProposedOutcome",
    "ResultValidatorStage",
]