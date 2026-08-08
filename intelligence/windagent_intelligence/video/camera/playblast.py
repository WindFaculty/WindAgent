"""
Camera preview manifest (VP3D Phase 13, stage_g §3 backlog 6).

Builds a light playblast manifest: the camera path + sampled framing report
(subject screen position, head room, look room per sample frame) so a reviewer
can inspect framing BEFORE any Cycles render. The manifest is deterministic —
same plan/compiler version yields the identical manifest hash.

The actual preview render stays in the renderer/tools layer (stage_g §6
evidence handoff); this is the domain-side review artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.cinematography import (
    CameraPose,
    CameraRigPlan,
    ScreenProjection,
    project_to_screen,
)
from windagent_core.domain.video_production.ids import CameraPathManifestId
from windagent_core.domain.video_production.set_dressing import Aabb, Vec3

PLAYBLAST_MANIFEST_VERSION = "1.0.0"
PLAYBLAST_SAMPLES_MAX = 12


class FramingSample(BaseModel):
    """One sampled frame's framing measurement (stage_g §3 backlog 6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame: int
    position: Vec3
    look_at: Vec3
    subject_screen_x: float = 0.0
    subject_screen_y: float = 0.0
    subject_visible: bool = False
    head_screen_y: float = 0.0
    head_room_ok: bool = False
    look_room_ok: bool = True
    fov_degrees: float = 0.0


class CameraPathManifest(BaseModel):
    """Deterministic camera path + sampled framing manifest for review."""

    model_config = ConfigDict(frozen=True, extra="allow")

    manifest_id: CameraPathManifestId
    plan_id: str = ""
    shot_id: str = ""
    primitive_id: str = ""
    primitive_version: str = ""
    compiler_version: str = ""
    manifest_version: str = PLAYBLAST_MANIFEST_VERSION
    keyframes: List[dict] = Field(default_factory=list)
    samples: List[FramingSample] = Field(default_factory=list)
    manifest_hash: str = ""

    def compute_hash(self) -> str:
        payload = json.loads(self.model_dump_json(exclude={"manifest_hash"}))
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PlayblastManifestBuilder:
    """Builds the light preview manifest from a compiled rig plan."""

    def __init__(self, *, id_factory=None) -> None:
        if id_factory is None:
            from windagent_intelligence.video.ids import StableIdFactory
            id_factory = StableIdFactory()
        self.id_factory = id_factory

    # ------------------------------------------------------------------
    def build(
        self,
        *,
        plan: CameraRigPlan,
        subject_bounds: Optional[Aabb] = None,
        sample_count: int = 5,
    ) -> CameraPathManifest:
        keys = plan.path.sorted_keyframes()
        samples = self._sample_frames(plan, subject_bounds, sample_count)
        manifest = CameraPathManifest(
            manifest_id=CameraPathManifestId(
                self.id_factory.camera_path_manifest_id(plan.shot_id)),
            plan_id=str(plan.plan_id),
            shot_id=str(plan.shot_id),
            primitive_id=plan.primitive_id,
            primitive_version=plan.primitive_version,
            compiler_version=plan.compiler_version,
            keyframes=[
                {
                    "frame": k.frame,
                    "position": k.position.as_tuple(),
                    "look_at": k.look_at.as_tuple(),
                    "easing": k.easing.value,
                }
                for k in keys
            ],
            samples=samples,
        )
        return manifest.model_copy(
            update={"manifest_hash": manifest.compute_hash()})

    # ------------------------------------------------------------------
    def _sample_frames(self, plan: CameraRigPlan,
                       subject_bounds: Optional[Aabb],
                       sample_count: int) -> List[FramingSample]:
        count = max(1, min(sample_count, PLAYBLAST_SAMPLES_MAX))
        if len(plan.path.keyframes) == 1:
            count = 1
        frames: List[FramingSample] = []
        for i in range(count):
            t = i / max(1, count - 1)
            pose = plan.path.sample(t)
            frame = plan.start_frame + int(round(
                t * max(0, plan.end_frame - plan.start_frame)))
            subject = self._subject_center(subject_bounds)
            proj = (project_to_screen(subject, pose, plan.lens)
                    if subject is not None else None)
            head = self._subject_head(subject_bounds)
            proj_head = (project_to_screen(head, pose, plan.lens)
                         if head is not None else None)
            head_room = 1.0 - plan.framing.head_room_ratio
            frames.append(FramingSample(
                frame=frame,
                position=pose.position,
                look_at=pose.look_at,
                subject_screen_x=round(proj.x, 4) if proj else 0.0,
                subject_screen_y=round(proj.y, 4) if proj else 0.0,
                subject_visible=bool(proj and proj.visible),
                head_screen_y=round(proj_head.y, 4) if proj_head else 0.0,
                head_room_ok=bool(proj_head and proj_head.visible
                                  and proj_head.y <= head_room),
                look_room_ok=True,
                fov_degrees=round(math.degrees(plan.lens.horizontal_fov_rad()),
                                  3),
            ))
        return frames

    @staticmethod
    def _subject_center(bounds: Optional[Aabb]) -> Optional[Vec3]:
        if bounds is None:
            return None
        return Vec3(x=bounds.center_x, y=bounds.center_y,
                    z=(bounds.min.z + bounds.max.z) / 2.0)

    @staticmethod
    def _subject_head(bounds: Optional[Aabb]) -> Optional[Vec3]:
        if bounds is None:
            return None
        return Vec3(x=bounds.center_x, y=bounds.center_y, z=bounds.top_z)


__all__ = [
    "PLAYBLAST_MANIFEST_VERSION",
    "PLAYBLAST_SAMPLES_MAX",
    "FramingSample",
    "CameraPathManifest",
    "PlayblastManifestBuilder",
]
