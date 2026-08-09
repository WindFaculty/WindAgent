"""
Multi-Scene Episode orchestration (VP3D Phase 26, Stage M).

Production orchestrator over the multi-scene episode pipeline with asset
reuse, parallel audio/asset branches, chunk-granularity kill/resume,
targeted invalidation and a fail-closed verdict.
"""

from windagent_intelligence.video.episode.cache import (
    EpisodeAssetCache,
    asset_expected_hash,
)
from windagent_intelligence.video.episode.checks import (
    episode_identity_checker,
    episode_verification_checker,
)
from windagent_intelligence.video.episode.orchestrator import (
    EpisodeAssetGeneratorLeg,
    EpisodeAudioSynthesisLeg,
    EpisodeFfmpegLeg,
    EpisodeOrchestrator,
    EpisodeRenderLeg,
    EpisodeReviewRepairLeg,
)

__all__ = [
    "EpisodeOrchestrator",
    "EpisodeAssetCache",
    "asset_expected_hash",
    "episode_identity_checker",
    "episode_verification_checker",
    "EpisodeRenderLeg",
    "EpisodeReviewRepairLeg",
    "EpisodeFfmpegLeg",
    "EpisodeAudioSynthesisLeg",
    "EpisodeAssetGeneratorLeg",
]
