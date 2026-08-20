"""Studio composer for the API composition root (Phase 7).

Constructs the Studio run service, the worker-attested capability provider, and
the Studio application service.  The capability provider observes the container;
the application service binds Plan A ports at handoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork
from windagent_orchestration.studio.service import StudioRunService
from windagent_api.services.studio_application_service import StudioApplicationService
from windagent_api.services.studio_capability_provider import ApiRuntimeCapabilityProvider
from windagent_api.composition.repositories import RepositoryBundle

if TYPE_CHECKING:
    from windagent_api.composition.container import ApplicationContainer


@dataclass
class StudioBundle:
    """Typed result of the studio application composer."""

    studio_capability_provider: ApiRuntimeCapabilityProvider
    studio_application_service: StudioApplicationService


class StudioComposer:
    """Constructs the Studio V3 surface for the API process."""

    @staticmethod
    def compose_run_service(
        db: DatabaseManager,
        studio_task_submission: StudioTaskSubmissionAdapter,
    ) -> StudioRunService:
        """Build the durable Studio run authority (Plan A A4 seam)."""
        return StudioRunService(
            lambda: StudioUnitOfWork(db.session_factory),
            studio_task_submission,
        )

    @staticmethod
    def compose_application(
        container: "ApplicationContainer",
        repositories: RepositoryBundle,
    ) -> StudioBundle:
        """Build the capability provider and the Plan C1 application service."""
        capability = ApiRuntimeCapabilityProvider(container)
        studio_application_service = StudioApplicationService(
            orchestrator=container.studio_run_service,
            run_query=repositories.run_query,
            event_query=repositories.event_query,
            capability=capability,
            series_repo=repositories.studio_reads,
            episodes_repo=repositories.episodes_repo,
            revisions_repo=repositories.revisions_repo,
            artifacts_repo=repositories.artifacts_repo,
            approvals_repo=repositories.approvals_repo,
        )
        return StudioBundle(
            studio_capability_provider=capability,
            studio_application_service=studio_application_service,
        )


__all__ = ["StudioBundle", "StudioComposer"]