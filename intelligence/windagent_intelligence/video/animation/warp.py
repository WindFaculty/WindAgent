"""
Bounded time-warp service (VP3D Phase 15, stage_h §3 backlog 5).

A clip may be stretched/compressed within [MIN_WARP_RATIO, MAX_WARP_RATIO]
(0.5x .. 2.0x of its natural duration). Outside the band the compiler must
pick another clip or request a plan revision — it fails closed with
`AnimationCompileError` (WARP_OUT_OF_BOUNDS) instead of silently stretching
a motion into an uncanny state.

Root displacement is preserved under warp (the same motion, played faster or
slower); only the frame count/duration change.
"""

from __future__ import annotations

from typing import Optional

from windagent_core.domain.video_production.animation import (
    MAX_WARP_RATIO,
    MIN_WARP_RATIO,
    TimeWarp,
)
from windagent_core.domain.video_production.errors import AnimationCompileError


class WarpService:
    """Deterministic, bounded time-warp planning (backlog 5)."""

    def apply(
        self,
        *,
        clip_duration_seconds: float,
        target_duration_seconds: float,
        fps: int,
    ) -> TimeWarp:
        ratio = target_duration_seconds / clip_duration_seconds
        if not (MIN_WARP_RATIO - 1e-9 <= ratio <= MAX_WARP_RATIO + 1e-9):
            raise AnimationCompileError(
                "time-warp outside the bounded band; pick another clip or "
                "request a plan revision",
                details={
                    "kind": "WARP_OUT_OF_BOUNDS",
                    "ratio": ratio,
                    "min_ratio": MIN_WARP_RATIO,
                    "max_ratio": MAX_WARP_RATIO,
                    "clip_duration_seconds": clip_duration_seconds,
                    "target_duration_seconds": target_duration_seconds,
                })
        return TimeWarp(
            ratio=ratio,
            duration_seconds=target_duration_seconds,
            applied_frames=round(target_duration_seconds * fps),
        )


__all__ = ["WarpService"]
