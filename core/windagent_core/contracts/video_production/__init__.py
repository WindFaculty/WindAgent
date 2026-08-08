"""
WindAgent Video Production contracts (Phase 3 canonical ports).

Ports are implementation-independent; no browser/provider implementation
details (selectors, cookies, project URLs, or session objects) may appear.
"""

from windagent_core.contracts.video_production.preproduction import PreproductionPort
from windagent_core.contracts.video_production.direction import VideoDirectionPort
from windagent_core.contracts.video_production.media_generation import MediaGenerationProviderPort
from windagent_core.contracts.video_production.asset_storage import AssetStoragePort
from windagent_core.contracts.video_production.quality_review import QualityReviewPort
from windagent_core.contracts.video_production.production_engine import ProductionEnginePort
from windagent_core.contracts.video_production.asset_resolver import (
    AssetResolverPort,
    AssetTrustPort,
)
from windagent_core.contracts.video_production.asset_normalizer import AssetNormalizerPort
from windagent_core.contracts.video_production.video_inspection import (
    VideoInspection,
    VideoInspectionError,
    VideoInspectionPolicy,
    VideoInspectorPort,
    VideoProbeUnavailableError,
)
from windagent_core.contracts.video_production.tts_provider import (
    TtsProviderCapability,
    TtsProviderPort,
    TtsSynthesisHandle,
)
from windagent_core.contracts.video_production.forced_alignment import (
    AlignmentResultHandle,
    ForcedAlignmentPort,
)
from windagent_core.contracts.video_production.facial_animation import (
    FacialAnimationCompilerPort,
)

__all__ = [
    "PreproductionPort",
    "VideoDirectionPort",
    "MediaGenerationProviderPort",
    "AssetStoragePort",
    "QualityReviewPort",
    "ProductionEnginePort",
    "AssetResolverPort",
    "AssetTrustPort",
    "AssetNormalizerPort",
    "VideoInspection",
    "VideoInspectionError",
    "VideoInspectionPolicy",
    "VideoInspectorPort",
    "VideoProbeUnavailableError",
    "TtsProviderPort",
    "TtsProviderCapability",
    "TtsSynthesisHandle",
    "ForcedAlignmentPort",
    "AlignmentResultHandle",
    "FacialAnimationCompilerPort",
]

