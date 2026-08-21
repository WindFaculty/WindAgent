"""Worker composition orchestrator (Architecture V3 Phase 8).

Concrete construction lives in focused composers.  This container preserves
the process-facing compatibility attributes used by the runner and tests while
owning only ordering, manifest, lifecycle, and delegation.
"""

from __future__ import annotations

import logging
from typing import Any

from windagent_worker.composition.assets import AssetComposer
from windagent_worker.composition.core import CoreComposer
from windagent_worker.composition.outbox import OutboxComposer
from windagent_worker.composition.providers import ProviderBundle, ProviderComposer
from windagent_worker.composition.queue import QueueComposer
from windagent_worker.composition.settings import (
    CertificationPreflightError,
    WorkerRuntimeSettings,
    validate_settings,
)
from windagent_worker.composition.studio import (
    StudioComposer,
    StudioRouteBundle,
)
from windagent_worker.composition.video import VideoComposer

logger = logging.getLogger("windagent.worker.composition")


class WorkerContainer:
    """Process-specific Worker composition root (PHASE 7 / Phase 8)."""

    def __init__(
        self,
        db_url: str = "sqlite+aiosqlite:///windagent.db",
        settings: WorkerRuntimeSettings | None = None,
    ) -> None:
        self.settings = settings or WorkerRuntimeSettings.from_environment(
            default_db_url=db_url
        )
        self.db_url = self.settings.database_url

        # Stable compatibility surface consumed by runner/entrypoint/tests.
        self.db: Any | None = None
        self.uow_factory: Any | None = None
        self.sql_uow_factory: Any | None = None
        self.event_dispatcher: Any | None = None
        self.task_queue: Any | None = None
        self.lease_manager: Any | None = None
        self.heartbeat_repo: Any | None = None
        self.orchestration_container: Any | None = None
        self.task_manager: Any | None = None
        self.execution_registry: Any | None = None
        self.provider_registry: Any | None = None
        self.tool_registry: Any | None = None
        self.workflow_registry: Any | None = None
        self.intelligence_pipeline: Any | None = None
        self.context_service: Any | None = None
        self.memory_service: Any | None = None
        self.verification_service: Any | None = None
        self.outbox_publisher: Any | None = None
        self.route_lock_service: Any | None = None
        self.provider_execution_coordinator: Any | None = None
        self.studio_route_lock_service: Any | None = None
        self.studio_model_port: Any | None = None
        self.studio_capability_probe: Any | None = None
        self.studio_endpoint_bindings: list[dict[str, Any]] = []
        self.studio_runtime: Any | None = None
        self.studio_reconciler: Any | None = None
        self.studio_recovery: Any | None = None
        self.production_engine: Any | None = None
        self.production_executor: Any | None = None
        self.production_step_executor: Any | None = None
        self.production_workflow: Any | None = None
        self.asset_resolver: Any | None = None
        self.asset_trust_gate: Any | None = None
        self.asset_normalizer: Any | None = None
        self.normalization_config: Any | None = None
        self.is_initialized = False

        self._core_composer = CoreComposer()
        self._queue_composer = QueueComposer()
        self._provider_composer = ProviderComposer()
        self._studio_composer = StudioComposer()
        self._outbox_composer = OutboxComposer()
        self._video_composer = VideoComposer()
        self._asset_composer = AssetComposer()
        self._provider_bundle: ProviderBundle | None = None

    def capability_manifest(self) -> dict[str, bool]:
        """Return the stable public capability manifest without side effects."""
        return {
            "studio": self.settings.studio_runtime,
            "provider_routing": self.settings.provider_routing,
            "blender": self.settings.blender_engine,
            "asset_gateway": self.settings.asset_gateway,
        }

    def validate_settings(self) -> None:
        validate_settings(self.settings)

    async def bootstrap(self) -> dict[str, bool]:
        """Compose the Worker graph in dependency/lifecycle order."""
        if self.is_initialized:
            return self.capability_manifest()
        self.validate_settings()
        logger.info("Initializing WorkerContainer with database: %s", self.db_url)

        core = await self._core_composer.compose(self.settings)
        self.db = core.db
        self.uow_factory = core.uow_factory
        self.sql_uow_factory = core.sql_uow_factory
        self.event_dispatcher = core.event_dispatcher
        self.orchestration_container = core.orchestration_container
        self.task_manager = core.task_manager
        self.execution_registry = core.execution_registry
        self.context_service = core.context_service
        self.memory_service = core.memory_service
        self.verification_service = core.verification_service

        queue = self._queue_composer.compose(self.uow_factory)
        self.task_queue = queue.task_queue
        self.lease_manager = queue.lease_manager
        self.heartbeat_repo = queue.heartbeat_repo

        providers = self._provider_composer.compose(self.db_url)
        self._provider_bundle = providers
        self.provider_registry = providers.provider_registry
        self.tool_registry = providers.tool_registry
        self.workflow_registry = providers.workflow_registry
        self.intelligence_pipeline = providers.intelligence_pipeline
        self.route_lock_service = providers.route_lock_service

        if self.settings.studio_runtime:
            self._register_studio_provider_route(
                providers.sync_factory,
                providers.lock_repo,
                providers.audit_repo,
                providers.binding_repo,
                providers.provider_management_repo,
            )
            self._register_studio_runtime()

        # Fail before starting any publisher/background task.
        self.validate_certification_preflight()
        self.outbox_publisher = await self._outbox_composer.compose(
            self.uow_factory, self.event_dispatcher
        )

        video = self._video_composer.compose(self.settings)
        self.production_engine = video.production_engine
        self.production_executor = video.production_executor
        self.production_step_executor = video.production_step_executor
        self.production_workflow = video.production_workflow

        if self.settings.asset_gateway:
            self._register_asset_gateway()
        if self.settings.asset_normalizer:
            self._register_asset_normalizer()

        self.is_initialized = True
        logger.info("WorkerContainer bootstrapped (Architecture V3 Phase 8).")
        return self.capability_manifest()

    async def shutdown(self) -> None:
        """Stop publisher/services before closing the durable database."""
        if not self.is_initialized:
            return
        await self._outbox_composer.shutdown(self.outbox_publisher)
        for name, service in (
            ("tool_registry", self.tool_registry),
            ("provider_registry", self.provider_registry),
            ("workflow_registry", self.workflow_registry),
            ("intelligence_pipeline", self.intelligence_pipeline),
            ("context_service", self.context_service),
            ("memory_service", self.memory_service),
            ("verification_service", self.verification_service),
        ):
            if service is None or not hasattr(service, "close"):
                continue
            try:
                result = service.close()
                if hasattr(result, "__await__"):
                    await result
            except Exception as ex:
                logger.warning("Error closing worker service %s: %s", name, ex)
        try:
            await self._core_composer.close_database(self.db)
        except Exception as ex:
            logger.warning("Error closing worker db: %s", ex)
        self.is_initialized = False

    def get_uow(self):
        if self.uow_factory is None:
            raise RuntimeError("WorkerContainer is not initialized.")
        return self._core_composer.make_uow(self.uow_factory)

    def validate_certification_preflight(self) -> None:
        self._studio_composer.validate_certification_preflight(
            self.settings,
            db=self.db,
            uow_factory=self.uow_factory,
            task_queue=self.task_queue,
            execution_registry=self.execution_registry,
            studio_runtime=self.studio_runtime,
            studio_reconciler=self.studio_reconciler,
            studio_recovery=self.studio_recovery,
            studio_model_port=self.studio_model_port,
            studio_route_lock_service=self.studio_route_lock_service,
            provider_execution_coordinator=self.provider_execution_coordinator,
            studio_endpoint_bindings=self.studio_endpoint_bindings,
        )

    def _register_studio_provider_route(
        self,
        sync_factory,
        lock_repo,
        audit_repo,
        binding_repo,
        provider_management_repo,
    ) -> None:
        """Compatibility delegate for the focused Studio composer."""
        route = self._studio_composer.compose_provider_route(
            self.settings,
            sync_factory,
            lock_repo,
            audit_repo,
            binding_repo,
            provider_management_repo,
        )
        self.provider_execution_coordinator = route.provider_execution_coordinator
        self.studio_route_lock_service = route.studio_route_lock_service
        self.studio_model_port = route.studio_model_port
        self.studio_endpoint_bindings = route.studio_endpoint_bindings

    def _studio_route_bundle(self) -> StudioRouteBundle:
        if self.provider_execution_coordinator is None:
            raise RuntimeError("Studio provider route is not composed.")
        return StudioRouteBundle(
            provider_execution_coordinator=self.provider_execution_coordinator,
            studio_route_lock_service=self.studio_route_lock_service,
            studio_model_port=self.studio_model_port,
            studio_endpoint_bindings=self.studio_endpoint_bindings,
        )

    def _register_studio_runtime(self) -> None:
        """Compatibility delegate for the focused Studio composer."""
        runtime = self._studio_composer.compose_runtime(
            self.settings,
            db=self.db,
            task_queue=self.task_queue,
            execution_registry=self.execution_registry,
            uow_factory=self.uow_factory,
            route_bundle=self._studio_route_bundle(),
        )
        self.studio_runtime = runtime.studio_runtime
        self.studio_reconciler = runtime.studio_reconciler
        self.studio_recovery = runtime.studio_recovery
        self.studio_capability_probe = runtime.studio_capability_probe

    def _register_asset_gateway(self) -> None:
        """Compatibility delegate used by guarded bootstrap and legacy tests."""
        gateway = self._asset_composer.compose_gateway(self.settings)
        self.asset_resolver = gateway.asset_resolver
        self.asset_trust_gate = gateway.asset_trust_gate

    def _register_asset_normalizer(self) -> None:
        """Compatibility delegate used by guarded bootstrap and legacy tests."""
        normalizer = self._asset_composer.compose_normalizer(self.settings)
        self.asset_normalizer = normalizer.asset_normalizer
        self.normalization_config = normalizer.normalization_config


# Preserve the canonical public module path used by runtime attestations.
WorkerContainer.__module__ = "windagent_worker.composition"

__all__ = ["CertificationPreflightError", "WorkerContainer"]
