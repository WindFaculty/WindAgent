"""
Real runtime capability probe for /api/v3/studio (Plan C1).

Implements ``RuntimeCapabilityPort`` by observing the actual API composition:
database manager, durable queue adapter, worker heartbeat query, provider
registry, and the OrchestratorService Studio seam. No fake/mock fallback:
a component that is not composed or not reporting healthy is reported
UNAVAILABLE/DEGRADED with an honest reason. Plan A deepens individual probes
(A3 persistence, A4 orchestration seam, A5 worker runtime, A6 model route);
this provider only ever reports what the API process can observe today.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, List

from windagent_core.contracts.studio.capabilities import (
    CapabilityStatus,
    RuntimeCapability,
    RuntimeCapabilityProfile,
)

if TYPE_CHECKING:
    from windagent_api.composition import ApplicationContainer

logger = logging.getLogger("windagent.api.studio.capability")

_STUDIO_ORCHESTRATION = "studio_orchestration"
_STORY_ENGINE = "story_engine"
_MODEL_ROUTE = "model_route"
_WORKER = "worker"
_DURABLE_DB = "durable_db"
_QUEUE = "queue"
_OUTBOX = "outbox"


class ApiRuntimeCapabilityProvider:
    """Observes the live ApplicationContainer and reports typed capabilities."""

    def __init__(self, container: "ApplicationContainer") -> None:
        self.container = container

    async def get_capabilities(self) -> RuntimeCapabilityProfile:
        worker = await self._worker()
        model_route = self._model_route()
        capabilities: List[RuntimeCapability] = [
            self._durable_db(),
            self._queue(),
            self._outbox(),
            worker,
            model_route,
            self._studio_orchestration(),
            self._story_engine(worker=worker, model_route=model_route),
        ]
        return RuntimeCapabilityProfile(
            capabilities=capabilities,
            fail_closed_flags=self._fail_closed_flags(),
            certification_mode=os.getenv("WINDAGENT_CERTIFICATION_MODE") == "1",
        )

    def _durable_db(self) -> RuntimeCapability:
        db = self.container.db
        if db is None:
            return RuntimeCapability(
                name=_DURABLE_DB,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.db",
                reason="database manager not composed",
            )
        return RuntimeCapability(
            name=_DURABLE_DB,
            status=CapabilityStatus.AVAILABLE,
            source="composition.ApplicationContainer.db",
            reason="database manager composed; schema applied at bootstrap",
            metadata={"db_url_scheme": str(self.container.db_url).split(":", 1)[0]},
        )

    def _queue(self) -> RuntimeCapability:
        adapter = self.container.task_submission
        if adapter is None:
            return RuntimeCapability(
                name=_QUEUE,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.task_submission",
                reason="durable queue adapter not composed",
            )
        return RuntimeCapability(
            name=_QUEUE,
            status=CapabilityStatus.AVAILABLE,
            source="composition.ApplicationContainer.task_submission",
            reason="SqlWorkSubmissionAdapter composed",
        )

    def _outbox(self) -> RuntimeCapability:
        if self.container.db is None:
            return RuntimeCapability(
                name=_OUTBOX,
                status=CapabilityStatus.UNAVAILABLE,
                source="storage.unit_of_work.SqlUnitOfWork",
                reason="database not composed; outbox unavailable",
            )
        return RuntimeCapability(
            name=_OUTBOX,
            status=CapabilityStatus.AVAILABLE,
            source="storage.unit_of_work.SqlUnitOfWork",
            reason="outbox submission rides the SQL unit of work",
        )

    async def _worker(self) -> RuntimeCapability:
        query = self.container.worker_status_query
        if query is None:
            return RuntimeCapability(
                name=_WORKER,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.worker_status_query",
                reason="worker heartbeat query not composed",
            )
        try:
            status = await query.get_status(stale_after_seconds=30)
        except Exception as ex:  # pragma: no cover - defensive probe
            logger.warning("worker capability probe failed: %s", ex)
            return RuntimeCapability(
                name=_WORKER,
                status=CapabilityStatus.UNAVAILABLE,
                source="storage.repositories.worker_status",
                reason=f"heartbeat probe raised: {type(ex).__name__}",
            )
        if status.available:
            return RuntimeCapability(
                name=_WORKER,
                status=CapabilityStatus.AVAILABLE,
                source="storage.repositories.worker_status",
                reason=f"{status.active_workers} active worker(s), {status.active_leases} lease(s)",
            )
        return RuntimeCapability(
            name=_WORKER,
            status=CapabilityStatus.UNAVAILABLE,
            source="storage.repositories.worker_status",
            reason="no active worker heartbeat; durable execution is not running",
        )

    def _model_route(self) -> RuntimeCapability:
        route_enabled = os.getenv("WINDAGENT_STUDIO_MODEL_ROUTE", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if not route_enabled:
            return RuntimeCapability(
                name=_MODEL_ROUTE,
                status=CapabilityStatus.UNAVAILABLE,
                source="providers.registry.canonical_registry",
                reason="WINDAGENT_STUDIO_MODEL_ROUTE is not enabled; real model execution fails closed",
            )
        registry = self.container.provider_registry
        if registry is None:
            return RuntimeCapability(
                name=_MODEL_ROUTE,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.provider_registry",
                reason="provider registry not composed",
            )
        canonical_model = os.getenv("WINDAGENT_STUDIO_CANONICAL_MODEL", "").strip()
        durable = bool(getattr(registry, "is_durable", False))
        if not canonical_model:
            return RuntimeCapability(
                name=_MODEL_ROUTE,
                status=CapabilityStatus.DEGRADED,
                source="providers.registry.canonical_registry",
                reason="registry composed but no certification canonical model is selected",
                metadata={"registry_durable": durable},
            )
        resolver = getattr(registry, "get_exact_equivalent_endpoints", None)
        if resolver is None:
            return RuntimeCapability(
                name=_MODEL_ROUTE,
                status=CapabilityStatus.UNAVAILABLE,
                source="providers.registry.canonical_registry",
                reason="registry cannot resolve exact provider bindings",
                metadata={
                    "registry_durable": durable,
                    "canonical_model": canonical_model,
                },
            )
        try:
            bindings = list(resolver(canonical_model))
        except Exception as ex:  # pragma: no cover - defensive probe
            logger.warning("model route capability probe failed: %s", ex)
            return RuntimeCapability(
                name=_MODEL_ROUTE,
                status=CapabilityStatus.UNAVAILABLE,
                source="providers.registry.canonical_registry",
                reason=f"provider binding lookup raised: {type(ex).__name__}",
                metadata={
                    "registry_durable": durable,
                    "canonical_model": canonical_model,
                },
            )
        if not bindings:
            return RuntimeCapability(
                name=_MODEL_ROUTE,
                status=CapabilityStatus.UNAVAILABLE,
                source="providers.registry.canonical_registry",
                reason="no enabled exact-revision provider binding for canonical model",
                metadata={
                    "registry_durable": durable,
                    "canonical_model": canonical_model,
                    "binding_count": 0,
                },
            )
        return RuntimeCapability(
            name=_MODEL_ROUTE,
            status=CapabilityStatus.AVAILABLE,
            source="providers.registry.canonical_registry",
            reason="durable registry resolved enabled exact-revision provider binding(s)",
            metadata={
                "registry_durable": durable,
                "canonical_model": canonical_model,
                "binding_count": len(bindings),
            },
        )

    def _studio_orchestration(self) -> RuntimeCapability:
        orchestrator = self.container.orchestrator_service
        if orchestrator is None:
            return RuntimeCapability(
                name=_STUDIO_ORCHESTRATION,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.orchestrator_service",
                reason="orchestrator not composed",
            )
        seam = getattr(orchestrator, "_studio_run_extension", None)
        if seam is not None:
            return RuntimeCapability(
                name=_STUDIO_ORCHESTRATION,
                status=CapabilityStatus.AVAILABLE,
                source="orchestration.orchestrator_service.studio_run_extension",
                reason="Studio run authority seam wired (Plan A A4)",
            )
        return RuntimeCapability(
            name=_STUDIO_ORCHESTRATION,
            status=CapabilityStatus.UNAVAILABLE,
            source="orchestration.orchestrator_service.studio_run_extension",
            reason="Studio run authority awaits Plan A A4 handoff; V3 commands fail closed",
        )

    def _story_engine(
        self,
        *,
        worker: RuntimeCapability,
        model_route: RuntimeCapability,
    ) -> RuntimeCapability:
        runtime_enabled = os.getenv("WINDAGENT_STUDIO_RUNTIME", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if not runtime_enabled:
            return RuntimeCapability(
                name=_STORY_ENGINE,
                status=CapabilityStatus.UNAVAILABLE,
                source="worker story handlers",
                reason="WINDAGENT_STUDIO_RUNTIME is not enabled for this runtime profile",
            )
        if worker.status != CapabilityStatus.AVAILABLE:
            return RuntimeCapability(
                name=_STORY_ENGINE,
                status=CapabilityStatus.UNAVAILABLE,
                source="worker story handlers",
                reason="no live durable worker heartbeat for Story task execution",
            )
        if model_route.status != CapabilityStatus.AVAILABLE:
            return RuntimeCapability(
                name=_STORY_ENGINE,
                status=CapabilityStatus.UNAVAILABLE,
                source="worker story handlers",
                reason="real model route is unavailable; Story execution fails closed",
            )
        return RuntimeCapability(
            name=_STORY_ENGINE,
            status=CapabilityStatus.AVAILABLE,
            source="worker story handlers",
            reason="Studio runtime enabled with a live durable worker and real model binding",
        )

    @staticmethod
    def _fail_closed_flags() -> List[str]:
        """Report unsafe certification composition without exposing secrets."""

        if os.getenv("WINDAGENT_CERTIFICATION_MODE") != "1":
            return []
        flags: List[str] = []
        if os.getenv("WINDAGENT_FAKE_RUNTIME", "").lower() in ("1", "true", "yes"):
            flags.append("fake_runtime_active")
        if os.getenv("WINDAGENT_MODEL_BACKEND", "").lower() in ("mock", "fake", "fixture"):
            flags.append("non_real_model_backend_active")
        if os.getenv("WINDAGENT_STUDIO_RUNTIME", "").lower() in ("1", "true", "yes") and os.getenv(
            "WINDAGENT_STUDIO_MODEL_ROUTE", ""
        ).lower() not in ("1", "true", "yes"):
            flags.append("studio_model_route_disabled")
        return flags


__all__ = ["ApiRuntimeCapabilityProvider"]
