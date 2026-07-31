"""
MediaGenerationProviderPort — canonical provider abstraction.

Supports image generation, video generation, video extension, job inspection,
and result download. The contract deliberately contains NO selectors,
cookies, Flow project URLs, or browser session objects: those live in the
provider adapter layer only (road_map.md Phase 12–15).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.generation_job import (
    GenerationCandidate,
    GenerationRequest,
)
from windagent_core.domain.video_production.ids import ReferenceAssetId


@runtime_checkable
class MediaGenerationProviderPort(Protocol):
    """Port for a media generation provider (Flow, Veo API, Kling, etc.)."""

    async def generate_image(self, request: GenerationRequest) -> GenerationCandidate:
        """Generate an image from a request."""
        ...

    async def generate_video(self, request: GenerationRequest) -> GenerationCandidate:
        """Generate a video clip from a request."""
        ...

    async def extend_video(
        self,
        request: GenerationRequest,
        source_asset_id: ReferenceAssetId,
        extension_seconds: float,
    ) -> GenerationCandidate:
        """Extend an existing video clip."""
        ...

    async def inspect_job(self, request: GenerationRequest) -> GenerationCandidate:
        """Inspect the current status of a submitted generation job."""
        ...

    async def download_result(self, request: GenerationRequest) -> ReferenceAsset:
        """Download a completed result as a content-addressed asset."""
        ...


__all__ = ["MediaGenerationProviderPort"]
