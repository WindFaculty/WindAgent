"""
Golden Scene End-to-End orchestration (VP3D Phase 25, Stage M).

Production orchestrator over the golden scene node DAG with checkpointed
resume (cancel/restart never duplicates), identity/continuity gates, real
technical verification and a fail-closed verdict.
"""

from windagent_intelligence.video.golden_scene.checks import (
    default_identity_checker,
    default_verification_checker,
)
from windagent_intelligence.video.golden_scene.orchestrator import (
    GoldenSceneFfmpegLeg,
    GoldenSceneOrchestrator,
    GoldenSceneRenderLeg,
    GoldenSceneReviewRepairLeg,
    GoldenSceneStepRunner,
)
from windagent_intelligence.video.golden_scene.steps import (
    AnimationAudioStep,
    AssetsStep,
    FacialStep,
    FinalStep,
    IrStep,
    SceneStep,
    ScriptStep,
    build_default_steps,
)

__all__ = [
    "GoldenSceneOrchestrator",
    "GoldenSceneRenderLeg",
    "GoldenSceneReviewRepairLeg",
    "GoldenSceneFfmpegLeg",
    "GoldenSceneStepRunner",
    "default_identity_checker",
    "default_verification_checker",
    "build_default_steps",
    "ScriptStep",
    "IrStep",
    "AssetsStep",
    "SceneStep",
    "AnimationAudioStep",
    "FacialStep",
    "FinalStep",
]
