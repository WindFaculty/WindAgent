"""
Canonical Application Composition Root for WindAgent V2 (Phase 7).
Provides a strongly-typed ApplicationContainer managing domain services, storage,
orchestration, providers, tools, and event buses without loose state objects.

API Composition Root (PHASE 7):
- Database
- Unit of Work
- Query services
- Command services
- Provider registry
- Tool registry
- Plugin registry
- Skill registry
- Workflow registry
- Context services
- Memory query services
- Verification query services
- Observability
- Outbox submission
- Worker status query

NOT composed (separate process):
- Production Worker
- Worker event loop
- Tool subprocess runtime directly
- Desktop supervisor
"""

from __future__ import annotations
import logging
from typing import Optional, Any, Dict

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.v2_orchestration_models
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_orchestration.task_manager.service import TaskManager
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_tools.registry import ToolRegistry
from windagent_plugins.registry import PluginRegistry
from windagent_skills.registry import SkillRegistry
from windagent_workflows.registry import WorkflowRegistry
from windagent_context.services import ContextService
from windagent_memory.query import MemoryQueryService
from windagent_verification.query import VerificationQueryService
from windagent_core.contracts.workers import WorkerStatusQueryPort
from windagent_storage.repositories.worker_status import (
    SqlWorkerHeartbeatRepository,
    SqlWorkerStatusQuery,
)
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_observability.events.dispatcher import EventDispatcher
from windagent_observability.events.publisher import OutboxEventPublisher

logger = logging.getLogger("windagent.api.composition")


class ApplicationContainer:
    """Strongly-typed composition root for WindAgent V2 applications (PHASE 7).
    
    Composes ONLY services that API needs:
    - Database & Unit of Work for persistence
    - TaskManager for orchestration (query/command)
    - Registries for discovery (providers, tools, plugins, skills, workflows)
    - Context, Memory, Verification for query services
    - Observability for monitoring
    - Outbox for event submission
    - Worker status query for health checks
    
    Does NOT compose:
    - Production Worker (separate process)
    - Worker event loop (separate process)
    - Tool subprocess runtime directly (executed via registry)
    - Desktop supervisor (separate process)
    """

    def __init__(self, db_url: str = "sqlite+aiosqlite:///windagent.db"):
        self.db_url = db_url
        self.db: Optional[DatabaseManager] = None
        self.task_manager: Optional[TaskManager] = None
        self.event_dispatcher: Optional[EventDispatcher] = None
        self.outbox_publisher: Optional[OutboxEventPublisher] = None
        self.provider_registry: Optional[CanonicalModelRegistryService] = None
        self.route_lock_service: Optional[RouteLockService] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.plugin_registry: Optional[PluginRegistry] = None
        self.skill_registry: Optional[SkillRegistry] = None
        self.workflow_registry: Optional[WorkflowRegistry] = None
        self.context_service: Optional[ContextService] = None
        self.memory_query_service: Optional[MemoryQueryService] = None
        self.verification_query_service: Optional[VerificationQueryService] = None
        self.worker_status_query: Optional[WorkerStatusQueryPort] = None
        self.is_initialized: bool = False

    async def bootstrap(self) -> None:
        """Bootstraps database pools, migrations, and service graphs.
        
        PHASE 7: API composes ONLY its required services, not worker or desktop components.
        """
        if self.is_initialized:
            return

        logger.info(f"Initializing ApplicationContainer with database: {self.db_url}")
        self.db = DatabaseManager(self.db_url)
        try:
            await self.db.create_tables(BaseORM.metadata)
        except Exception as ex:
            logger.warning(f"Database table creation warning: {ex}")

        # Event dispatcher for internal notifications
        self.event_dispatcher = EventDispatcher()
        
        # TaskManager for orchestration (query and command services)
        # Note: We don't use OrchestrationV2Container here to avoid composing worker-specific services
        self.task_manager = TaskManager(uow_factory=self.db.session_factory)
        
        # Registries for service discovery
        self.provider_registry = CanonicalModelRegistryService()
        self.tool_registry = ToolRegistry()
        self.plugin_registry = PluginRegistry()
        self.skill_registry = SkillRegistry()
        self.workflow_registry = WorkflowRegistry()
        
        # Query services
        self.context_service = ContextService()
        self.memory_query_service = MemoryQueryService()
        self.verification_query_service = VerificationQueryService()
        
        # Routing and worker coordination
        self.route_lock_service = RouteLockService()
        self.worker_status_query = SqlWorkerStatusQuery(
            SqlWorkerHeartbeatRepository(self.db.session_factory)
        )

        # Outbox: API process only SUBMITS events to outbox via repository
        # Actual PUBLISHING is owned by Worker process
        self.outbox_publisher = OutboxEventPublisher(
            outbox_repo=SqlOutboxRepository(self.db.session_factory),
            dispatcher=self.event_dispatcher.dispatch,
        )

        self.is_initialized = True
        logger.info("ApplicationContainer successfully bootstrapped (PHASE 7 - Process-specific composition).")

    async def shutdown(self) -> None:
        """Gracefully disposes database connections and resources."""
        if not self.is_initialized:
            return

        logger.info("Shutting down ApplicationContainer...")
        if self.outbox_publisher:
            await self.outbox_publisher.stop()
        if self.db:
            await self.db.close()
        # Clean up registries
        if self.tool_registry:
            await self.tool_registry.close()
        if self.plugin_registry:
            await self.plugin_registry.close()
        if self.skill_registry:
            await self.skill_registry.close()
        if self.context_service:
            await self.context_service.close()
        if self.memory_query_service:
            await self.memory_query_service.close()
        self.is_initialized = False
        logger.info("ApplicationContainer shutdown complete.")

    def get_uow(self) -> SqlUnitOfWork:
        """Returns a new UnitOfWork transaction context."""
        if not self.db:
            raise RuntimeError("ApplicationContainer is not initialized.")
        return SqlUnitOfWork(self.db.session_factory)
