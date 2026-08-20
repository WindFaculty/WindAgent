"""Provider health probe + model discovery service (Phase 10).

``ProviderProbeService`` performs a REAL adapter network call (``health``) and
model discovery (``list_models``) for an endpoint, then persists the probe
status/timestamp and discovered endpoint/model bindings through the injected
repository. It never fabricates reachability, latency, or auth validity.

The adapter factory is injectable so tests can drive the real adapter code path
against a controlled local/mock HTTP transport with a synthetic test-only key.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from windagent_core.contracts.providers.provider_management import (
    ProviderAuditEvent,
    ProviderManagementRepositoryPort,
    ProviderProbeResult,
)
from windagent_providers.base.errors import ProviderFailure


class ProviderNotFoundError(Exception):
    """Raised when a probe targets an endpoint that does not exist."""

    def __init__(self, endpoint_id: str):
        super().__init__(f"Provider endpoint '{endpoint_id}' not found")
        self.endpoint_id = endpoint_id


class ProviderProbeService:
    """Real adapter health probe + model discovery with durable persistence."""

    def __init__(
        self,
        adapter_factory: Any,
        repository: ProviderManagementRepositoryPort,
    ) -> None:
        self._adapter_factory = adapter_factory
        self._repository = repository

    async def test_connection(self, endpoint_id: str) -> ProviderProbeResult:
        """Probe one endpoint with a real adapter network call + discovery."""
        material = self._repository.get_probe_material(endpoint_id)
        if material is None:
            raise ProviderNotFoundError(endpoint_id)

        adapter = self._adapter_factory.create(material)
        started = time.perf_counter()
        try:
            health = await adapter.health()
        except ProviderFailure as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return self._finish_failure(
                endpoint_id=endpoint_id,
                vendor_id=material.vendor_id,
                latency_ms=latency_ms,
                error_code=exc.__class__.__name__,
                message=str(exc.message),
            )
        except Exception as exc:  # fail closed: never fabricate a healthy result
            latency_ms = (time.perf_counter() - started) * 1000.0
            return self._finish_failure(
                endpoint_id=endpoint_id,
                vendor_id=material.vendor_id,
                latency_ms=latency_ms,
                error_code=type(exc).__name__,
                message=str(exc),
            )

        if not health.healthy:
            return self._finish_failure(
                endpoint_id=endpoint_id,
                vendor_id=material.vendor_id,
                latency_ms=health.latency_ms,
                error_code=health.error_message or "unhealthy",
                message=health.error_message or "Provider endpoint is unhealthy",
            )

        # Real model discovery over the same adapter.
        try:
            discovered = await adapter.list_models()
        except ProviderFailure as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return self._finish_failure(
                endpoint_id=endpoint_id,
                vendor_id=material.vendor_id,
                latency_ms=latency_ms,
                error_code=exc.__class__.__name__,
                message=f"Health probe passed but model discovery failed: {exc.message}",
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return self._finish_failure(
                endpoint_id=endpoint_id,
                vendor_id=material.vendor_id,
                latency_ms=latency_ms,
                error_code=type(exc).__name__,
                message=f"Health probe passed but model discovery failed: {exc}",
            )

        latency_ms = (time.perf_counter() - started) * 1000.0
        bindings = self._repository.register_discovered_models(endpoint_id, discovered)
        result = ProviderProbeResult(
            endpoint_id=endpoint_id,
            reachable=True,
            latency_ms=latency_ms,
            auth_valid=True,
            message=(
                f"Successfully authenticated and reachable via endpoint "
                f"'{endpoint_id}' ({latency_ms:.1f}ms); "
                f"{len(discovered)} models discovered."
            ),
            discovered_models=[d.raw_model_id for d in discovered],
        )
        self._repository.record_probe_result(endpoint_id, result)
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.probe",
                vendor_id=material.vendor_id,
                endpoint_id=endpoint_id,
                reason=f"probe pass; {len(bindings)} bindings registered",
                metadata={"latency_ms": round(latency_ms, 1), "models": len(discovered)},
            )
        )
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.discovery",
                vendor_id=material.vendor_id,
                endpoint_id=endpoint_id,
                reason=f"{len(bindings)} model bindings registered",
                metadata={"models": len(discovered)},
            )
        )
        return result

    # ------------------------------------------------------------------ #
    def _finish_failure(
        self,
        *,
        endpoint_id: str,
        vendor_id: str,
        latency_ms: float,
        error_code: Optional[str],
        message: str,
    ) -> ProviderProbeResult:
        result = ProviderProbeResult(
            endpoint_id=endpoint_id,
            reachable=False,
            latency_ms=latency_ms,
            auth_valid=False,
            error_code=error_code,
            message=message,
        )
        self._repository.record_probe_result(endpoint_id, result)
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.probe",
                vendor_id=vendor_id,
                endpoint_id=endpoint_id,
                reason=f"probe fail: {error_code}",
                metadata={"latency_ms": round(latency_ms, 1), "error_code": error_code},
            )
        )
        return result


__all__ = ["ProviderNotFoundError", "ProviderProbeService"]
