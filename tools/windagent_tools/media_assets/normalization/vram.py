"""
Pre-preview VRAM estimation (VP3D Phase 7, Stage C item 5).

Geometry and texture footprints are estimated BEFORE any preview render. An
asset that exceeds the hard limit is ``BLOCKED`` — it is never blindly
rendered (no hidden OOM mid-render).
"""

from __future__ import annotations

from windagent_core.domain.video_production.asset_normalization.enums import VramDecision
from windagent_core.domain.video_production.asset_normalization.models import (
    NormalizationConfig,
    TextureInfo,
    VramEstimate,
)

from windagent_tools.media_assets.normalization.snapshot import MeshSnapshot

# GPU memory per vertex: position (3x4) + normal (3x4) + UV (2x4) + tangent (4x4).
BYTES_PER_VERTEX = 56
# Index buffer: 4 bytes per triangle corner.
BYTES_PER_TRIANGLE_INDEX = 12


class VramEstimator:
    """Computes the geometry/texture VRAM budget before preview."""

    def estimate(
        self,
        snapshot: MeshSnapshot,
        textures: list[TextureInfo],
        config: NormalizationConfig,
    ) -> VramEstimate:
        geometry_bytes = (
            snapshot.vertex_count * BYTES_PER_VERTEX
            + snapshot.triangle_count * BYTES_PER_TRIANGLE_INDEX
        )
        texture_bytes = sum(t.bytes_estimate for t in textures)
        total = geometry_bytes + texture_bytes
        within = total <= config.max_vram_bytes
        detail = (
            f"geometry {geometry_bytes} B + textures {texture_bytes} B = {total} B "
            f"(hard limit {config.max_vram_bytes} B)"
        )
        return VramEstimate(
            geometry_bytes=geometry_bytes,
            texture_bytes=texture_bytes,
            total_bytes=total,
            hard_limit_bytes=config.max_vram_bytes,
            decision=VramDecision.WITHIN_BUDGET if within else VramDecision.BLOCKED,
            detail=detail,
        )


__all__ = ["VramEstimator", "BYTES_PER_VERTEX", "BYTES_PER_TRIANGLE_INDEX"]
