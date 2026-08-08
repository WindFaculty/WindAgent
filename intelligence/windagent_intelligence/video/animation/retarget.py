"""
Clip retarget service (VP3D Phase 15, stage_h §3 backlog 4).

Normalizes a library/mocap clip onto a Stage D target skeleton: semantic
bone mapping, fps resample and root-motion/unit normalization. Fail-closed:

- target skeleton missing a required semantic bone -> `ClipRetargetError`
  (no silent pose drop, stage_d §5);
- clip fps != target fps and the clip forbids resampling (locked contact
  timing) -> `ClipRetargetError` (FPS_MISMATCH).

Root displacement is invariant under retarget: `root_motion_meters` is
preserved and `root_motion_mps` is normalized to the target fps so the
validator's ROOT_DRIFT check has a single source of truth.
"""

from __future__ import annotations

from typing import List, Optional

from windagent_core.domain.video_production.animation import RetargetReceipt
from windagent_core.domain.video_production.enums import SemanticBone
from windagent_core.domain.video_production.errors import ClipRetargetError
from windagent_core.domain.video_production.ids import (
    AnimationClipId,
    RetargetProfileId,
    RetargetReceiptId,
)
from windagent_intelligence.video.ids import StableIdFactory


class RetargetService:
    """Builds a deterministic retarget receipt for one clip (backlog 4)."""

    def __init__(self, id_factory: Optional[StableIdFactory] = None) -> None:
        self.id_factory = id_factory or StableIdFactory()

    def build_receipt(
        self,
        *,
        clip,
        target_fps: int,
        target_bones: List[SemanticBone],
        retarget_profile_id: RetargetProfileId = "",
        retarget_profile_hash: str = "",
    ) -> RetargetReceipt:
        missing = [b for b in clip.required_bones if b not in target_bones]
        if missing:
            raise ClipRetargetError(
                "target skeleton misses required semantic bones",
                details={
                    "clip_id": str(clip.clip_id),
                    "action": clip.action.value,
                    "missing_bones": [b.value for b in missing],
                    "target_bone_count": len(target_bones),
                })

        if clip.fps != target_fps and not clip.resamplable:
            raise ClipRetargetError(
                "clip fps cannot be resampled to the target fps",
                details={
                    "clip_id": str(clip.clip_id),
                    "source_fps": clip.fps,
                    "target_fps": target_fps,
                    "kind": "FPS_MISMATCH",
                })

        resample_ratio = target_fps / clip.fps
        root_mps = clip.root_motion_meters / clip.duration_seconds
        return RetargetReceipt(
            receipt_id=RetargetReceiptId(
                self.id_factory.retarget_receipt_id(clip.clip_id)),
            clip_id=AnimationClipId(str(clip.clip_id)),
            source_fps=clip.fps,
            target_fps=target_fps,
            resample_ratio=resample_ratio,
            root_motion_meters=clip.root_motion_meters,
            root_motion_mps=root_mps,
            units_normalized=True,
            semantic_bones_mapped=list(clip.required_bones),
            retarget_profile_id=(
                RetargetProfileId(str(retarget_profile_id))
                if str(retarget_profile_id) else None),
            retarget_profile_hash=retarget_profile_hash,
        )


__all__ = ["RetargetService"]
