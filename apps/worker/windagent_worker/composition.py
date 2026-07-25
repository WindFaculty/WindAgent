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
from windagent_memory.services import MemoryService
from windagent_workflows.registry import WorkflowRegistry
from windagent_verification.services import VerificationService
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_observability.events.dispatcher import EventDispatcher
from windagent_observability.events.publisher import OutboxEventPublisher
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
        
        # Durable queue and lease management (Worker-specific)
        self.lease_manager = DurableTaskLeaseManager(uow_factory=self.uow_factory)
        
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
        self.memory_service = MemoryService()
        self.verification_service = VerificationService()
        
        # Routing
        self.route_lock_service = RouteLockService()
        
        # Outbox: Worker OWNS the outbox publisher - publishes events to message bus
        self.outbox_publisher = OutboxEventPublisher(
            outbox_repo=SqlOutboxRepository(self.uow_factory),
            dispatcher=self.event_dispatcher.dispatch,
        )
        
        self.is_initialized = True
        logger.info("WorkerContainer successfully bootstrapped (PHASE 7 - Process-specific composition).")

    async def shutdown(self) -> None:
        """Gracefully shuts down all Worker services."""
        if not self.is_initialized:
            return

        logger.info("Shutting down WorkerContainer...")
        
        if self.outbox_publisher:
            await self.outbox_publisher.stop()
        
        if self.db:
            await self.db.close()
        
        # Clean up registries
        if self.tool_registry:
            await self.tool_registry.close()
        if self.provider_registry:
            await self.provider_registry.close()
        if self.intelligence_pipeline:
            await self.intelligence_pipeline.close()
        if self.context_service:
            await self.context_service.close()
        if self.memory_service:
            await self.memory_service.close()
        if self.verification_service:
            await self.verification_service.close()
        
        self.is_initialized = False
        logger.info("WorkerContainer shutdown complete.")

    def get_uow(self) -> SqlUnitOfWork:
        """Returns a new UnitOfWork transaction context."""
        if not self.uow_factory:
            raise RuntimeError("WorkerContainer is not initialized.")
        return SqlUnitOfWork(self.uow_factory)
