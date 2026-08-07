"""
MeshApiAdapter — external Mesh API integration (VP3D Phase 5).

Phase 5 defines the adapter surface and the fail-closed behavior: without an
injected transport the adapter reports ``REQUIRES_CONFIG`` and capability
matching rejects every requirement (typed rejection BEFORE any call). No
credential is ever stored in the adapter — only a redacted secret REFERENCE
(``api_key_ref``) that the transport resolves at call time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from windagent_core.domain.video_production.asset_resolution import (
    AdapterKind,
    AssetCandidate,
    AssetKind,
    AssetProviderCapability,
    AssetResolutionRequest,
    AssetStyle,
    LicenseConstraint,
    ProviderAvailability,
    ProviderUnavailableError,
)

from windagent_providers.assets.adapter import AcquiredAsset, AssetAdapter
from windagent_providers.assets.redaction import assert_no_credentials


@dataclass(frozen=True)
class MeshApiConfig:
    """Provider-neutral Mesh API configuration.

    ``api_key_ref`` is a secret REFERENCE (e.g. ``env:WINDAGENT_MESH_API_KEY``)
    — never the raw key. The injected transport resolves it at call time.
    """

    base_url: str = ""
    api_key_ref: str = ""
    timeout_seconds: float = 30.0

    def to_payload(self) -> dict:
        payload = {
            "base_url": self.base_url,
            "api_key_ref": self.api_key_ref,
            "timeout_seconds": self.timeout_seconds,
        }
        # Fail closed: the payload must contain only a redacted reference.
        assert_no_credentials(payload, context="MeshApiConfig")
        return payload


class MeshTransportPort(Protocol):
    """Injected Mesh API transport (never part of the core surface)."""

    async def fetch_candidates(
        self,
        request: AssetResolutionRequest,
        config: MeshApiConfig,
    ) -> List[AssetCandidate]:
        ...

    async def acquire_candidate(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
        config: MeshApiConfig,
    ) -> AcquiredAsset:
        ...


class MeshApiAdapter(AssetAdapter):
    """Adapter over the Mesh API (typed rejection when not configured)."""

    adapter_id = "mesh.api.v1"
    adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        config: Optional[MeshApiConfig] = None,
        transport: Optional[MeshTransportPort] = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def capability(self) -> AssetProviderCapability:
        ready = self._config is not None and self._transport is not None
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.MESH_API,
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
            ],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=8192,
            license_constraints=[
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.ANY_PERMISSIVE,
            ],
            max_polygons=5_000_000,
            max_file_bytes=1024 * 1024 * 1024,
            description="External Mesh API catalog (requires configured transport).",
        )

    def _require_ready(self) -> MeshApiConfig:
        if self._config is None or self._transport is None:
            raise ProviderUnavailableError(
                f"Provider {self.adapter_id} is not configured (no transport).",
                details={"provider_id": self.adapter_id},
            )
        return self._config

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        config = self._require_ready()
        assert self._transport is not None
        candidates = await self._transport.fetch_candidates(request, config)
        return candidates[: request.max_candidates]

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        config = self._require_ready()
        assert self._transport is not None
        return await self._transport.acquire_candidate(candidate, request, config)


__all__ = ["MeshApiConfig", "MeshApiAdapter", "MeshTransportPort"]
