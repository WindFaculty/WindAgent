"""Plan A A6 — worker-side typed runtime capability discovery.

``WorkerRuntimeCapabilityProbe`` implements ``RuntimeCapabilityPort`` by
observing the REAL worker composition: durable DB, durable queue, outbox
boundary, the worker itself, the real model route (durable route lock +
execution coordinator), Blender availability (env executable or PATH), and
the registered Story engine handlers. Every entry carries source/reason/
timestamp; nothing is invented — a component that is not composed or not
reporting healthy is DEGRADED/UNAVAILABLE with an honest reason.

The certification profile (``WINDAGENT_CERTIFICATION_MODE=1``) fails closed:
fake runtime, fixture model port, non-durable model route, and missing story
handlers are reported as ``fail_closed_flags``; ``is_fail_closed_ok`` is
False while any flag is active. Flags are also reported outside certification
(observability), but only certification interprets them as a gate.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import shutil
from typing import Any, List, Optional

from windagent_core.config.certification import certification_mode_enabled
from windagent_core.contracts.studio.capabilities import (
    CapabilityStatus,
    RuntimeCapability,
    RuntimeCapabilityProfile,
    WorkerRuntimeAttestation,
)

_BLENDER_ENV = "WINDAGENT_BLENDER_EXECUTABLE"


class WorkerRuntimeCapabilityProbe:
    """Observes the composed worker and reports typed capabilities (A6)."""

    def __init__(
        self,
        *,
        db: Any = None,
        task_queue: Any = None,
        route_lock_service: Any = None,
        coordinator: Any = None,
        handler_registry: Any = None,
        model_port: Any = None,
        studio_runtime: Any = None,
        completion_reconciler: Any = None,
        completion_recovery: Any = None,
        canonical_model: Optional[str] = None,
        endpoint_bindings: Optional[List[dict[str, Any]]] = None,
        fake_runtime_active: bool = False,
        blender_executable_env: str = _BLENDER_ENV,
        certification_mode: Optional[bool] = None,
    ) -> None:
        self._db = db
        self._task_queue = task_queue
        self._route_lock_service = route_lock_service
        self._coordinator = coordinator
        self._handler_registry = handler_registry
        self._model_port = model_port
        self._studio_runtime = studio_runtime
        self._completion_reconciler = completion_reconciler
        self._completion_recovery = completion_recovery
        self._canonical_model = canonical_model or ""
        self._endpoint_bindings = endpoint_bindings or []
        self._fake_runtime_active = fake_runtime_active
        self._blender_executable_env = blender_executable_env
        self._certification_mode = (
            certification_mode_enabled()
            if certification_mode is None
            else certification_mode
        )

    async def get_capabilities(self) -> RuntimeCapabilityProfile:
        capabilities: List[RuntimeCapability] = [
            self._durable_db(),
            self._queue(),
            self._outbox(),
            self._worker(),
            self._model_route(),
            self._blender(),
            self._story_engine(),
            self._unreal(),
        ]
        flags = self._fail_closed_flags(capabilities)
        return RuntimeCapabilityProfile(
            capabilities=capabilities,
            fail_closed_flags=flags,
            certification_mode=self._certification_mode,
        )

    async def get_attestation(self, *, worker_id: str) -> WorkerRuntimeAttestation:
        """Describe this worker's real Studio authority for durable heartbeat publication."""

        profile = await self.get_capabilities()
        handler_names = sorted(
            getattr(task_type, "value", str(task_type))
            for task_type in (self._handler_registry or {})
        )
        handler_digest = hashlib.sha256("\n".join(handler_names).encode()).hexdigest()
        identities = [
            {
                "binding_id": str(binding.get("id") or ""),
                "endpoint_id": str(binding.get("endpoint_id") or ""),
                "provider_model_id": str(binding.get("provider_model_id") or ""),
            }
            for binding in self._endpoint_bindings
            if binding.get("id") and binding.get("endpoint_id") and binding.get("provider_model_id")
        ]
        try:
            process_version = importlib.metadata.version("windagent-worker")
        except importlib.metadata.PackageNotFoundError:
            process_version = "workspace"
        return WorkerRuntimeAttestation(
            worker_id=worker_id,
            source_sha=os.getenv("WINDAGENT_SOURCE_SHA", "unknown"),
            process_version=process_version,
            certification_mode=self._certification_mode,
            runtime_adapter=type(self._studio_runtime).__name__ if self._studio_runtime else "",
            completion_reconciler=(
                type(self._completion_reconciler).__name__
                if self._completion_reconciler
                else ""
            ),
            completion_recovery=(
                type(self._completion_recovery).__name__ if self._completion_recovery else ""
            ),
            handler_names=handler_names,
            handler_digest=handler_digest,
            model_port_type=type(self._model_port).__name__ if self._model_port else "",
            canonical_model=self._canonical_model,
            provider_route_ready=bool(identities),
            durable_route_lock=bool(getattr(self._route_lock_service, "is_durable", False)),
            endpoint_binding_identities=identities,
            fake_runtime=self._fake_runtime_active,
            capability_profile=profile,
        )

    # -- per-capability probes ---------------------------------------------

    def _durable_db(self) -> RuntimeCapability:
        if self._db is None:
            return RuntimeCapability(
                name="durable_db",
                status=CapabilityStatus.UNAVAILABLE,
                source="apps.worker.composition.WorkerContainer.db",
                reason="database manager not composed",
            )
        return RuntimeCapability(
            name="durable_db",
            status=CapabilityStatus.AVAILABLE,
            source="apps.worker.composition.WorkerContainer.db",
            reason="database manager composed; schema applied at bootstrap",
            metadata={"db_url_scheme": str(getattr(self._db, "url", "")).split(":", 1)[0]},
        )

    def _queue(self) -> RuntimeCapability:
        if self._task_queue is None:
            return RuntimeCapability(
                name="queue",
                status=CapabilityStatus.UNAVAILABLE,
                source="apps.worker.composition.WorkerContainer.task_queue",
                reason="durable task queue not composed",
            )
        return RuntimeCapability(
            name="queue",
            status=CapabilityStatus.AVAILABLE,
            source="apps.worker.composition.WorkerContainer.task_queue",
            reason="SqlDurableTaskQueue composed",
        )

    def _outbox(self) -> RuntimeCapability:
        if self._db is None:
            return RuntimeCapability(
                name="outbox",
                status=CapabilityStatus.UNAVAILABLE,
                source="storage.unit_of_work.SqlUnitOfWork",
                reason="database not composed; outbox unavailable",
            )
        return RuntimeCapability(
            name="outbox",
            status=CapabilityStatus.AVAILABLE,
            source="storage.unit_of_work.SqlUnitOfWork",
            reason="outbox submission rides the SQL unit of work",
        )

    def _worker(self) -> RuntimeCapability:
        return RuntimeCapability(
            name="worker",
            status=CapabilityStatus.AVAILABLE,
            source="apps.worker.composition.WorkerContainer",
            reason="this probe runs inside the independent worker process",
            metadata={"fake_runtime": self._fake_runtime_active},
        )

    def _model_route(self) -> RuntimeCapability:
        lock = self._route_lock_service
        if lock is None:
            return RuntimeCapability(
                name="model_route",
                status=CapabilityStatus.UNAVAILABLE,
                source="apps.worker.composition.WorkerContainer.route_lock_service",
                reason="route lock service not composed",
            )
        if self._coordinator is None:
            return RuntimeCapability(
                name="model_route",
                status=CapabilityStatus.UNAVAILABLE,
                source="apps.worker.composition.WorkerContainer.provider_execution_coordinator",
                reason="execution coordinator not composed",
            )
        durable = bool(getattr(lock, "is_durable", False))
        status = CapabilityStatus.AVAILABLE if durable else CapabilityStatus.UNAVAILABLE
        return RuntimeCapability(
            name="model_route",
            status=status,
            source="providers.routing.route_lock_service + routing.execution_coordinator",
            reason=(
                "durable route lock + endpoint coordinator composed"
                if durable
                else "route lock service is IN-MEMORY (dev/test only); cross-process route authority missing"
            ),
            metadata={
                "lock_durable": durable,
                "model_port_type": type(self._model_port).__name__ if self._model_port else None,
            },
        )

    def _blender(self) -> RuntimeCapability:
        executable = os.getenv(self._blender_executable_env, "")
        if executable and os.path.isfile(executable):
            return RuntimeCapability(
                name="blender",
                status=CapabilityStatus.AVAILABLE,
                source=f"env:{self._blender_executable_env}",
                reason="configured Blender executable exists",
                metadata={"executable": os.path.basename(executable)},
            )
        discovered = shutil.which("blender")
        if discovered:
            return RuntimeCapability(
                name="blender",
                status=CapabilityStatus.AVAILABLE,
                source="shutil.which('blender')",
                reason="Blender discovered on PATH",
                metadata={"executable": discovered},
            )
        if os.getenv("WINDAGENT_BLENDER_ENGINE", "").lower() in ("1", "true", "yes"):
            return RuntimeCapability(
                name="blender",
                status=CapabilityStatus.DEGRADED,
                source="env:WINDAGENT_BLENDER_ENGINE",
                reason="engine flag set but no Blender executable found; engine jobs fail closed",
            )
        return RuntimeCapability(
            name="blender",
            status=CapabilityStatus.UNAVAILABLE,
            source=f"env:{self._blender_executable_env} + shutil.which",
            reason="no Blender executable configured or discoverable",
        )

    def _story_engine(self) -> RuntimeCapability:
        registry = self._handler_registry
        if registry is None:
            return RuntimeCapability(
                name="story_engine",
                status=CapabilityStatus.UNAVAILABLE,
                source="apps.worker.composition.WorkerContainer.studio_runtime",
                reason="studio runtime not composed",
            )
        count = len(registry)
        if count == 0:
            return RuntimeCapability(
                name="story_engine",
                status=CapabilityStatus.UNAVAILABLE,
                source="windagent_intelligence.story.runtime_handlers.HANDLER_REGISTRY",
                reason="no story handlers registered",
            )
        return RuntimeCapability(
            name="story_engine",
            status=CapabilityStatus.AVAILABLE,
            source="windagent_intelligence.story.runtime_handlers.HANDLER_REGISTRY",
            reason=f"{count} frozen task handler(s) registered",
            metadata={
                "handler_count": count,
                "handler_digest": hashlib.sha256(
                    "\n".join(
                        sorted(
                            getattr(task_type, "value", str(task_type))
                            for task_type in registry
                        )
                    ).encode()
                ).hexdigest(),
            },
        )

    def _unreal(self) -> RuntimeCapability:
        return RuntimeCapability(
            name="unreal",
            status=CapabilityStatus.UNAVAILABLE,
            source="providers (future engine)",
            reason="Unreal engine capability is not composed in Roadmap 1",
        )

    # -- certification profile ----------------------------------------------

    def _fail_closed_flags(self, capabilities: List[RuntimeCapability]) -> List[str]:
        flags: List[str] = []
        by_name = {c.name: c for c in capabilities}
        if self._fake_runtime_active:
            flags.append("fake_runtime")
        if self._model_port is not None and bool(getattr(self._model_port, "fixture", False)):
            flags.append("fixture_model_port")
        route = by_name.get("model_route")
        if route is not None and route.status != CapabilityStatus.AVAILABLE:
            flags.append("non_durable_model_route")
        engine = by_name.get("story_engine")
        if engine is not None and engine.status != CapabilityStatus.AVAILABLE:
            flags.append("story_engine_unregistered")
        return flags


def blender_env_var() -> str:
    return _BLENDER_ENV


__all__ = [
    "WorkerRuntimeCapabilityProbe",
    "blender_env_var",
]
