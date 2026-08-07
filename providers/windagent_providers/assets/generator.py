"""
FutureGeneratorAdapter — future 3D generation APIs (VP3D Phase 5).

The generator slot exists so the gateway surface is future-proof. In Phase 5
no generation backend ships: without an injected generator backend the adapter
is ``REQUIRES_CONFIG`` (typed rejection before any call) and any direct
invocation raises ``GenerationNotEnabledError``. Fake adapters in ``fake.py``
provide the deterministic CI semantics.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from windagent_core.domain.video_production.asset_resolution import (
    AdapterKind,
    AssetCandidate,
    AssetKind,
    AssetProviderCapability,
    AssetResolutionRequest,
    AssetStyle,
    GenerationNotEnabledError,
    LicenseConstraint,
    ProviderAvailability,
)

from windagent_providers.assets.adapter import AcquiredAsset, AssetAdapter


class GeneratorBackendPort(Protocol):
    """Injected 3D generation backend (never part of the core surface)."""

    async def generate_candidates(
        self,
        request: AssetResolutionRequest,
    ) -> List[AssetCandidate]:
        ...

    async def acquire_generated(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        ...


class FutureGeneratorAdapter(AssetAdapter):
    """Adapter over future 3D generation APIs (fail closed in Phase 5)."""

    adapter_id = "generator.future"
    adapter_version = "1.0.0"

    def __init__(self, *, backend: Optional[GeneratorBackendPort] = None) -> None:
        self._backend = backend

    def capability(self) -> AssetProviderCapability:
        ready = self._backend is not None
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.GENERATOR,
            adapter_version=self.adapter_version,
            availability=(
                ProviderAvailability.READY if ready else ProviderAvailability.REQUIRES_CONFIG
            ),
            supported_kinds=[
                AssetKind.CHARACTER,
                AssetKind.PROP,
                AssetKind.ENVIRONMENT,
                AssetKind.VEHICLE,
                AssetKind.CREATURE,
                AssetKind.TEXTURE,
                AssetKind.MATERIAL,
            ],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=4096,
            license_constraints=[
                LicenseConstraint.ANY_PERMISSIVE,
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.NO_ATTRIBUTION,
            ],
            max_polygons=3_000_000,
            max_file_bytes=512 * 1024 * 1024,
            supports_generation=True,
            description="Future 3D generation APIs (generation not enabled in Phase 5).",
        )

    def _require_backend(self):
        if self._backend is None:
            raise GenerationNotEnabledError(
                f"Provider {self.adapter_id}: generation is not enabled (no backend "
                "injected).",
                details={"provider_id": self.adapter_id},
            )
        return self._backend

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        backend = self._require_backend()
        candidates = await backend.generate_candidates(request)
        return candidates[: request.max_candidates]

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        backend = self._require_backend()
        return await backend.acquire_generated(candidate, request)


__all__ = ["FutureGeneratorAdapter", "GeneratorBackendPort"]
