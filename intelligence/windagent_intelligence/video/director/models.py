"""
Director planner schemas (Phase 8).

The Director is model-backed: it builds a structured planning prompt from a
`VideoProductionPackage`, calls the `PreproductionModelPort`, and expects a
STRUCTURED JSON answer matching `PlannerOutput` (no free-text parsing —
plan §9.4). A deterministic validator then decides whether the proposed plan
is valid; invalid model output raises a typed failure and never publishes a
partial plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.director import (
    DirectorialIssue,
    ScriptRevisionProposal,
)
from windagent_core.domain.video_production.enums import (
    CameraMovement,
    GenerationMode,
    ShotType,
    TransitionType,
)
from windagent_core.domain.video_production.ids import (
    DialogueLineId,
    ReferenceAssetId,
    SceneId,
)
from windagent_core.domain.video_production.shot import CinematicPlan


class BeatPlan(BaseModel):
    """One narrative beat within a scene (plan §9.1)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    beat_order: int = Field(ge=1)
    objective: str = ""
    source: str = ""  # e.g. "scene.action" or "dialogue:<line_id>"


class SceneObjectivePlan(BaseModel):
    """Proposed narrative goal + beats for a single scene."""

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_id: SceneId
    objective: str = Field(min_length=1)
    beats: List[BeatPlan] = Field(default_factory=list)
    required_story_facts: List[str] = Field(default_factory=list)


class ShotPlan(BaseModel):
    """Proposed shot from the planner (validated before publish)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_id: SceneId
    order: int = Field(ge=1)
    shot_type: ShotType = ShotType.MEDIUM
    camera_movement: CameraMovement = CameraMovement.STATIC
    camera_angle: str = "eye-level"
    duration_seconds: float = Field(gt=0)
    framing_description: str = ""
    transition_type: TransitionType = TransitionType.CUT
    generation_mode: GenerationMode = GenerationMode.TEXT_TO_VIDEO
    dialogue_line_ids: List[DialogueLineId] = Field(default_factory=list)
    reference_asset_ids: List[ReferenceAssetId] = Field(default_factory=list)
    narrative_purpose: str = ""


class PlannerOutput(BaseModel):
    """Structured, schema-validated planner proposal."""

    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: str = "1.0.0"
    planner_version: str = Field(min_length=1)
    scene_objectives: List[SceneObjectivePlan] = Field(default_factory=list)
    shots: List[ShotPlan] = Field(default_factory=list)


@dataclass(frozen=True)
class DirectorPlanReceipt:
    """Detailed result of `create_cinematic_plan_receipt` — never partial."""

    plan: CinematicPlan
    plan_hash: str
    source_package_hash: str
    scene_objectives: List[SceneObjectivePlan]
    issues: List[DirectorialIssue] = field(default_factory=list)
    proposals: List[ScriptRevisionProposal] = field(default_factory=list)
    planner_version: str = "1.0.0"
    prompt_version: str = ""
    prompt_hash: str = ""
    duration_policy_version: str = "1.0.0"
    screenplay_locked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.model_dump(mode="json"),
            "plan_hash": self.plan_hash,
            "source_package_hash": self.source_package_hash,
            "scene_objectives": [o.model_dump(mode="json") for o in self.scene_objectives],
            "issues": [i.to_dict() for i in self.issues],
            "proposals": [p.to_dict() for p in self.proposals],
            "planner_version": self.planner_version,
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "duration_policy_version": self.duration_policy_version,
            "screenplay_locked": self.screenplay_locked,
            "metadata": self.metadata,
        }


__all__ = [
    "BeatPlan",
    "SceneObjectivePlan",
    "ShotPlan",
    "PlannerOutput",
    "DirectorPlanReceipt",
]
