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
- Outbox submission (via Unit of Work)
- Worker status query

NOT composed (separate process):
- Production Worker
- Worker event loop
- Tool subprocess runtime directly
- Desktop supervisor
"""

from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
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
from windagent_observability.events.dispatcher import EventDispatcher
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter
from windagent_storage.security.encryption import decrypt
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_execution.worktree.context import WorktreeContextManager
from windagent_orchestration.orchestrator_service import OrchestratorService
from windagent_orchestration.release.rollout import MultiAgentReleasePolicy
from windagent_observability.release_metrics import ReleaseTelemetry
from windagent_providers.routing.endpoint_adapter_resolver import EndpointAdapterResolver
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator

logger = logging.getLogger("windagent.api.composition")


class ApplicationContainer:
    """Strongly-typed composition root for WindAgent V2 applications (PHASE 7).
    
    Composes ONLY services that API needs:
    - Database & Unit of Work for persistence
    - TaskManager for orchestration (query/command)
    - Registries for discovery (providers, tools, plugins, skills, workflows)
    - Context, Memory, Verification for query services
    - Observability for monitoring
    - Outbox submission via Unit of Work (no publisher loop)
    - Worker status query for health checks
    
    Does NOT compose:
    - Production Worker (separate process)
    - Worker event loop (separate process)
    - Tool subprocess runtime directly (executed via registry)
    - Desktop supervisor (separate process)
    """

    def __init__(self, db_url: str = "sqlite+aiosqlite:///windagent.db"):
        self.db_url = db_url
        self.release_policy = MultiAgentReleasePolicy.from_environment()
        self.release_telemetry = ReleaseTelemetry()
        self.db: Optional[DatabaseManager] = None
        self.task_manager: Optional[TaskManager] = None
        self.event_dispatcher: Optional[EventDispatcher] = None
        self.provider_registry: Optional[CanonicalModelRegistryService] = None
        self.route_lock_service: Optional[RouteLockService] = None
        self.execution_registry: Optional[ExecutionRuntimeRegistry] = None
        self.worktree_manager: Optional[WorktreeContextManager] = None
        self.provider_execution_coordinator: Optional[EndpointExecutionCoordinator] = None
        self.orchestrator_service: Optional[OrchestratorService] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.plugin_registry: Optional[PluginRegistry] = None
        self.skill_registry: Optional[SkillRegistry] = None
        self.workflow_registry: Optional[WorkflowRegistry] = None
        self.context_service: Optional[ContextService] = None
        self.memory_query_service: Optional[MemoryQueryService] = None
        self.verification_query_service: Optional[VerificationQueryService] = None
        self.worker_status_query: Optional[WorkerStatusQueryPort] = None
        self.task_submission: Optional[SqlWorkSubmissionAdapter] = None
        self.is_initialized: bool = False

    async def bootstrap(self) -> None:
        """Bootstraps database pools, migrations, and service graphs.
        
        PHASE 7: API composes ONLY its required services, not worker or desktop components.
        """
        if self.is_initialized:
            return

        logger.info(f"Initializing ApplicationContainer with database: {self.db_url}")
        self.db = DatabaseManager(
            self.db_url,
            release_telemetry=self.release_telemetry,
        )
        try:
            if os.getenv("WINDAGENT_ENV", "").lower() == "production":
                backup_root = os.getenv("WINDAGENT_RELEASE_BACKUP_ROOT")
                if self.db_url.startswith("sqlite+aiosqlite:///"):
                    if not backup_root:
                        raise RuntimeError(
                            "WINDAGENT_RELEASE_BACKUP_ROOT is required before a production migration"
                        )
                    backup = await asyncio.to_thread(
                        self.db.create_pre_migration_backup, backup_root
                    )
                    if backup is not None:
                        logger.info("Created pre-migration SQLite backup at %s", backup)
                else:
                    evidence = os.getenv("WINDAGENT_EXTERNAL_BACKUP_EVIDENCE")
                    if not evidence or not Path(evidence).exists():
                        raise RuntimeError(
                            "WINDAGENT_EXTERNAL_BACKUP_EVIDENCE must reference a verified "
                            "PostgreSQL backup before a production migration"
                        )
            # Phase 1 (G1.1): runtime bootstraps schema through the canonical
            # Alembic migration workflow instead of ad-hoc create_all.
            await self.db.upgrade_to_head(BaseORM.metadata)
        except Exception as ex:
            if os.getenv("WINDAGENT_ENV") == "production":
                # Fail closed: a partially-migrated schema must not serve traffic.
                raise
            logger.warning(f"Database migration warning: {ex}")

        # Event dispatcher for internal notifications
        self.event_dispatcher = EventDispatcher()
        
        # TaskManager for orchestration (query and command services)
        # Note: We don't use OrchestrationV2Container here to avoid composing worker-specific services
        self.task_manager = TaskManager(uow_factory=self.db.session_factory)

        # Durable task submission: enqueue into SQL durable queue (shared with Worker).
        self.task_submission = SqlWorkSubmissionAdapter(self.db.session_factory)
        
        from windagent_storage.database.sync_factory import make_sync_session_factory
        from windagent_storage.repositories.v3_routing_repositories import (
            SQLEndpointBindingRepository,
            SQLProviderRoutingAuditRepository,
        )
        from windagent_storage.repositories.v3_repositories import (
            SQLEndpointRegistryRepository,
            SQLEndpointStateRepository,
            SQLQuotaStateRepository,
            SQLRouteAttemptRepository,
            SQLRouteLockRepository,
        )

        sync_factory = make_sync_session_factory(self.db_url)
        binding_repo = SQLEndpointBindingRepository(sync_factory())
        audit_repo = SQLProviderRoutingAuditRepository(sync_factory())
        lock_repo = SQLRouteLockRepository(sync_factory())

        # Registries for service discovery (DB-backed durable authority)
        self.provider_registry = CanonicalModelRegistryService(binding_repository=binding_repo)
        self.tool_registry = ToolRegistry()
        self.plugin_registry = PluginRegistry()
        self.skill_registry = SkillRegistry()
        self.workflow_registry = WorkflowRegistry()
        
        # Query services
        self.context_service = ContextService()
        self.memory_query_service = MemoryQueryService()
        self.verification_query_service = VerificationQueryService()
        
        # Routing and worker coordination
        from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet

        default_model = os.getenv("WINDAGENT_ORCHESTRATOR_CANONICAL_MODEL", "windagent/local-agent")
        self.route_lock_service = RouteLockService(
            ruleset=RoutingRuleSet(
                rules=[
                    RoutingRule(
                        rule_id="orchestrator-local-agent",
                        rule_version=1,
                        canonical_model_id=default_model,
                        description="Phase-2 conversation control plane",
                    )
                ]
            ),
            lock_repository=lock_repo,
            audit_repository=audit_repo,
        )
        self.execution_registry = ExecutionRuntimeRegistry()
        # Phase 5: the deployment (not a browser/API request) chooses which
        # repository coding agents may modify.  Leaving this unset deliberately
        # disables coding-agent dispatch rather than falling back to the API
        # process's current directory.
        workspace_root = os.getenv("WINDAGENT_WORKSPACE_ROOT")
        if workspace_root:
            self.worktree_manager = WorktreeContextManager(
                workspace_root,
                worktree_root=os.getenv("WINDAGENT_WORKTREE_ROOT") or None,
                quarantine_root=os.getenv("WINDAGENT_WORKTREE_QUARANTINE_ROOT") or None,
            )
        else:
            if os.getenv("WINDAGENT_ENV") == "production":
                raise RuntimeError(
                    "WINDAGENT_WORKSPACE_ROOT is required for production coding-agent execution"
                )
            logger.warning(
                "WINDAGENT_WORKSPACE_ROOT is unset; coding-agent Git worktree isolation is disabled"
            )
        self.provider_execution_coordinator = EndpointExecutionCoordinator(
            adapter_resolver=EndpointAdapterResolver(decrypt),
            endpoint_registry=SQLEndpointRegistryRepository(sync_factory()),
            endpoint_state=SQLEndpointStateRepository(sync_factory()),
            quota_state=SQLQuotaStateRepository(sync_factory()),
            attempt_log=SQLRouteAttemptRepository(sync_factory()),
            release_telemetry=self.release_telemetry,
        )
        self.orchestrator_service = OrchestratorService(
            self.db.session_factory,
            self.execution_registry,
            self.route_lock_service,
            self.provider_execution_coordinator,
            self.worktree_manager,
            self.release_policy,
            self.release_telemetry,
        )
        self.worker_status_query = SqlWorkerStatusQuery(
            SqlWorkerHeartbeatRepository(self.db.session_factory)
        )

        # Outbox: API submits events via get_uow().record_outbox_event() only.
        # Publishing loop is owned exclusively by the Worker process (Phase 6).

        # Durable task submission: API enqueues tasks into the SQL durable queue
        # so the independent Worker process can claim them (PHASE 14 wiring).
        self.task_submission = SqlWorkSubmissionAdapter(self.db.session_factory)

        self.is_initialized = True
        logger.info("ApplicationContainer successfully bootstrapped (PHASE 7 - Process-specific composition).")

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

        # 2. Close database connection LAST
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
