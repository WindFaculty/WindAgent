"""Studio route/runtime/recovery composition and certification gate."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from windagent_core.contracts.studio.capabilities import REQUIRED_STORY_TASK_HANDLERS
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue

from windagent_worker.composition.settings import (
    CertificationPreflightError,
    WorkerRuntimeSettings,
)

logger = logging.getLogger("windagent.worker.composition.studio")


@dataclass(frozen=True)
class StudioRouteBundle:
    provider_execution_coordinator: Any
    studio_route_lock_service: Any | None
    studio_model_port: Any | None
    studio_endpoint_bindings: list[dict[str, Any]]


@dataclass(frozen=True)
class StudioRuntimeBundle:
    studio_runtime: Any
    studio_reconciler: Any
    studio_recovery: Any
    studio_capability_probe: Any


class StudioComposer:
    """Compose the guarded Studio model route and runtime capability."""

    @staticmethod
    def compose_provider_route(
        settings: WorkerRuntimeSettings,
        sync_factory: Callable[[], Any],
        lock_repo: Any,
        audit_repo: Any,
        binding_repo: Any,
        provider_management_repo: Any | None = None,
    ) -> StudioRouteBundle:
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

        coordinator = EndpointExecutionCoordinator(
            adapter_resolver=EndpointAdapterResolver(decrypt),
            endpoint_registry=SQLEndpointRegistryRepository(sync_factory()),
            endpoint_state=SQLEndpointStateRepository(sync_factory()),
            quota_state=SQLQuotaStateRepository(sync_factory()),
            attempt_log=SQLRouteAttemptRepository(sync_factory()),
        )
        route_lock_service = None
        model_port = None
        endpoint_bindings: list[dict[str, Any]] = []
        if settings.studio_model_route:
            from windagent_worker.studio_model_port import (
                RouteLockedModelPort,
                build_studio_ruleset,
            )

            canonical_model = settings.studio_canonical_model or None
            if canonical_model:
                ruleset = build_studio_ruleset(canonical_model)
                endpoint_bindings = binding_repo.get_exact_equivalent_endpoints(
                    canonical_model
                )
            else:
                from windagent_providers.management import RoutingPolicyProjection

                ruleset = (
                    RoutingPolicyProjection(provider_management_repo).load_ruleset()
                    if provider_management_repo is not None
                    else build_studio_ruleset(None)
                )
                seen: set[str] = set()
                for rule in ruleset.sorted_rules():
                    for binding in binding_repo.get_exact_equivalent_endpoints(
                        rule.canonical_model_id
                    ):
                        binding_id = str(binding.get("id", ""))
                        if binding_id not in seen:
                            endpoint_bindings.append(binding)
                            seen.add(binding_id)
            route_lock_service = RouteLockService(
                ruleset=ruleset,
                lock_repository=lock_repo,
                audit_repository=audit_repo,
            )
            model_port = RouteLockedModelPort(
                route_lock_service,
                coordinator,
                canonical_model=canonical_model,
            )
        return StudioRouteBundle(
            provider_execution_coordinator=coordinator,
            studio_route_lock_service=route_lock_service,
            studio_model_port=model_port,
            studio_endpoint_bindings=endpoint_bindings,
        )

    @staticmethod
    def compose_runtime(
        settings: WorkerRuntimeSettings,
        *,
        db: Any,
        task_queue: Any,
        execution_registry: Any,
        uow_factory: Any,
        route_bundle: StudioRouteBundle,
    ) -> StudioRuntimeBundle:
        from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY
        from windagent_orchestration.studio.service import StudioRunService
        from windagent_providers.studio import WorkerRuntimeCapabilityProbe
        from windagent_storage.studio.task_submission import (
            StudioTaskSubmissionAdapter,
        )
        from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork
        from windagent_worker.studio_runtime import (
            StudioCompletionRecovery,
            StudioRuntimeAdapter,
        )

        fake_active = (
            type(execution_registry.default_adapter).__name__ == "FakeRuntimeAdapter"
        )
        studio_runtime = StudioRuntimeAdapter(
            handler_registry=HANDLER_REGISTRY,
            session_factory=uow_factory,
            model_port=route_bundle.studio_model_port,
            fake_runtime_active=fake_active,
            worker_id="studio-worker",
        )
        execution_registry.register_capability("studio", studio_runtime)
        studio_reconciler = StudioRunService(
            lambda: StudioUnitOfWork(uow_factory),
            StudioTaskSubmissionAdapter(uow_factory),
        )
        studio_recovery = StudioCompletionRecovery(uow_factory, studio_reconciler)
        probe = WorkerRuntimeCapabilityProbe(
            db=db,
            task_queue=task_queue,
            route_lock_service=route_bundle.studio_route_lock_service,
            coordinator=route_bundle.provider_execution_coordinator,
            handler_registry=HANDLER_REGISTRY,
            model_port=route_bundle.studio_model_port,
            studio_runtime=studio_runtime,
            completion_reconciler=getattr(studio_reconciler, "_reconciler", None),
            completion_recovery=studio_recovery,
            canonical_model=settings.studio_canonical_model,
            endpoint_bindings=route_bundle.studio_endpoint_bindings,
            fake_runtime_active=fake_active,
        )
        return StudioRuntimeBundle(
            studio_runtime=studio_runtime,
            studio_reconciler=studio_reconciler,
            studio_recovery=studio_recovery,
            studio_capability_probe=probe,
        )

    @staticmethod
    def validate_certification_preflight(
        settings: WorkerRuntimeSettings,
        *,
        db: Any,
        uow_factory: Any,
        task_queue: Any,
        execution_registry: Any,
        studio_runtime: Any,
        studio_reconciler: Any,
        studio_recovery: Any,
        studio_model_port: Any,
        studio_route_lock_service: Any,
        provider_execution_coordinator: Any,
        studio_endpoint_bindings: list[dict[str, Any]],
    ) -> None:
        if not settings.certification_enabled:
            return

        missing: list[str] = []
        if settings.certification_conflict:
            missing.append("consistent certification flag")
        if not settings.studio_runtime:
            missing.append("WINDAGENT_STUDIO_RUNTIME=1")
        if not settings.studio_model_route:
            missing.append("WINDAGENT_STUDIO_MODEL_ROUTE=1")
        if not settings.studio_canonical_model.strip():
            missing.append("canonical model")
        configured_db = settings.database_url.strip()
        if not configured_db or ":memory:" in configured_db.lower():
            missing.append("durable WINDAGENT_DATABASE_URL")
        if db is None or uow_factory is None:
            missing.append("durable DB")
        if not isinstance(task_queue, SqlDurableTaskQueue):
            missing.append("durable queue")
        if type(studio_runtime).__name__ != "StudioRuntimeAdapter":
            missing.append("StudioRuntimeAdapter")
        try:
            resolved = execution_registry.resolve_adapter(
                "studio.story.idea.generate"
            )
            if resolved is not studio_runtime:
                missing.append("registered studio capability")
        except Exception:
            missing.append("registered studio capability")
        reconciler = getattr(studio_reconciler, "_reconciler", None)
        if type(reconciler).__name__ != "StudioCompletionReconciler":
            missing.append("StudioCompletionReconciler")
        if type(studio_recovery).__name__ != "StudioCompletionRecovery":
            missing.append("StudioCompletionRecovery")
        if type(studio_model_port).__name__ != "RouteLockedModelPort":
            missing.append("RouteLockedModelPort")
        if studio_route_lock_service is None:
            missing.append("durable route lock")
        if provider_execution_coordinator is None:
            missing.append("provider execution coordinator")
        handlers = getattr(studio_runtime, "_handler_registry", {}) or {}
        registered_handlers = {
            getattr(task_type, "value", str(task_type)) for task_type in handlers
        }
        if not REQUIRED_STORY_TASK_HANDLERS <= registered_handlers:
            missing.append("required story handlers")
        if not studio_endpoint_bindings:
            missing.append("enabled exact provider binding")
        if settings.fake_runtime:
            missing.append("fake runtime disabled")
        if missing:
            raise CertificationPreflightError(
                "Certification worker preflight failed: " + ", ".join(missing)
            )


__all__ = [
    "StudioComposer",
    "StudioRouteBundle",
    "StudioRuntimeBundle",
]
