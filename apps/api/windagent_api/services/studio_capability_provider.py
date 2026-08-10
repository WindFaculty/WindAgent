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
from typing import TYPE_CHECKING, Any, List

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
        capabilities: List[RuntimeCapability] = [
            self._durable_db(),
            self._queue(),
            self._outbox(),
            await self._worker(),
            self._model_route(),
            self._studio_orchestration(),
            self._story_engine(),
        ]
        return RuntimeCapabilityProfile(
            capabilities=capabilities,
            fail_closed_flags=[],  # no fake/mock/bypass is ever composed
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
        registry = self.container.provider_registry
        if registry is None:
            return RuntimeCapability(
                name=_MODEL_ROUTE,
                status=CapabilityStatus.UNAVAILABLE,
                source="composition.ApplicationContainer.provider_registry",
                reason="provider registry not composed",
            )
        durable = bool(getattr(registry, "is_durable", False))
        return RuntimeCapability(
            name=_MODEL_ROUTE,
            status=CapabilityStatus.AVAILABLE,
            source="providers.registry.canonical_registry",
            reason="registry composed; route/model validation is certification-scoped (A6)",
            metadata={"registry_durable": durable},
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

    def _story_engine(self) -> RuntimeCapability:
        return RuntimeCapability(
            name=_STORY_ENGINE,
            status=CapabilityStatus.UNAVAILABLE,
            source="worker story handlers",
            reason="durable Story task handlers await Plan A A5 handoff",
        )


__all__ = ["ApiRuntimeCapabilityProvider"]
