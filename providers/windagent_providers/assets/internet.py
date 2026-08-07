"""
InternetAssetAdapter — Internet asset acquisition (VP3D Phase 5).

The adapter is a SEAM: the actual SSRF-safe download / MIME sniffing /
content-addressed storage stays in ``windagent_tools.media_assets`` (shared
download & validation) and is injected here through structural ports at the
composition root. Without injected backends the adapter is ``REQUIRES_CONFIG``
and every call fails closed with ``ProviderUnavailableError``.

Backlog item 4: discover is separate from acquire — search results are
DISCOVERED candidates only and never usable assets.
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
    LicenseConstraint,
    ProviderAvailability,
    ProviderUnavailableError,
)

from windagent_providers.assets.adapter import AcquiredAsset, AssetAdapter


class InternetSearchPort(Protocol):
    """Injected search backend (tools-side AssetSearchService wraps this)."""

    async def search(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        """Return DISCOVERED candidates; never approve or fetch content."""
        ...


class InternetAcquisitionPort(Protocol):
    """Injected acquisition backend (tools-side download+validate+store)."""

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        """Download, validate and content-address the candidate; return the
        acquired asset with provenance."""
        ...


class InternetAssetAdapter(AssetAdapter):
    """Adapter over injected search/acquisition backends (never credentials)."""

    adapter_id = "internet.search"
    adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        search: Optional[InternetSearchPort] = None,
        acquisition: Optional[InternetAcquisitionPort] = None,
    ) -> None:
        self._search = search
        self._acquisition = acquisition

    def capability(self) -> AssetProviderCapability:
        ready = self._search is not None and self._acquisition is not None
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.INTERNET,
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
                LicenseConstraint.ANY_PERMISSIVE,
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.ATTRIBUTION_REQUIRED,
                LicenseConstraint.NO_ATTRIBUTION,
            ],
            max_polygons=None,
            max_file_bytes=None,
            description="Internet search + acquisition through injected SSRF-safe "
            "download/validation backends (media_assets).",
        )

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        if self._search is None:
            raise ProviderUnavailableError(
                f"Provider {self.adapter_id} has no search backend configured (fail closed).",
                details={"provider_id": self.adapter_id},
            )
        candidates = await self._search.search(request)
        return candidates[: request.max_candidates]

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        if self._acquisition is None:
            raise ProviderUnavailableError(
                f"Provider {self.adapter_id} has no acquisition backend configured "
                "(fail closed).",
                details={"provider_id": self.adapter_id},
            )
        return await self._acquisition.acquire(candidate, request)


__all__ = ["InternetAssetAdapter", "InternetSearchPort", "InternetAcquisitionPort"]
