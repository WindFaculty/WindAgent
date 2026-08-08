"""
AssetNormalizerPort — asset normalization contract (VP3D Phase 7, Stage C).

The Scene Compiler consumes ONLY normalized assets: every acquired asset must
pass through this port before it can be referenced by a shot. Rules:

- The port receives a trusted, content-addressed ``ReferenceAsset`` and
  returns a typed ``NormalizedAsset`` (READY/BLOCKED/FAILED) — never a raw
  file handle and never an engine SDK object.
- An over-budget asset is ``BLOCKED`` BEFORE any preview render (fail closed).
- The returned bundle is immutable and content-addressed.
- No ``bpy``, Unreal, provider SDK, or transport may appear on this surface.
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from windagent_core.domain.video_production.asset_normalization.models import (
    NormalizationRequest,
    NormalizedAsset,
)
from windagent_core.domain.video_production.asset_normalization.enums import AssetFormat


@runtime_checkable
class AssetNormalizerPort(Protocol):
    """Port every 3D asset must pass through before Scene Compiler use."""

    async def normalize(self, request: NormalizationRequest) -> NormalizedAsset:
        """Normalize one trusted asset into an immutable normalized bundle.

        Outcome statuses:
        - ``READY`` — full pipeline completed, bundle published;
        - ``BLOCKED`` — a hard limit (security/polygon/VRAM) stopped the
          pipeline BEFORE preview render or publish;
        - ``FAILED`` — a stage error occurred; nothing was published.
        """
        ...

    def formats_supported(self) -> List[AssetFormat]:
        """Formats this normalizer can ingest without an external engine."""
        ...


__all__ = ["AssetNormalizerPort"]
