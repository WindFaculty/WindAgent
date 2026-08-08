"""
Blend transition planner (VP3D Phase 15, stage_h §3 backlog 6).

Plans a blend between two tracks of the SAME actor with a stable frame
boundary (the first track's end frame). The blend window straddles the
boundary; overlap beyond the window fails closed with `AnimationCompileError`
(OVERLAP_CONFLICT) — two animations must never silently fight over the same
frames (stage_h §6 ownership/conflict).

The planner only plans; baking the in-between poses is the renderer's job.
"""

from __future__ import annotations

from typing import Optional

from windagent_core.domain.video_production.animation import BlendTransition
from windagent_core.domain.video_production.errors import AnimationCompileError
from windagent_core.domain.video_production.ids import BlendTransitionId
from windagent_intelligence.video.ids import StableIdFactory

BLEND_DEFAULT_WINDOW_FRAMES = 6


class BlendPlanner:
    """Deterministic blend planning with stable boundaries (backlog 6)."""

    def __init__(self, id_factory: Optional[StableIdFactory] = None) -> None:
        self.id_factory = id_factory or StableIdFactory()

    def plan(
        self,
        *,
        track_a,
        track_b,
        blend_window_frames: int = BLEND_DEFAULT_WINDOW_FRAMES,
    ) -> BlendTransition:
        if track_a.actor_id != track_b.actor_id:
            raise AnimationCompileError(
                "blend requires two tracks of the same actor",
                details={
                    "kind": "OVERLAP_CONFLICT",
                    "actor_a": track_a.actor_id,
                    "actor_b": track_b.actor_id,
                })

        overlap = track_a.end_frame - track_b.start_frame
        if overlap > blend_window_frames:
            raise AnimationCompileError(
                "track overlap exceeds the blend window",
                details={
                    "kind": "OVERLAP_CONFLICT",
                    "track_a": str(track_a.track_id),
                    "track_b": str(track_b.track_id),
                    "overlap_frames": overlap,
                    "blend_window_frames": blend_window_frames,
                    "boundary_frame": track_a.end_frame,
                })

        boundary = track_a.end_frame  # stable frame boundary
        return BlendTransition(
            transition_id=BlendTransitionId(
                self.id_factory.blend_transition_id(
                    track_a.actor_id, boundary)),
            actor_id=track_a.actor_id,
            from_track_id=track_a.track_id,
            to_track_id=track_b.track_id,
            boundary_frame=boundary,
            blend_window_frames=blend_window_frames,
        )


__all__ = ["BLEND_DEFAULT_WINDOW_FRAMES", "BlendPlanner"]
