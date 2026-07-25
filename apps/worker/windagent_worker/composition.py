"""
Canonical Worker Composition Root for WindAgent V2 (PHASE 7).
Provides process-specific composition for Worker process with all required services
for task execution, leasing, and event publishing.

Worker Composition Root (PHASE 7):
- Database
- Durable queue
- Lease manager
- Orchestration engine
- Execution runtime
- Tools
- Providers
- Intelligence pipeline
- Context
- Memory
- Workflows
- Verification
- Outbox publisher
- Observability

NOTE: Worker runs as a SEPARATE process from API and Desktop.
Worker does NOT compose:
- API HTTP endpoints
- Web UI services
- Desktop supervisor
"""

from __future__ import annotations
import logging
from typing import Optional, Any

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.v2_orchestration_models
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_orchestration import OrchestrationV2Container
from windagent_orchestration.task_manager.service import TaskManager
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_tools.registry import ToolRegistry
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_intelligence.pipeline import IntelligencePipeline
from windagent_context.services import ContextService
from windagent_memory.query import MemoryQueryService
from windagent_workflows.registry import WorkflowRegistry
from windagent_verification.query import VerificationQueryService
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_observability.events.dispatcher import EventDispatcher
from windagent_observability.events.publisher import OutboxEventPublisher
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue
from windagent_storage.repositories.worker_status import SqlWorkerHeartbeatRepository
from windagent_worker.lease import DurableTaskLeaseManager

logger = logging.getLogger("windagent.worker.composition")


class WorkerContainer:
    """Process-specific composition root for Worker.
    
    Composes ALL services required for Worker process:
    - Database & Unit of Work for persistence
    - Durable queue for task leasing
    - Lease manager for task claim/renewal
    - Orchestration engine for workflow execution
    - Execution runtime for tool execution
    - Registries (providers, tools, workflows)
    - Intelligence pipeline for model selection
    - Context, Memory, Verification services
    - Outbox publisher for event publishing
    - Observability for monitoring
    
    Note: Worker does NOT compose API, Web, or Desktop components.
    """

    def __init__(self, db_url: str = "sqlite+aiosqlite:///windagent.db"):
        self.db_url = db_url
        self.db: Optional[DatabaseManager] = None
        self.uow_factory: Optional[Any] = None
        self.event_dispatcher: Optional[EventDispatcher] = None
        self.lease_manager: Optional[DurableTaskLeaseManager] = None
        self.orchestration_container: Optional[OrchestrationV2Container] = None
        self.task_manager: Optional[TaskManager] = None
        self.execution_registry: Optional[ExecutionRuntimeRegistry] = None
        self.provider_registry: Optional[CanonicalModelRegistryService] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.workflow_registry: Optional[WorkflowRegistry] = None
        self.intelligence_pipeline: Optional[IntelligencePipeline] = None
        self.context_service: Optional[ContextService] = None
        self.memory_service: Optional[MemoryService] = None
        self.verification_service: Optional[VerificationService] = None
        self.outbox_publisher: Optional[OutboxEventPublisher] = None
        self.route_lock_service: Optional[RouteLockService] = None
        self.is_initialized: bool = False

    async def bootstrap(self) -> None:
        """Bootstraps all Worker process services.
        
        PHASE 7: Worker composes ALL its required services for independent operation.
        """
        if self.is_initialized:
            return

        logger.info(f"Initializing WorkerContainer with database: {self.db_url}")
        
        # Database layer
        self.db = DatabaseManager(self.db_url)
        try:
            await self.db.create_tables(BaseORM.metadata)
        except Exception as ex:
            logger.warning(f"Database table creation warning: {ex}")
        
        self.uow_factory = self.db.session_factory
        
        # Event dispatcher
        self.event_dispatcher = EventDispatcher()
        
        # Durable queue, lease management, and heartbeat repository (Worker-specific)
        self.task_queue = SqlDurableTaskQueue(self.db.session_factory) if self.db else None
        self.lease_manager = DurableTaskLeaseManager(session_factory=self.db.session_factory if self.db else None)
        self.heartbeat_repo = SqlWorkerHeartbeatRepository(self.db.session_factory) if self.db else None
        
        # Orchestration engine (Worker needs full orchestration for execution)
        self.orchestration_container = OrchestrationV2Container(uow_factory=self.uow_factory)
        self.task_manager = self.orchestration_container.task_manager
        
        # Execution runtime (Worker executes tools directly)
        self.execution_registry = ExecutionRuntimeRegistry()
        
        # Registries
        self.provider_registry = CanonicalModelRegistryService()
        self.tool_registry = ToolRegistry()
        self.workflow_registry = WorkflowRegistry()
        
        # Intelligence pipeline (Worker needs for model selection)
        self.intelligence_pipeline = IntelligencePipeline(
            provider_registry=self.provider_registry,
            tool_registry=self.tool_registry
        )
        
        # Context, Memory, Verification services
        self.context_service = ContextService()
        self.memory_service = MemoryQueryService()
        self.verification_service = VerificationQueryService()
        
        # Routing
        self.route_lock_service = RouteLockService()
        
        # Outbox: Worker OWNS the outbox publisher - publishes events to message bus
        self.outbox_publisher = OutboxEventPublisher(
            outbox_repo=SqlOutboxRepository(self.uow_factory),
            dispatcher=self.event_dispatcher.dispatch,
        )
        await self.outbox_publisher.start()
        
        self.is_initialized = True
        logger.info("WorkerContainer successfully bootstrapped (PHASE 7 - Process-specific composition).")

    async def shutdown(self) -> None:
        """Gracefully shuts down all Worker services."""
        if not self.is_initialized:
            return

        logger.info("Shutting down WorkerContainer...")
        
        # 1. Stop outbox publisher (drain pending claimed batch)
        if self.outbox_publisher and hasattr(self.outbox_publisher, "stop"):
            try:
                await self.outbox_publisher.stop(drain=True)
            except Exception as ex:
                logger.warning(f"Error stopping worker outbox publisher: {ex}")
        
        # 2. Clean up registries and services
        for name, service in [
            ("tool_registry", self.tool_registry),
            ("provider_registry", self.provider_registry),
            ("workflow_registry", self.workflow_registry),
            ("intelligence_pipeline", self.intelligence_pipeline),
            ("context_service", self.context_service),
            ("memory_service", self.memory_service),
            ("verification_service", self.verification_service),
        ]:
            if service is not None and hasattr(service, "close"):
                try:
                    res = service.close()
                    if hasattr(res, "__await__"):
                        await res
                except Exception as ex:
                    logger.warning(f"Error closing worker service {name}: {ex}")
        
        # 3. Close database connection last
        if self.db and hasattr(self.db, "close"):
            try:
                await self.db.close()
            except Exception as ex:
                logger.warning(f"Error closing worker db: {ex}")
        
        self.is_initialized = False
        logger.info("WorkerContainer shutdown complete.")

    def get_uow(self) -> SqlUnitOfWork:
        """Returns a new UnitOfWork transaction context."""
        if not self.uow_factory:
            raise RuntimeError("WorkerContainer is not initialized.")
        return SqlUnitOfWork(self.uow_factory)
