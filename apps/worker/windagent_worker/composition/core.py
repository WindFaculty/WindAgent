"""Always-on Worker core composition (Architecture V3 Phase 8)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from windagent_context.services import ContextService
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_memory.query import MemoryQueryService
from windagent_observability.events.dispatcher import EventDispatcher
from windagent_orchestration import OrchestrationContainer, OrchestrationV2Container
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_verification.query import VerificationQueryService

from windagent_worker.composition.settings import (
    CertificationPreflightError,
    WorkerRuntimeSettings,
)

logger = logging.getLogger("windagent.worker.composition.core")


@dataclass(frozen=True)
class CoreBundle:
    db: DatabaseManager
    uow_factory: Any
    event_dispatcher: EventDispatcher
    orchestration_container: OrchestrationContainer
    task_manager: Any
    execution_registry: ExecutionRuntimeRegistry
    context_service: ContextService
    memory_service: MemoryQueryService
    verification_service: VerificationQueryService


class CoreComposer:
    """Compose durable storage, orchestration, and the execution runtime."""

    async def compose(self, settings: WorkerRuntimeSettings) -> CoreBundle:
        db = DatabaseManager(settings.database_url)
        try:
            await db.upgrade_to_head(BaseORM.metadata)
        except Exception as ex:
            if settings.certification_enabled:
                raise CertificationPreflightError(
                    f"Certification database migration failed: {type(ex).__name__}"
                ) from ex
            logger.warning("Database migration warning: %s", ex)

        uow_factory = db.session_factory
        event_dispatcher = EventDispatcher()
        orchestration_container = OrchestrationContainer(uow_factory=uow_factory)
        if settings.fake_runtime:
            from windagent_execution.adapters.fake_runtime_adapter import (
                FakeRuntimeAdapter,
            )

            execution_registry = ExecutionRuntimeRegistry(
                default_adapter=FakeRuntimeAdapter(default_mode="success")
            )
        else:
            execution_registry = ExecutionRuntimeRegistry()

        return CoreBundle(
            db=db,
            uow_factory=uow_factory,
            event_dispatcher=event_dispatcher,
            orchestration_container=orchestration_container,
            task_manager=orchestration_container.task_manager,
            execution_registry=execution_registry,
            context_service=ContextService(),
            memory_service=MemoryQueryService(),
            verification_service=VerificationQueryService(),
        )

    @staticmethod
    def make_uow(uow_factory: Any) -> SqlUnitOfWork:
        return SqlUnitOfWork(uow_factory)

    @staticmethod
    async def close_database(db: DatabaseManager | None) -> None:
        if db is not None:
            await db.close()


__all__ = ["CoreBundle", "CoreComposer"]
