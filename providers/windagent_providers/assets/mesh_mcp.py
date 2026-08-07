"""
MeshMcpAdapter — Mesh MCP client integration (VP3D Phase 5).

Same fail-closed surface as the Mesh API adapter: without an injected MCP
transport the adapter is ``REQUIRES_CONFIG`` and every call is a typed
rejection. The MCP client object is never imported here — it is referenced by
a redacted reference (``client_ref``) resolved by the injected transport.
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
class MeshMcpConfig:
    """Provider-neutral Mesh MCP configuration.

    ``client_ref`` is a secret/connection REFERENCE (e.g.
    ``env:WINDAGENT_MESH_MCP_CLIENT``) — never an embedded credential or
    client object.
    """

    client_ref: str = ""
    timeout_seconds: float = 30.0

    def to_payload(self) -> dict:
        payload = {
            "client_ref": self.client_ref,
            "timeout_seconds": self.timeout_seconds,
        }
        assert_no_credentials(payload, context="MeshMcpConfig")
        return payload


class MeshMcpTransportPort(Protocol):
    """Injected MCP transport (never part of the core surface)."""

    async def fetch_candidates(
        self,
        request: AssetResolutionRequest,
        config: MeshMcpConfig,
    ) -> List[AssetCandidate]:
        ...

    async def acquire_candidate(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
        config: MeshMcpConfig,
    ) -> AcquiredAsset:
        ...


class MeshMcpAdapter(AssetAdapter):
    """Adapter over a Mesh MCP backend (typed rejection when not configured)."""

    adapter_id = "mesh.mcp.v1"
    adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        config: Optional[MeshMcpConfig] = None,
        transport: Optional[MeshMcpTransportPort] = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def capability(self) -> AssetProviderCapability:
        ready = self._config is not None and self._transport is not None
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.MESH_MCP,
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
                AssetKind.ANIMATION_CLIP,
            ],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=8192,
            license_constraints=[
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.ANY_PERMISSIVE,
                LicenseConstraint.ATTRIBUTION_REQUIRED,
            ],
            max_polygons=5_000_000,
            max_file_bytes=1024 * 1024 * 1024,
            description="Mesh MCP backend catalog (requires configured transport).",
        )

    def _require_ready(self) -> MeshMcpConfig:
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


__all__ = ["MeshMcpConfig", "MeshMcpAdapter", "MeshMcpTransportPort"]
