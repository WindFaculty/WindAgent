"""Project/application service composer for the API composition root (Phase 7).

Constructs the task manager, query services, the namespaced durable V3 resource
service, and the observability log service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from windagent_storage.database.connection import DatabaseManager
from windagent_orchestration.task_manager.service import TaskManager
from windagent_context.services import ContextService
from windagent_memory.query import MemoryQueryService
from windagent_verification.query import VerificationQueryService
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.log_service import LogService
from windagent_api.composition.repositories import RepositoryBundle


@dataclass
class ProjectBundle:
    """Typed result of the project/application service composer."""

    task_manager: TaskManager
    context_service: ContextService
    memory_query_service: MemoryQueryService
    verification_query_service: VerificationQueryService
    v3_resource_service: V3ResourceService
    log_service: LogService


class ProjectComposer:
    """Constructs the application/query services for the API process."""

    def compose(
        self,
        db: DatabaseManager,
        repositories: RepositoryBundle,
        uow_factory: Callable[[], Any],
    ) -> ProjectBundle:
        task_manager = TaskManager(uow_factory=db.session_factory)
        v3_resource_service = V3ResourceService(
            uow_factory=uow_factory,
            repository_factory=repositories.v3_resource_repository_factory,
        )
        return ProjectBundle(
            task_manager=task_manager,
            context_service=ContextService(),
            memory_query_service=MemoryQueryService(),
            verification_query_service=VerificationQueryService(),
            v3_resource_service=v3_resource_service,
            log_service=LogService(),
        )


__all__ = ["ProjectBundle", "ProjectComposer"]