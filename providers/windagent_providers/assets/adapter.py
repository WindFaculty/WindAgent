"""
Adapter contract for the Universal Asset Gateway (VP3D Phase 5).

Every provider (local library, Internet, Mesh API, Mesh MCP, future generator)
implements ``AssetAdapter``. Adapters:

- declare a stable ``adapter_id`` + ``adapter_version`` — the idempotency scope;
- expose an immutable ``AssetProviderCapability`` for pre-call matching;
- implement ``discover`` (candidates, DISCOVERED only) and ``acquire``
  (content-addressed ``ReferenceAsset`` + provenance);
- NEVER accept or emit credentials — secrets are injected as references and
  redacted by the gateway before any receipt is built.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, List

from windagent_core.domain.video_production.asset import (
    AssetAcquisitionRecord,
    ReferenceAsset,
)
from windagent_core.domain.video_production.asset_resolution import (
    AssetCandidate,
    AssetProviderCapability,
    AssetResolutionRequest,
    AssetTrustEvidence,
)


@dataclass(frozen=True)
class AcquiredAsset:
    """Outcome of a successful adapter-level acquire.

    ``trust`` carries the evidence the gateway's trust gate evaluates
    (Phase 6): checksum verification, commercial-use right, trademark /
    attribution flags and (optional) content-scan evidence. Every flag is
    fail-closed — False unless the adapter can actually prove it.
    """

    asset: ReferenceAsset
    acquisition: AssetAcquisitionRecord
    trust: AssetTrustEvidence = field(default_factory=AssetTrustEvidence)


class AssetAdapter(ABC):
    """Provider-neutral adapter surface for one asset source."""

    adapter_id: ClassVar[str] = ""
    adapter_version: ClassVar[str] = "0.0.0"

    @abstractmethod
    def capability(self) -> AssetProviderCapability:
        """Declared capability used for pre-call matching."""

    @abstractmethod
    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        """Return DISCOVERED candidates; raise typed errors on failure."""

    @abstractmethod
    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        """Acquire a candidate into a content-addressed asset with provenance."""


__all__ = ["AcquiredAsset", "AssetAdapter"]
