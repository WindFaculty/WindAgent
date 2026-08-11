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
import os
from typing import Optional, Any

from windagent_core.config.certification import (
    certification_mode_conflict,
    certification_mode_enabled,
)
from windagent_core.contracts.studio.capabilities import REQUIRED_STORY_TASK_HANDLERS
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
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

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


class CertificationPreflightError(RuntimeError):
    """Worker composition cannot satisfy the certification profile."""


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _load_ir_document(artifact_root: str, revision_id: str):
    """Load the engine-neutral IR document for a revision (VP3D Stage A).

    The IR is written into the artifact workspace when the revision's shot
    plan is locked / migrated. Returns None (fail closed) when absent so a
    RENDER step never submits garbage.
    """
    import json

    from windagent_core.domain.video_production.production_ir import (
        ProductionIrDocument,
    )

    path = os.path.join(
        artifact_root, "video_production_3d", "ir", f"{revision_id}.ir.json"
    )
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return ProductionIrDocument.model_validate(json.load(fh))
    except (OSError, ValueError) as exc:
        logger.warning(f"Failed to load IR for revision {revision_id}: {exc}")
        return None


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
        self.task_queue: Optional[SqlDurableTaskQueue] = None
        self.lease_manager: Optional[DurableTaskLeaseManager] = None
        self.heartbeat_repo: Optional[SqlWorkerHeartbeatRepository] = None
        self.orchestration_container: Optional[OrchestrationV2Container] = None
        self.task_manager: Optional[TaskManager] = None
        self.execution_registry: Optional[ExecutionRuntimeRegistry] = None
        self.provider_registry: Optional[CanonicalModelRegistryService] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.workflow_registry: Optional[WorkflowRegistry] = None
        self.intelligence_pipeline: Optional[IntelligencePipeline] = None
        self.context_service: Optional[ContextService] = None
        self.memory_service: Optional[MemoryQueryService] = None
        self.verification_service: Optional[VerificationQueryService] = None
        self.outbox_publisher: Optional[OutboxEventPublisher] = None
        self.route_lock_service: Optional[RouteLockService] = None
        self.provider_execution_coordinator: Optional[Any] = None  # Plan A A6
        self.studio_route_lock_service: Optional[RouteLockService] = None  # Plan A A6
        self.studio_model_port: Optional[Any] = None  # Plan A A6 (guarded)
        self.studio_capability_probe: Optional[Any] = None  # Plan A A6 (guarded)
        self.studio_endpoint_bindings: list[dict[str, Any]] = []
        self.studio_runtime: Optional[Any] = None  # Plan A A5 (guarded)
        self.studio_reconciler: Optional[Any] = None  # Plan A A5 (guarded)
        self.studio_recovery: Optional[Any] = None  # Plan A A5 (guarded)
        self.production_engine: Optional[Any] = None  # VP3D Phase 3 (guarded)
        self.production_executor: Optional[Any] = None  # VP3D Stage A consumer seam
        self.production_step_executor: Optional[Any] = None  # VP3D Stage A RENDER dispatch
        self.production_workflow: Optional[Any] = None  # VP3D Stage A durable engine w/ executor
        self.asset_resolver: Optional[Any] = None  # VP3D Phase 5 Universal Asset Gateway (guarded)
        self.asset_trust_gate: Optional[Any] = None  # VP3D Phase 6 trust gate (guarded)
        self.asset_normalizer: Optional[Any] = None  # VP3D Phase 7 Asset Normalizer (guarded)
        self.normalization_config: Optional[Any] = None  # VP3D Phase 7 default config
        self.is_initialized: bool = False

    async def bootstrap(self) -> None:
        """Bootstraps all Worker process services.
        
        PHASE 7: Worker composes ALL its required services for independent operation.
        """
        if self.is_initialized:
            return

        # Honor WINDAGENT_DATABASE_URL so the Worker process shares the API's DB
        # (the two processes must target the same durable store). PHASE 14.
        self.db_url = os.getenv("WINDAGENT_DATABASE_URL", self.db_url)

        logger.info(f"Initializing WorkerContainer with database: {self.db_url}")
        
        # Database layer
        self.db = DatabaseManager(self.db_url)
        try:
            # Phase 1 (G1.1): canonical Alembic migration workflow.
            await self.db.upgrade_to_head(BaseORM.metadata)
        except Exception as ex:
            if certification_mode_enabled():
                raise CertificationPreflightError(
                    f"Certification database migration failed: {type(ex).__name__}"
                ) from ex
            logger.warning(f"Database migration warning: {ex}")
        
        self.uow_factory = self.db.session_factory
        
        # Event dispatcher
        self.event_dispatcher = EventDispatcher()
        
        # Durable queue, lease management, and heartbeat repository (Worker-specific)
        self.task_queue = SqlDurableTaskQueue(self.db.session_factory) if self.db else None
        self.lease_manager = DurableTaskLeaseManager(session_factory=self.db.session_factory)
        self.heartbeat_repo = SqlWorkerHeartbeatRepository(self.db.session_factory) if self.db else None
        
        # Orchestration engine (Worker needs full orchestration for execution)
        self.orchestration_container = OrchestrationV2Container(uow_factory=self.uow_factory)
        self.task_manager = self.orchestration_container.task_manager
        
        # Execution runtime (Worker executes tools directly)
        # FakeRuntimeAdapter seam for E2E / mock-safe task scenarios (WINDAGENT_FAKE_RUNTIME=1).
        if os.getenv("WINDAGENT_FAKE_RUNTIME", "").lower() in ("1", "true", "yes"):
            from windagent_execution.adapters.fake_runtime_adapter import FakeRuntimeAdapter
            self.execution_registry = ExecutionRuntimeRegistry(default_adapter=FakeRuntimeAdapter(default_mode="success"))
        else:
            self.execution_registry = ExecutionRuntimeRegistry()
        
        # Registries (DB-backed durable authority shared with API)
        from windagent_storage.database.sync_factory import make_sync_session_factory
        from windagent_storage.repositories.v3_routing_repositories import (
            SQLEndpointBindingRepository,
            SQLProviderRoutingAuditRepository,
        )
        from windagent_storage.repositories.v3_repositories import (
            SQLRouteLockRepository,
        )
        sync_factory = make_sync_session_factory(self.db_url)
        binding_repo = SQLEndpointBindingRepository(sync_factory())
        audit_repo = SQLProviderRoutingAuditRepository(sync_factory())
        lock_repo = SQLRouteLockRepository(sync_factory())
        self.provider_registry = CanonicalModelRegistryService(binding_repository=binding_repo)
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
        self.route_lock_service = RouteLockService(lock_repository=lock_repo, audit_repository=audit_repo)

        # Plan A A6 — real Studio model route (guarded by the studio runtime
        # switch). Composes the canonical coordinator over the same durable
        # endpoint/lock repos as the API process; the RouteLockedModelPort is
        # the real PreproductionModelPort handed to B handlers. The canonical
        # model is a compatibility input (WINDAGENT_STUDIO_CANONICAL_MODEL),
        # never hidden domain policy.
        if os.getenv("WINDAGENT_STUDIO_RUNTIME", "").lower() in ("1", "true", "yes"):
            self._register_studio_provider_route(
                sync_factory, lock_repo, audit_repo, binding_repo
            )

        # Plan A A5 — Studio Story worker runtime (guarded). Registers the
        # studio.* execution capability over the frozen B handler registry;
        # without WINDAGENT_STUDIO_MODEL_ROUTE=1 the model port stays None and
        # model-backed handlers fail closed with STUDIO_MODEL_PORT_UNAVAILABLE.
        if os.getenv("WINDAGENT_STUDIO_RUNTIME", "").lower() in ("1", "true", "yes"):
            self._register_studio_runtime()

        self.validate_certification_preflight()
        
        # Outbox: Worker OWNS the outbox publisher - publishes events to message bus
        self.outbox_publisher = OutboxEventPublisher(
            outbox_repo=SqlOutboxRepository(self.uow_factory),
            dispatcher=self.event_dispatcher.dispatch,
        )
        await self.outbox_publisher.start()

        # VP3D Phase 3 — guarded production engine registration.
        # Only composed when explicitly enabled (WINDAGENT_BLENDER_ENGINE=1);
        # the Blender adapter is never registered from memory/config defaults so
        # existing worker bootstraps stay unaffected.
        if os.getenv("WINDAGENT_BLENDER_ENGINE", "").lower() in ("1", "true", "yes"):
            from windagent_tools.production_engines.blender import create_blender_engine_adapter

            artifact_root = os.getenv("WINDAGENT_ARTIFACT_ROOT", "artifacts")
            self.production_engine = create_blender_engine_adapter(
                artifact_root=artifact_root,
                state_dir=os.path.join(artifact_root, "video_production_3d", "blender_state"),
            )
            logger.info("BlenderEngineAdapter registered (VP3D Phase 3, guarded).")
            
            # VP3D Stage A consumer cutover: the worker-facing facade over the
            # engine port lives in the orchestration layer (concrete executor with
            # filesystem persistence — core keeps only the protocol/type contract).
            # Workflow RENDER steps dispatch through the executor, which persists
            # receipts for durable re-attach on worker restart.
            from windagent_orchestration.production import (
                ProductionEngineExecutor,
                ProductionRunStore,
                ProductionStepExecutor,
                ProductionWorkflowEngine,
            )
            from windagent_workflows.video_production.definition import (
                build_production_step_nodes,
            )

            self.production_executor = ProductionEngineExecutor(
                port=self.production_engine,
                state_dir=os.path.join(
                    artifact_root, "video_production_3d", "executor_state"
                ),
            )
            logger.info("ProductionEngineExecutor registered over BlenderEngineAdapter (VP3D Stage A).")

            # Runtime call site: a queued RENDER step actually goes through the
            # engine-neutral executor -> ProductionEnginePort + IR. The IR is
            # loaded per revision from the artifact workspace (written at
            # LOCK_SHOT_PLAN / migration time); a missing IR fails closed.
            self.production_step_executor = ProductionStepExecutor(
                engine=self.production_executor,
                ir_source=lambda revision_id: _load_ir_document(
                    artifact_root, revision_id
                ),
            )
            self.production_workflow = ProductionWorkflowEngine(
                store=ProductionRunStore(
                    os.path.join(artifact_root, "video_production_3d", "runs")
                ),
                executor=self.production_step_executor,
                step_nodes=build_production_step_nodes(),
            )
            logger.warning(
                "DEPRECATED AUTHORITY: ProductionWorkflowEngine composed behind "
                "WINDAGENT_BLENDER_ENGINE for VP3D paths. It rejects Studio "
                "(studio.story.*) steps; new Story runs belong to OrchestratorService."
            )
            logger.info("ProductionStepExecutor + ProductionWorkflowEngine wired (VP3D Stage A cutover).")

        # VP3D Phase 5/6 — Universal Asset Gateway (guarded).
        # All 3D asset acquisition goes through AssetResolverPort; nothing in
        # the workflow/Director talks to Internet/Mesh/Blender directly. The
        # Phase 6 trust gate is composed here so RESOLVED is only reachable
        # through an APPROVE verdict.
        if os.getenv("WINDAGENT_ASSET_GATEWAY", "").lower() in ("1", "true", "yes"):
            self._register_asset_gateway()

        # VP3D Phase 7 — Asset Normalization (guarded). Only the gateway's
        # RESOLVED assets may pass through the normalizer before the Scene
        # Compiler consumes them.
        if os.getenv("WINDAGENT_ASSET_NORMALIZER", "").lower() in ("1", "true", "yes"):
            self._register_asset_normalizer()
        
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

    def validate_certification_preflight(self) -> None:
        """Fail startup unless the real Studio certification stack is composed."""

        if not certification_mode_enabled():
            return

        missing: list[str] = []
        if certification_mode_conflict():
            missing.append("consistent certification flag")
        if not _env_enabled("WINDAGENT_STUDIO_RUNTIME"):
            missing.append("WINDAGENT_STUDIO_RUNTIME=1")
        if not _env_enabled("WINDAGENT_STUDIO_MODEL_ROUTE"):
            missing.append("WINDAGENT_STUDIO_MODEL_ROUTE=1")
        if not os.getenv("WINDAGENT_STUDIO_CANONICAL_MODEL", "").strip():
            missing.append("canonical model")
        configured_db = os.getenv("WINDAGENT_DATABASE_URL", "").strip()
        if not configured_db or ":memory:" in configured_db.lower():
            missing.append("durable WINDAGENT_DATABASE_URL")
        if self.db is None or self.uow_factory is None:
            missing.append("durable DB")
        if not isinstance(self.task_queue, SqlDurableTaskQueue):
            missing.append("durable queue")
        if type(self.studio_runtime).__name__ != "StudioRuntimeAdapter":
            missing.append("StudioRuntimeAdapter")
        try:
            resolved = self.execution_registry.resolve_adapter(
                "studio.story.idea.generate"
            )
            if resolved is not self.studio_runtime:
                missing.append("registered studio capability")
        except Exception:
            missing.append("registered studio capability")
        reconciler = getattr(self.studio_reconciler, "_reconciler", None)
        if type(reconciler).__name__ != "StudioCompletionReconciler":
            missing.append("StudioCompletionReconciler")
        if type(self.studio_recovery).__name__ != "StudioCompletionRecovery":
            missing.append("StudioCompletionRecovery")
        if type(self.studio_model_port).__name__ != "RouteLockedModelPort":
            missing.append("RouteLockedModelPort")
        if self.studio_route_lock_service is None:
            missing.append("durable route lock")
        if self.provider_execution_coordinator is None:
            missing.append("provider execution coordinator")
        handlers = getattr(self.studio_runtime, "_handler_registry", {}) or {}
        registered_handlers = {
            getattr(task_type, "value", str(task_type)) for task_type in handlers
        }
        if not REQUIRED_STORY_TASK_HANDLERS <= registered_handlers:
            missing.append("required story handlers")
        if not self.studio_endpoint_bindings:
            missing.append("enabled exact provider binding")
        if _env_enabled("WINDAGENT_FAKE_RUNTIME"):
            missing.append("fake runtime disabled")

        if missing:
            raise CertificationPreflightError(
                "Certification worker preflight failed: " + ", ".join(missing)
            )

    def _register_studio_provider_route(self, sync_factory, lock_repo, audit_repo, binding_repo) -> None:
        """Compose the real A6 provider adapter: coordinator + studio route lock.

        Only runs under ``WINDAGENT_STUDIO_RUNTIME=1``. The coordinator is the
        same canonical execution path as the API process (durable endpoint
        registry/state/quota/attempt repos); the studio route lock reuses the
        durable lock repo under a Studio ruleset. The model port is composed
        ONLY when ``WINDAGENT_STUDIO_MODEL_ROUTE=1`` — otherwise handlers fail
        closed with STUDIO_MODEL_PORT_UNAVAILABLE (no mock fallback).
        """
        from windagent_providers.routing.endpoint_adapter_resolver import (
            EndpointAdapterResolver,
        )
        from windagent_providers.routing.execution_coordinator import (
            EndpointExecutionCoordinator,
        )
        from windagent_storage.repositories.v3_repositories import (
            SQLEndpointRegistryRepository,
            SQLEndpointStateRepository,
            SQLQuotaStateRepository,
            SQLRouteAttemptRepository,
        )
        from windagent_storage.security.encryption import decrypt

        self.provider_execution_coordinator = EndpointExecutionCoordinator(
            adapter_resolver=EndpointAdapterResolver(decrypt),
            endpoint_registry=SQLEndpointRegistryRepository(sync_factory()),
            endpoint_state=SQLEndpointStateRepository(sync_factory()),
            quota_state=SQLQuotaStateRepository(sync_factory()),
            attempt_log=SQLRouteAttemptRepository(sync_factory()),
        )
        if os.getenv("WINDAGENT_STUDIO_MODEL_ROUTE", "").lower() in ("1", "true", "yes"):
            from windagent_worker.studio_model_port import (
                RouteLockedModelPort,
                build_studio_ruleset,
            )

            canonical_model = os.getenv("WINDAGENT_STUDIO_CANONICAL_MODEL", "") or None
            self.studio_endpoint_bindings = (
                binding_repo.get_exact_equivalent_endpoints(canonical_model)
                if canonical_model
                else []
            )
            self.studio_route_lock_service = RouteLockService(
                ruleset=build_studio_ruleset(canonical_model),
                lock_repository=lock_repo,
                audit_repository=audit_repo,
            )
            self.studio_model_port = RouteLockedModelPort(
                self.studio_route_lock_service,
                self.provider_execution_coordinator,
                canonical_model=canonical_model,
            )
            logger.info(
                "RouteLockedModelPort composed (Plan A A6); "
                f"canonical model: {canonical_model or 'default'}."
            )
        else:
            self.studio_model_port = None
            logger.info(
                "WINDAGENT_STUDIO_MODEL_ROUTE unset; model-backed Studio tasks fail closed "
                "(STUDIO_MODEL_PORT_UNAVAILABLE)."
            )

    def _register_studio_runtime(self) -> None:
        """Compose the A5 Studio worker runtime + completion recovery (guarded).

        Runs only under ``WINDAGENT_STUDIO_RUNTIME=1``; the fake runtime guard
        is detected from the composed default adapter so certification mode
        fails closed even when ``WINDAGENT_FAKE_RUNTIME`` is set. The A6
        capability probe observes the real composition (durable DB, queue,
        model route, Blender, story handlers) with certification fail-closed
        flags.
        """
        from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY
        from windagent_orchestration.studio.service import StudioRunService
        from windagent_providers.studio import WorkerRuntimeCapabilityProbe
        from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
        from windagent_worker.studio_runtime import (
            StudioCompletionRecovery,
            StudioRuntimeAdapter,
        )

        fake_active = (
            type(self.execution_registry.default_adapter).__name__ == "FakeRuntimeAdapter"
        )
        studio_runtime = StudioRuntimeAdapter(
            handler_registry=HANDLER_REGISTRY,
            session_factory=self.uow_factory,
            model_port=self.studio_model_port,
            fake_runtime_active=fake_active,
            worker_id="studio-worker",
        )
        self.execution_registry.register_capability("studio", studio_runtime)
        self.studio_runtime = studio_runtime
        self.studio_reconciler = StudioRunService(
            self.uow_factory,
            StudioTaskSubmissionAdapter(self.uow_factory),
        )
        self.studio_recovery = StudioCompletionRecovery(
            self.uow_factory, self.studio_reconciler
        )
        self.studio_capability_probe = WorkerRuntimeCapabilityProbe(
            db=self.db,
            task_queue=self.task_queue,
            route_lock_service=self.studio_route_lock_service,
            coordinator=self.provider_execution_coordinator,
            handler_registry=HANDLER_REGISTRY,
            model_port=self.studio_model_port,
            studio_runtime=studio_runtime,
            completion_reconciler=getattr(self.studio_reconciler, "_reconciler", None),
            completion_recovery=self.studio_recovery,
            canonical_model=os.getenv("WINDAGENT_STUDIO_CANONICAL_MODEL", ""),
            endpoint_bindings=self.studio_endpoint_bindings,
            fake_runtime_active=fake_active,
        )
        logger.info(
            "StudioRuntimeAdapter registered (Plan A A5/A6); "
            f"fake runtime guard: {'ACTIVE' if fake_active else 'inactive'}; "
            f"real model port: {'composed' if self.studio_model_port else 'NONE (fail closed)'}."
        )

    def _register_asset_gateway(self) -> None:
        """Compose the Universal Asset Gateway (VP3D Phase 5/6).

        - AssetResolverPort over the adapter registry;
        - local library adapter over WINDAGENT_ASSET_LIBRARY_ROOT
          (fail-closed: an absent/unlicensed library resolves to nothing
          usable — QUARANTINED/REJECTED, never RESOLVED);
        - Internet adapter WITHOUT injected search/acquisition backends stays
          REQUIRES_CONFIG and every call fails closed (no unguarded network);
        - the Phase 6 trust gate (MediaAssetTrustGate) is the ONLY path to a
          RESOLVED verdict.
        """
        from pathlib import Path as _Path

        from windagent_providers.assets import (
            AssetAdapterRegistry,
            AssetResolver,
            InternetAssetAdapter,
            LocalAssetAdapter,
        )
        from windagent_tools.media_assets.trust_gate import MediaAssetTrustGate

        registry = AssetAdapterRegistry()
        library_root = os.getenv("WINDAGENT_ASSET_LIBRARY_ROOT", "data/assets/library")
        registry.register(LocalAssetAdapter(_Path(library_root).resolve()))

        # Internet adapter: search/acquisition backends are injected from the
        # tools-side media-asset pipeline (SSRF-safe download, MIME sniffing,
        # content-addressed store). Not configured here until a search provider
        # is wired -> adapter stays REQUIRES_CONFIG and every call fails closed.
        registry.register(InternetAssetAdapter())

        self.asset_trust_gate = MediaAssetTrustGate()
        self.asset_resolver = AssetResolver(
            registry,
            trust=self.asset_trust_gate,
        )
        logger.info(
            "AssetResolverPort registered with trust gate (VP3D Phase 5/6, guarded)."
        )

    def _register_asset_normalizer(self) -> None:
        """Compose the Asset Normalizer (VP3D Phase 7).

        - host-side pipeline over the content-addressed store + bundle root;
        - engine work (sandboxed import of FBX/USD/BLEND, LOD decimation,
          deterministic preview render) uses the REAL Blender runner when a
          policy-satisfying Blender executable is available, otherwise the
          normalizer is still wired but every engine job fails closed.
        """
        from pathlib import Path as _Path

        from windagent_core.domain.video_production.asset_normalization import (
            NormalizationConfig,
        )
        from windagent_tools.media_assets.normalization import (
            AssetNormalizationPipeline,
            AssetNormalizer,
        )
        from windagent_tools.media_assets.normalization.bundle import (
            AssetBundlePublisher,
        )
        from windagent_tools.media_assets.store import ContentAddressedStore

        artifact_root = os.getenv("WINDAGENT_ARTIFACT_ROOT", "artifacts")
        store = ContentAddressedStore(
            _Path(artifact_root) / "video_production_3d" / "assets" / "store"
        )
        job_runner = None
        executable_path = os.getenv("WINDAGENT_BLENDER_EXECUTABLE", "")
        if executable_path and _Path(executable_path).is_file():
            try:
                from windagent_tools.production_engines.blender.asset_pipeline import (
                    BlenderAssetJobRunner,
                )

                job_runner = BlenderAssetJobRunner(
                    executable_path=executable_path,
                    artifact_root=str(_Path(artifact_root) / "video_production_3d"),
                    state_dir=str(
                        _Path(artifact_root) / "video_production_3d" / "blender_state"
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - engine optional
                logger.warning(f"Blender asset job runner unavailable: {exc}")

        pipeline = AssetNormalizationPipeline(
            store=store,
            bundle_publisher=AssetBundlePublisher(
                str(_Path(artifact_root) / "video_production_3d" / "bundles")
            ),
            job_runner=job_runner,
        )
        self.asset_normalizer = AssetNormalizer(pipeline)
        self.normalization_config = NormalizationConfig()
        logger.info(
            "AssetNormalizerPort registered (VP3D Phase 7, guarded); "
            f"engine job runner: {'blender' if job_runner else 'NONE (fail closed)'}."
        )
