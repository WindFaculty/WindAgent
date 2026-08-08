"""
Occlusion preflight (VP3D Phase 13, stage_g §3 backlog 5).

Uses the scene proxy (forbidden volumes from the set-dressing `EnvironmentSpec`
plus the subject's AABB) to check camera->subject occlusion along the camera
path. Moving cameras/actors sample MULTIPLE frames; the sampling density scales
with path complexity (stage_g §6 risk: sampling only the first frame misses
dynamic errors).

Pure AABB segment tests (Liang-Barsky) — no mesh geometry, no Blender API.
"""

from __future__ import annotations

import math
from typing import List, Optional

from windagent_core.domain.video_production.cinematography import (
    CameraFinding,
    CameraFindingKind,
    CameraRigPlan,
    segment_hits_aabb,
)
from windagent_core.domain.video_production.ids import CameraFindingId
from windagent_core.domain.video_production.set_dressing import (
    Aabb,
    ForbiddenVolume,
    Vec3,
)

OCCLUSION_SAMPLES_MIN = 1
OCCLUSION_SAMPLES_MAX = 12
OCCLUSION_SAMPLE_STEP_M = 2.0   # one sample per 2m of path


class OcclusionPreflight:
    """Samples the camera path and reports blocking occlusion findings."""

    def __init__(self, *, finding_prefix: str = "occ") -> None:
        self.finding_prefix = finding_prefix

    # ------------------------------------------------------------------
    def preflight(
        self,
        *,
        plan: CameraRigPlan,
        subject_bounds: Aabb,
        forbidden_volumes: Optional[List[ForbiddenVolume]] = None,
    ) -> List[CameraFinding]:
        if not forbidden_volumes:
            return []
        samples = self._sample_count(plan)
        findings: List[CameraFinding] = []
        subject_center = Vec3(
            x=subject_bounds.center_x, y=subject_bounds.center_y,
            z=(subject_bounds.min.z + subject_bounds.max.z) / 2.0,
        )
        path_length = plan.path.length_m()
        for i in range(samples):
            t = i / max(1, samples - 1)
            pose = plan.path.sample(t)
            frame = plan.start_frame + int(round(
                t * max(0, plan.end_frame - plan.start_frame)))
            for volume in forbidden_volumes:
                if segment_hits_aabb(pose.position, subject_center,
                                     volume.bounds):
                    findings.append(CameraFinding(
                        finding_id=CameraFindingId(
                            f"{self.finding_prefix}:{plan.shot_id}:{frame}:"
                            f"{volume.name or 'vol'}"),
                        kind=CameraFindingKind.OCCLUSION,
                        shot_id=plan.shot_id,
                        detail=(
                            f"camera->subject segment blocked by {volume.name!r} "
                            f"at frame {frame} (sample {i + 1}/{samples})"
                        ),
                        blocking=True,
                        frame=frame,
                        position=pose.position,
                        measured={
                            "sample_index": i,
                            "sample_count": samples,
                            "volume": volume.name or "",
                            "path_length_m": round(path_length, 3),
                        },
                    ))
                    break  # one finding per sample frame is enough
        return findings

    # ------------------------------------------------------------------
    def _sample_count(self, plan: CameraRigPlan) -> int:
        """Density scales with path length; static paths sample 1 frame."""
        length = plan.path.length_m()
        if length <= 1e-6:
            return OCCLUSION_SAMPLES_MIN
        count = 1 + int(math.ceil(length / OCCLUSION_SAMPLE_STEP_M))
        return max(OCCLUSION_SAMPLES_MIN, min(count, OCCLUSION_SAMPLES_MAX))


__all__ = [
    "OCCLUSION_SAMPLES_MIN",
    "OCCLUSION_SAMPLES_MAX",
    "OCCLUSION_SAMPLE_STEP_M",
    "OcclusionPreflight",
]
