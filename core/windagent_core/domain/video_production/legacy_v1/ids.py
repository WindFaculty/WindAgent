"""
Legacy compatibility — `FlowGenerationSpecificationId`.

Retired from `windagent_core.domain.video_production.ids` during VP3D Stage A.
Kept ONLY for the bounded legacy reader / migration window.
"""

from __future__ import annotations

from windagent_core.domain.types import OpaqueId


class FlowGenerationSpecificationId(OpaqueId):
    """Identifier for a legacy FlowGenerationSpecification (retired)."""


__all__ = ["FlowGenerationSpecificationId"]
