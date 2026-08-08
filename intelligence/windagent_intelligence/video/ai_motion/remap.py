"""
Skeleton remap service (VP3D Phase 17, stage_h §5 pipeline step 2).

Remaps the artifact's claimed skeleton onto the target skeleton's semantic
bone roles. Fail-closed: any required semantic bone the target does not
provide lands in `missing_bones` and the adapter refuses to continue (no
silent pose drop — stage_d §5). The mapped bones are exactly the semantic
roles both sides agree on, so the retarget step (Phase 15 RetargetService)
always has a complete, typed bone set.
"""

from __future__ import annotations

from typing import List, Optional

from windagent_core.domain.video_production.ai_motion import (
    RawMotionArtifact,
    SkeletonRemapReceipt,
)
from windagent_core.domain.video_production.enums import SemanticBone
from windagent_core.domain.video_production.ids import (
    SkeletonProfileId,
    SkeletonRemapReceiptId,
)
from windagent_intelligence.video.ids import StableIdFactory

# Semantic roles the production pipeline requires on a humanoid target.
REQUIRED_TARGET_BONES: List[SemanticBone] = [
    SemanticBone.ROOT,
    SemanticBone.PELVIS,
    SemanticBone.SPINE,
    SemanticBone.CHEST,
    SemanticBone.NECK,
    SemanticBone.HEAD,
    SemanticBone.SHOULDER_L,
    SemanticBone.SHOULDER_R,
    SemanticBone.ARM_UPPER_L,
    SemanticBone.ARM_UPPER_R,
    SemanticBone.ARM_LOWER_L,
    SemanticBone.ARM_LOWER_R,
    SemanticBone.HAND_L,
    SemanticBone.HAND_R,
    SemanticBone.THIGH_L,
    SemanticBone.THIGH_R,
    SemanticBone.SHIN_L,
    SemanticBone.SHIN_R,
    SemanticBone.FOOT_L,
    SemanticBone.FOOT_R,
]


class SkeletonRemapService:
    """Deterministic skeleton remap for raw AI motion artifacts."""

    def __init__(self, id_factory: Optional[StableIdFactory] = None) -> None:
        self.id_factory = id_factory or StableIdFactory()

    def remap(
        self,
        *,
        artifact: RawMotionArtifact,
        target_skeleton: SkeletonProfileId,
        target_bones: Optional[List[SemanticBone]] = None,
    ) -> SkeletonRemapReceipt:
        """Remap the artifact's claimed skeleton onto the target.

        `claimed_bones` comes from the artifact's motion metrics (the
        provider's own bone list). Required target bones not claimed by the
        provider are reported as missing and block the pipeline.
        """
        claimed = artifact.motion_metrics.get("claimed_bones", [])
        required = list(target_bones) if target_bones else REQUIRED_TARGET_BONES
        claimed_set = {str(b) for b in claimed}
        mapped = [b for b in required if b.value in claimed_set]
        missing = [b for b in required if b.value not in claimed_set]
        return SkeletonRemapReceipt(
            receipt_id=SkeletonRemapReceiptId(
                self.id_factory.skeleton_remap_receipt_id(artifact.artifact_id)),
            artifact_id=artifact.artifact_id,
            source_skeleton=artifact.claimed_skeleton_profile_id,
            target_skeleton=target_skeleton,
            mapped_bones=mapped,
            missing_bones=missing,
            ok=not missing,
        )


__all__ = ["REQUIRED_TARGET_BONES", "SkeletonRemapService"]
