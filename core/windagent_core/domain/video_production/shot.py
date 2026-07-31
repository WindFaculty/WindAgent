"""
Shot planning aggregates: CinematicPlan, Shot, ShotDependency, and the
ShotDependencyGraph (road_map.md Phase 9).

Shots carry an explicit `order` integer within their scene; dependencies are
typed edges between shot IDs. The graph must stay acyclic for scheduling.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    CameraMovement,
    DependencyType,
    GenerationMode,
    ShotType,
    TransitionType,
)
from windagent_core.domain.video_production.ids import (
    CinematicPlanId,
    DialogueLineId,
    ProductionRevisionId,
    ReferenceAssetId,
    SceneId,
    ShotDependencyId,
    ShotId,
    VideoProjectId,
)


class Shot(BaseModel):
    """A single camera shot within a scene."""

    model_config = ConfigDict(frozen=True, extra="allow")

    shot_id: ShotId
    scene_id: SceneId
    order: int = Field(ge=1)
    shot_type: ShotType = ShotType.MEDIUM
    camera_movement: CameraMovement = CameraMovement.STATIC
    duration_seconds: float = Field(gt=0)
    framing_description: str = ""
    transition_type: TransitionType = TransitionType.CUT
    generation_mode: GenerationMode = GenerationMode.TEXT_TO_VIDEO
    dialogue_line_ids: List[DialogueLineId] = Field(default_factory=list)
    reference_asset_ids: List[ReferenceAssetId] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ShotDependency(BaseModel):
    """Typed dependency edge between two shots."""

    model_config = ConfigDict(frozen=True, extra="allow")

    dependency_id: ShotDependencyId
    from_shot_id: ShotId
    to_shot_id: ShotId
    dependency_type: DependencyType = DependencyType.TEMPORAL
    reason: str = ""


class ShotDependencyGraph(BaseModel):
    """Directed acyclic graph over shots for scheduling."""

    model_config = ConfigDict(frozen=True, extra="allow")

    shots: List[Shot] = Field(default_factory=list)
    dependencies: List[ShotDependency] = Field(default_factory=list)

    def shot_ids(self) -> List[ShotId]:
        return [s.shot_id for s in self.shots]

    def ordered_shot_ids(self) -> List[ShotId]:
        """Shots ordered by (scene order, shot order) using stable sort keys."""
        return [
            s.shot_id
            for s in sorted(self.shots, key=lambda s: (str(s.scene_id), s.order))
        ]

    def dependencies_of(self, shot_id: ShotId) -> List[ShotDependency]:
        return [d for d in self.dependencies if d.from_shot_id == shot_id]


class CinematicPlan(BaseModel):
    """Shot plan for a revision: shots + typed dependency graph."""

    model_config = ConfigDict(frozen=True, extra="allow")

    plan_id: CinematicPlanId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    graph: ShotDependencyGraph = Field(default_factory=ShotDependencyGraph)
    locked: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "Shot",
    "ShotDependency",
    "ShotDependencyGraph",
    "CinematicPlan",
]
