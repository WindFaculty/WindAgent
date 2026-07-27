"""
Composition Root for Orchestration V2 Subsystem.
Wires TaskManager, WorkflowEngine, TaskScheduler, StepDispatcher, RetryPolicy, RecoveryManager, and CancellationManager.
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from windagent_orchestration.task_manager import TaskManager
from windagent_orchestration.workflow_engine import WorkflowEngine, CheckpointManager
from windagent_orchestration.scheduler import TaskScheduler
from windagent_orchestration.dispatcher import StepDispatcher, LeaseManager, WorkerRegistry
from windagent_orchestration.retry import RetryPolicy
from windagent_orchestration.recovery import RecoveryManager
from windagent_orchestration.cancellation import CancellationManager

logger = logging.getLogger("windagent.orchestration.composition")


class OrchestrationV2Container:
    def __init__(self, uow_factory: Optional[Any] = None, max_concurrency: int = 5, runtime_port: Optional[Any] = None):
        self.uow_factory = uow_factory
        
        self.cancellation_manager = CancellationManager(uow_factory=uow_factory)
        self.retry_policy = RetryPolicy()
        self.scheduler = TaskScheduler(max_concurrency=max_concurrency)
        self.worker_registry = WorkerRegistry()
        self.lease_manager = LeaseManager(uow_factory=uow_factory)
        self.dispatcher = StepDispatcher(
            lease_manager=self.lease_manager,
            worker_registry=self.worker_registry,
            runtime_port=runtime_port,
        )
        self.checkpoint_manager = CheckpointManager(uow_factory=uow_factory)
        self.workflow_engine = WorkflowEngine(checkpoint_manager=self.checkpoint_manager)
        self.task_manager = TaskManager(
            uow_factory=uow_factory,
            scheduler=self.scheduler,
            dispatcher=self.dispatcher,
            retry_policy=self.retry_policy,
            cancellation_manager=self.cancellation_manager,
        )
        self.recovery_manager = RecoveryManager(session_factory=uow_factory)
        
        logger.info("Initialized OrchestrationV2Container successfully.")
