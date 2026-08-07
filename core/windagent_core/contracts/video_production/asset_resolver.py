"""
AssetResolverPort — Universal Asset Gateway contract (VP3D Phase 5, Stage C).

The gateway is the ONLY acquisition channel the Director/Scene Compiler may use
for 3D assets. Rules:

- ``discover`` returns candidates (DISCOVERED state) — search results are never
  usable assets; ``acquire`` promotes one candidate to a content-addressed
  ``ReferenceAsset`` with provenance.
- Every provider that cannot serve a requirement returns a TYPED rejection —
  never a partial or silent result.
- The port surface is provider-neutral: no Mesh API/MCP SDK object, no network
  transport, no credential can appear here.
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from windagent_core.domain.video_production.asset_resolution.models import (
    AssetCandidate,
    AssetProviderCapability,
    AssetResolutionRequest,
    AssetResolutionResult,
)


@runtime_checkable
class AssetResolverPort(Protocol):
    """Port for the Universal Asset Gateway (local/Internet/Mesh/generator)."""

    async def discover(self, request: AssetResolutionRequest) -> AssetResolutionResult:
        """Search/scan capable providers for candidates.

        Returns status ``DISCOVERED`` with candidates, ``NOT_FOUND`` when no
        adapter produced a match, or a typed rejection status (``REJECTED``,
        ``TIMEOUT``, ``CANCELLED``). Candidates are NEVER approved assets.
        """
        ...

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AssetResolutionResult:
        """Acquire a discovered candidate into a content-addressed asset.

        On success the result carries ``acquired`` (``ReferenceAsset``) and an
        ``AssetAcquisitionRecord`` provenance. License state is carried through
        and never auto-approved.
        """
        ...

    def capabilities(self) -> List[AssetProviderCapability]:
        """Declared capabilities of every registered adapter.

        Callers use this for capability matching BEFORE any provider call.
        """
        ...


__all__ = ["AssetResolverPort"]
