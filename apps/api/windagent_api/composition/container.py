"""Canonical ApplicationContainer for the WindAgent V2 API (Phase 7).

The container orchestrates typed composer result bundles; concrete construction
lives in the focused composer modules.  The API owns HTTP validation,
application/query services, durable command submission, realtime, and health
only.  It instantiates zero execution-runtime registries and zero worktree
context managers.

NOT composed (separate process):
- Production Worker
- Worker event loop
- Tool subprocess runtime directly
- Desktop supervisor
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from windagent_core.contracts.workers import WorkerStatusQueryPort
from windagent_observability.events.dispatcher import EventDispatcher
from windagent_orchestration.orchestrator_service import OrchestratorService
from windagent_orchestration.release.rollout import MultiAgentReleasePolicy
from windagent_observability.release_metrics import ReleaseTelemetry
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

from windagent_api.composition.database import (
    DatabaseComposer,
    make_demo_canonical_model_persister,
)
from windagent_api.composition.repositories import RepositoryComposer
from windagent_api.composition.providers import ProviderComposer
from windagent_api.composition.realtime import RealtimeComposer
from windagent_api.composition.studio import StudioComposer
from windagent_api.composition.projects import ProjectComposer
from windagent_api.composition.health import HealthComposer

logger = logging.getLogger("windagent.api.composition")


class ApplicationContainer:
    """Strongly-typed composition root for the WindAgent V2 API (PHASE 7).

    Composes ONLY services the API needs:
    - Database & Unit of Work for persistence
    - TaskManager for orchestration (query/command)
    - Registries for discovery (providers, tools, plugins, skills, workflows)
    - Context, Memory, Verification for query services
    - Observability for monitoring
    - Outbox submission via Unit of Work (no publisher loop)
    - Worker status query for health checks
    - Realtime hub over a read-only SQL replay adapter

    Does NOT compose:
    - Production Worker (separate process)
    - Worker event loop (separate process)
    - Execution runtime registry / worktree manager (Worker ownership)
    - Desktop supervisor (separate process)
    """

    def __init__(self, db_url: str = "sqlite+aiosqlite:///windagent.db"):
        self.db_url = db_url
        self.release_policy = MultiAgentReleasePolicy.from_environment()
        self.release_telemetry = ReleaseTelemetry()
        self.db: Optional[Any] = None
        self.task_manager: Optional[Any] = None
        self.event_dispatcher: Optional[EventDispatcher] = None
        self.provider_registry: Optional[Any] = None
        self.route_lock_service: Optional[Any] = None
        self.provider_execution_coordinator: Optional[Any] = None
        self.orchestrator_service: Optional[OrchestratorService] = None
        self.studio_application_service: Optional[Any] = None
        self.studio_capability_provider: Optional[Any] = None
        self.v3_resource_service: Optional[Any] = None
        self.routing_authority_bridge: Optional[Any] = None
        self.provider_management_service: Optional[Any] = None
        self.provider_probe_service: Optional[Any] = None
        self.routing_policy_projection: Optional[Any] = None
        self.log_service: Optional[Any] = None
        self.tool_registry: Optional[Any] = None
        self.plugin_registry: Optional[Any] = None
        self.skill_registry: Optional[Any] = None
        self.workflow_registry: Optional[Any] = None
        self.context_service: Optional[Any] = None
        self.memory_query_service: Optional[Any] = None
        self.verification_query_service: Optional[Any] = None
        self.worker_status_query: Optional[WorkerStatusQueryPort] = None
        self.worker_heartbeat_repo: Optional[Any] = None
        self.task_submission: Optional[Any] = None
        self.realtime_replay: Optional[Any] = None
        self.realtime_hub: Optional[Any] = None
        self.studio_task_submission: Optional[Any] = None
        self.studio_run_service: Optional[Any] = None
        self.is_initialized: bool = False

    async def bootstrap(self) -> None:
        """Bootstraps database pools, migrations, and service graphs.

        PHASE 7: API composes ONLY its required services, not worker or desktop
        components.  No execution runtime registry and no worktree manager are
        ever constructed.
        """
        if self.is_initialized:
            return

        logger.info(f"Initializing ApplicationContainer with database: {self.db_url}")

        # 1. Database + canonical migration (production backup evidence gate).
        database = DatabaseComposer()
        db_bundle = await database.compose(self.db_url, self.release_telemetry)
        self.db = db_bundle.db

        # 2. Event dispatcher for internal notifications.
        self.event_dispatcher = EventDispatcher()

        # 3. Phase 6: canonical realtime hub. The API owns a read-only replay
        # adapter and the WS hub; the Worker remains the only outbox publisher
        # owner. Live delivery is wired to the dispatcher wildcard.
        realtime = RealtimeComposer()
        realtime_bundle = realtime.compose(self.db, self.event_dispatcher)
        self.realtime_replay = realtime_bundle.realtime_replay
        self.realtime_hub = realtime_bundle.realtime_hub

        # 4. Concrete SQL repositories (durable command submission, routing
        # authority, worker status, Studio read adapters).
        repositories = RepositoryComposer()
        repo_bundle = repositories.compose(self.db, self.db_url)
        self.worker_heartbeat_repo = repo_bundle.worker_heartbeat_repo
        self.task_submission = repo_bundle.task_submission
        self.studio_task_submission = repo_bundle.studio_task_submission
        self.route_receipt_repo = repo_bundle.route_receipt_repo

        # 5. Application/query services.
        projects = ProjectComposer()
        project_bundle = projects.compose(self.db, repo_bundle, self.get_uow)
        self.task_manager = project_bundle.task_manager
        self.context_service = project_bundle.context_service
        self.memory_query_service = project_bundle.memory_query_service
        self.verification_query_service = project_bundle.verification_query_service
        self.v3_resource_service = project_bundle.v3_resource_service
        self.log_service = project_bundle.log_service

        # 6. Provider/routing services.
        providers = ProviderComposer()
        provider_bundle = providers.compose(repo_bundle, self.release_telemetry)
        self.provider_registry = provider_bundle.provider_registry
        self.tool_registry = provider_bundle.tool_registry
        self.plugin_registry = provider_bundle.plugin_registry
        self.skill_registry = provider_bundle.skill_registry
        self.workflow_registry = provider_bundle.workflow_registry
        self.route_lock_service = provider_bundle.route_lock_service
        self.provider_execution_coordinator = provider_bundle.provider_execution_coordinator
        self.provider_management_service = provider_bundle.provider_management_service
        self.provider_probe_service = provider_bundle.provider_probe_service
        self.routing_policy_projection = provider_bundle.routing_policy_projection

        # 7. Studio run authority (Plan A A4 seam) before the orchestrator.
        self.studio_run_service = StudioComposer.compose_run_service(
            self.db, repo_bundle.studio_task_submission
        )

        # 8. Control-plane OrchestratorService.  The API composes it with NO
        # execution runtime and NO worktree manager: dispatch/reattach/cancel
        # methods fail closed or return queued results for Worker pickup.
        self.orchestrator_service = OrchestratorService(
            self.db.session_factory,
            None,  # no execution runtime (Worker ownership)
            self.route_lock_service,
            self.provider_execution_coordinator,
            None,  # no worktree manager (Worker ownership)
            self.release_policy,
            self.release_telemetry,
            studio_run_extension=self.studio_run_service,
            repo_factory=lambda session: MultiAgentRepository(session),
        )

        # 9. Studio V3 surface. The capability provider observes this
        # container; the application service binds Plan A ports at handoff.
        studio_bundle = StudioComposer.compose_application(self, repo_bundle)
        self.studio_capability_provider = studio_bundle.studio_capability_provider
        self.studio_application_service = studio_bundle.studio_application_service

        # 10. Health/readiness query.
        health_bundle = HealthComposer.compose(repo_bundle)
        self.worker_status_query = health_bundle.worker_status_query

        # 11. Phase 4 (P4-R4A): bridge the durable v3_resources:routing_rules
        # authority onto the composed RouteLockService runtime ruleset. The
        # ruleset is a rebuildable projection; the SQL records remain the
        # canonical authority. Refresh at startup so already-persisted rules
        # are reflected (empty SQL preserves the deployment fallback ruleset).
        self.routing_authority_bridge = ProviderComposer.compose_routing_bridge(
            self.v3_resource_service,
            self.route_lock_service,
        )
        await self.routing_authority_bridge.refresh_ruleset()

        self.is_initialized = True
        logger.info(
            "ApplicationContainer successfully bootstrapped "
            "(PHASE 7 - Process-specific composition)."
        )

    async def shutdown(self) -> None:
        """Gracefully disposes database connections and resources in canonical shutdown order."""
        if not self.is_initialized:
            return

        logger.info("Shutting down ApplicationContainer...")
        # 1. Clean up registries and query services
        for name, service in [
            ("workflow_registry", self.workflow_registry),
            ("tool_registry", self.tool_registry),
            ("plugin_registry", self.plugin_registry),
            ("skill_registry", self.skill_registry),
            ("context_service", self.context_service),
            ("memory_query_service", self.memory_query_service),
            ("verification_query_service", self.verification_query_service),
        ]:
            if service is not None and hasattr(service, "close"):
                try:
                    res = service.close()
                    if hasattr(res, "__await__"):
                        await res
                except Exception as ex:
                    logger.warning(f"Error closing {name}: {ex}")

        # 2. Stop the realtime hub before the database is closed so no
        # fallback task can touch a torn-down pool.  Unsubscribe it from the
        # dispatcher wildcard first so the graph does not retain a stopped hub.
        if self.event_dispatcher is not None and self.realtime_hub is not None:
            try:
                self.event_dispatcher.unsubscribe("*", self.realtime_hub.publish)
            except Exception as ex:
                logger.warning(f"Error unsubscribing realtime hub: {ex}")
        if self.realtime_hub is not None:
            try:
                await self.realtime_hub.stop()
            except Exception as ex:
                logger.warning(f"Error stopping realtime hub: {ex}")

        # 3. Close database connection LAST
        if self.db and hasattr(self.db, "close"):
            try:
                await self.db.close()
            except Exception as ex:
                logger.warning(f"Error closing database: {ex}")

        self.is_initialized = False
        logger.info("ApplicationContainer shutdown complete.")

    def get_uow(self) -> SqlUnitOfWork:
        """Returns a new UnitOfWork transaction context."""
        if not self.db:
            raise RuntimeError("ApplicationContainer is not initialized.")
        return SqlUnitOfWork(self.db.session_factory)

    def get_video_production_uow(self):
        """Returns a new VideoProductionUnitOfWork transaction context.

        The composition root is the only layer allowed to construct concrete
        unit-of-work adapters; request handlers receive it via dependencies.
        """
        if not self.db:
            raise RuntimeError("ApplicationContainer is not initialized.")
        from windagent_storage.unit_of_work.video_production_uow import (
            VideoProductionUnitOfWork,
        )

        return VideoProductionUnitOfWork(self.db.session_factory)

    async def seed_demo_profile(self) -> None:
        """Install the opt-in demo profile (WINDAGENT_PROFILE=demo).

        Idempotent: existing resources are left untouched.  The canonical-model
        persistence is delegated to the composition adapter so the application
        seed module never imports ORM/database.
        """
        if self.v3_resource_service is None:
            return
        from windagent_api.services.v3_demo_seed import seed_demo_data
        from windagent_storage.database.sync_factory import make_sync_session_factory

        persister = make_demo_canonical_model_persister(
            make_sync_session_factory(self.db_url)
        )
        await seed_demo_data(
            self.v3_resource_service,
            canonical_model_persister=persister,
            orchestrator_service=self.orchestrator_service,
        )
        # Phase 4 (P4-R4A): reflect the freshly seeded routing rules in the
        # composed RouteLockService runtime ruleset.
        if self.routing_authority_bridge is not None:
            await self.routing_authority_bridge.refresh_ruleset()


__all__ = ["ApplicationContainer"]