"""Provider health probe, model sync, and model probe services (Phase 10 / P0.2).

``ProviderProbeService`` exposes THREE clearly separated operations — never an
implicit pipeline:

1. ``test_connection``  — ONE real network connectivity/auth handshake
                          (health). Persists endpoint status + health sample.
                          Performs NO model discovery and registers NOTHING.
2. ``sync_models``      — real catalog discovery (adapter ``list_models``) +
                          durable reconciliation (ADDED / UPDATED / UNCHANGED /
                          UNAVAILABLE). Pricing is persisted only when the
                          provider advertises it; otherwise UNKNOWN.
3. ``probe_model``      — one tiny REAL inference against a specific bound
                          model to verify endpoint+credential+model-id+protocol
                          end to end. Never used for quality benchmarking.

No operation fabricates reachability, latency, auth validity, or pricing.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional

from windagent_core.contracts.providers.provider_management import (
    ProviderAuditEvent,
    ProviderManagementRepositoryPort,
    ProviderProbeResult,
)
from windagent_providers.base.contracts import ProviderRequest
from windagent_providers.base.errors import ProviderFailure


class ProviderNotFoundError(Exception):
    """Raised when a probe targets an endpoint that does not exist."""

    def __init__(self, endpoint_id: str):
        super().__init__(f"Provider endpoint '{endpoint_id}' not found")
        self.endpoint_id = endpoint_id


@dataclass
class ModelSyncResult:
    """Outcome of one explicit Sync Models operation (P0.2.1/P0.2.4)."""

    endpoint_id: str
    vendor_id: str
    ok: bool
    added: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    unavailable: List[str] = field(default_factory=list)
    discovered: List[str] = field(default_factory=list)
    error_code: Optional[str] = None
    message: str = ""
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ModelProbeReceipt:
    """Receipt of one explicit Test Model operation (P0.2.5).

    Verifies endpoint + credential + model id + protocol with a tiny real
    inference. Deliberately carries NO quality signals (no tokens/s, no
    benchmark scores).
    """

    endpoint_id: str
    vendor_id: str
    canonical_model_id: str
    provider_model_id: str
    ok: bool
    latency_ms: float = 0.0
    finish_reason: Optional[str] = None
    error_code: Optional[str] = None
    message: str = ""
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProviderProbeService:
    """Real adapter probes with durable persistence, split by operation."""

    def __init__(
        self,
        adapter_factory: Any,
        repository: ProviderManagementRepositoryPort,
    ) -> None:
        self._adapter_factory = adapter_factory
        self._repository = repository

    # ------------------------------------------------------------------ #
    # 1) Test Connection — connectivity/auth ONLY (P0.2.1)
    # ------------------------------------------------------------------ #
    async def test_connection(self, endpoint_id: str) -> ProviderProbeResult:
        """One real health handshake; never discovers or mutates the catalog."""
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

        latency_ms = (time.perf_counter() - started) * 1000.0
        result = ProviderProbeResult(
            endpoint_id=endpoint_id,
            reachable=True,
            auth_valid=True,
            latency_ms=latency_ms,
            message=(
                f"Successfully authenticated and reachable via endpoint "
                f"'{endpoint_id}' ({latency_ms:.1f}ms). Run Sync Models to "
                "refresh the catalog."
            ),
            discovered_models=[],
        )
        self._repository.record_probe_result(endpoint_id, result)
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.probe",
                vendor_id=material.vendor_id,
                endpoint_id=endpoint_id,
                reason="connection test pass",
                metadata={"latency_ms": round(latency_ms, 1)},
            )
        )
        return result

    # ------------------------------------------------------------------ #
    # 2) Sync Models — discovery + reconciliation (P0.2.1/P0.2.2/P0.2.4)
    # ------------------------------------------------------------------ #
    async def sync_models(self, endpoint_id: str) -> ModelSyncResult:
        """Discover the live catalog once and durably reconcile bindings."""
        material = self._repository.get_probe_material(endpoint_id)
        if material is None:
            raise ProviderNotFoundError(endpoint_id)

        adapter = self._adapter_factory.create(material)
        try:
            discovered = await adapter.list_models()
        except ProviderFailure as exc:
            return self._sync_failure(
                material, error_code=exc.__class__.__name__, message=str(exc.message)
            )
        except Exception as exc:  # fail closed, never partially reconcile
            return self._sync_failure(
                material, error_code=type(exc).__name__, message=str(exc)
            )

        summary = self._repository.reconcile_discovered_models(endpoint_id, discovered)
        raw_ids = [d.raw_model_id for d in discovered]
        result = ModelSyncResult(
            endpoint_id=endpoint_id,
            vendor_id=material.vendor_id,
            ok=True,
            added=list(summary.get("added", [])),
            updated=list(summary.get("updated", [])),
            unchanged=list(summary.get("unchanged", [])),
            unavailable=list(summary.get("unavailable", [])),
            discovered=raw_ids,
            message=(
                f"{len(raw_ids)} model(s) discovered on '{endpoint_id}': "
                f"{len(summary.get('added', []))} added, "
                f"{len(summary.get('updated', []))} updated, "
                f"{len(summary.get('unchanged', []))} unchanged, "
                f"{len(summary.get('unavailable', []))} unavailable."
            ),
        )
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.discovery",
                vendor_id=material.vendor_id,
                endpoint_id=endpoint_id,
                reason=(
                    f"sync: {len(result.added)} added / {len(result.updated)} updated / "
                    f"{len(result.unchanged)} unchanged / {len(result.unavailable)} unavailable"
                ),
                metadata={
                    "added": len(result.added),
                    "updated": len(result.updated),
                    "unchanged": len(result.unchanged),
                    "unavailable": len(result.unavailable),
                    "models": len(raw_ids),
                },
            )
        )
        return result

    # ------------------------------------------------------------------ #
    # 3) Test Model — tiny real inference (P0.2.5)
    # ------------------------------------------------------------------ #
    async def probe_model(self, endpoint_id: str, canonical_model_id: str) -> ModelProbeReceipt:
        """Verify endpoint+credential+model-id+protocol with one small call."""
        material = self._repository.get_probe_material(endpoint_id)
        if material is None:
            raise ProviderNotFoundError(endpoint_id)

        provider_model_id = self._repository.resolve_provider_model_id(
            endpoint_id, canonical_model_id
        )
        base = dict(
            endpoint_id=endpoint_id,
            vendor_id=material.vendor_id,
            canonical_model_id=canonical_model_id,
            provider_model_id=provider_model_id or "",
        )
        if provider_model_id is None:
            return ModelProbeReceipt(
                ok=False,
                error_code="MODEL_NOT_BOUND",
                message=(
                    f"Canonical model '{canonical_model_id}' has no active "
                    f"binding on endpoint '{endpoint_id}'. Sync Models first."
                ),
                **base,
            )

        adapter = self._adapter_factory.create(material)
        request = ProviderRequest(
            messages=[{"role": "user", "content": "Reply with the single word: OK"}],
            temperature=0.0,
            max_output_tokens=8,
            request_id=f"model-probe-{uuid.uuid4().hex[:10]}",
            timeout_seconds=20.0,
        )
        started = time.perf_counter()
        try:
            response = await adapter.generate(request, provider_model_id)
        except ProviderFailure as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            receipt = ModelProbeReceipt(
                ok=False,
                latency_ms=round(latency_ms, 1),
                error_code=exc.__class__.__name__,
                message=f"Model probe failed: {exc.message}",
                **base,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            receipt = ModelProbeReceipt(
                ok=False,
                latency_ms=round(latency_ms, 1),
                error_code=type(exc).__name__,
                message=f"Model probe failed: {exc}",
                **base,
            )
        else:
            latency_ms = (time.perf_counter() - started) * 1000.0
            receipt = ModelProbeReceipt(
                ok=True,
                latency_ms=round(latency_ms, 1),
                finish_reason=response.finish_reason,
                message=(
                    f"Inference succeeded on '{provider_model_id}' via "
                    f"'{endpoint_id}' ({latency_ms:.1f}ms)."
                ),
                **base,
            )

        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.model_probe",
                vendor_id=material.vendor_id,
                endpoint_id=endpoint_id,
                canonical_model_id=canonical_model_id,
                reason=(
                    "model probe pass"
                    if receipt.ok
                    else f"model probe fail: {receipt.error_code}"
                ),
                metadata={
                    "provider_model_id": provider_model_id,
                    "ok": receipt.ok,
                    "latency_ms": receipt.latency_ms,
                },
            )
        )
        return receipt

    # ------------------------------------------------------------------ #
    def _sync_failure(
        self, material: Any, *, error_code: str, message: str
    ) -> ModelSyncResult:
        result = ModelSyncResult(
            endpoint_id=material.endpoint_id,
            vendor_id=material.vendor_id,
            ok=False,
            error_code=error_code,
            message=f"Model sync failed: {message}",
        )
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.discovery",
                vendor_id=material.vendor_id,
                endpoint_id=material.endpoint_id,
                reason=f"sync fail: {error_code}",
                metadata={"error_code": error_code},
            )
        )
        return result

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


__all__ = [
    "ModelProbeReceipt",
    "ModelSyncResult",
    "ProviderNotFoundError",
    "ProviderProbeService",
]
