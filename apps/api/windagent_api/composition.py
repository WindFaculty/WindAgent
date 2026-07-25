"""
Canonical Application Composition Root for WindAgent V2 (Phase 16).
Provides a strongly-typed ApplicationContainer managing domain services, storage,
orchestration, providers, tools, and event buses without loose state objects.
"""

from __future__ import annotations
import logging
from typing import Optional, Any, Dict

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
from windagent_worker.runner import ProductionWorker

logger = logging.getLogger("windagent.api.composition")


class MockEventBus:
    """Canonical event bus interface placeholder for V2 composition root."""
    def __init__(self):
        self._handlers: Dict[str, list] = {}

    async def publish(self, topic: str, event: Any) -> None:
        pass

    async def subscribe(self, topic: str, handler: Any) -> None:
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)


class ApplicationContainer:
    """Strongly-typed composition root for WindAgent V2 applications."""

    def __init__(self, db_url: str = "sqlite+aiosqlite:///windagent.db"):
        self.db_url = db_url
        self.db: Optional[DatabaseManager] = None
        self.orchestration_container: Optional[OrchestrationV2Container] = None
        self.task_manager: Optional[TaskManager] = None
        self.execution_registry: Optional[ExecutionRuntimeRegistry] = None
        self.event_bus: Optional[MockEventBus] = None
        self.provider_registry: Optional[CanonicalModelRegistryService] = None
        self.route_lock_service: Optional[RouteLockService] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.is_initialized: bool = False

    async def bootstrap(self) -> None:
        """Bootstraps database pools, migrations, and service graphs."""
        if self.is_initialized:
            return

        logger.info(f"Initializing ApplicationContainer with database: {self.db_url}")
        self.db = DatabaseManager(self.db_url)
        try:
            await self.db.create_tables(BaseORM.metadata)
        except Exception as ex:
            logger.warning(f"Database table creation warning: {ex}")

        self.event_bus = MockEventBus()
        self.orchestration_container = OrchestrationV2Container(uow_factory=self.db.session_factory)
        self.task_manager = self.orchestration_container.task_manager
        self.execution_registry = ExecutionRuntimeRegistry()
        self.provider_registry = CanonicalModelRegistryService()
        self.route_lock_service = RouteLockService()
        self.tool_registry = ToolRegistry()

        self.is_initialized = True
        logger.info("ApplicationContainer successfully bootstrapped.")

    async def shutdown(self) -> None:
        """Gracefully disposes database connections and resources."""
        if not self.is_initialized:
            return

        logger.info("Shutting down ApplicationContainer...")
        if self.db:
            await self.db.close()
        self.is_initialized = False
        logger.info("ApplicationContainer shutdown complete.")

    def get_uow(self) -> SqlUnitOfWork:
        """Returns a new UnitOfWork transaction context."""
        if not self.db:
            raise RuntimeError("ApplicationContainer is not initialized.")
        return SqlUnitOfWork(self.db.session_factory)
