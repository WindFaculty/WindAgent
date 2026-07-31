"""
VideoDirectionPort — canonical contract for the Director layer.

The Director consumes a VideoProductionPackage and produces a locked
CinematicPlan. It must NOT mutate the locked screenplay and must NOT submit
generations on its own (road_map.md Phase 8 responsibilities).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.shot import CinematicPlan


@runtime_checkable
class VideoDirectionPort(Protocol):
    """Port for director responsibilities."""

    async def create_cinematic_plan(self, package: VideoProductionPackage) -> CinematicPlan:
        """Create a cinematic plan from an immutable package."""
        ...

    async def lock_shot_plan(self, plan: CinematicPlan) -> CinematicPlan:
        """Lock a shot plan for downstream generation."""
        ...


__all__ = ["VideoDirectionPort"]
