"""
Plan B narrative-structure content models (studio.artifact/v1alpha1): S7.

- ``BeatSheet`` — ordered beats with role, emotional progression, and a
  target-seconds allocation over the 180-300 s budget.
- ``EpisodeOutline`` — scenes with intent, location, characters,
  conflict/change, visual action, dialogue budget, estimated seconds; every
  scene traces to beats and canon IDs.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.story.canonical import StoryContent
from windagent_core.domain.story.ids import (
    BeatId,
    BeatSheetId,
    EpisodeOutlineId,
    OutlineSceneId,
    StoryCharacterId,
    StoryLocationId,
)
from windagent_core.domain.story.outline.duration import DURATION_FORMULA_VERSION

__all__ = [
    "Beat",
    "BeatSheet",
    "OutlineScene",
    "EpisodeOutline",
]

BEAT_ROLES = frozenset({"hook", "setup", "rising", "climax", "falling", "resolution"})


class Beat(BaseModel):
    """One narrative beat with a target-seconds allocation."""

    model_config = ConfigDict(frozen=True, extra="allow")

    beat_id: BeatId
    order: int = Field(ge=1)
    role: str = "rising"
    description: str = Field(min_length=1)
    emotional_beat: str = ""
    character_ids: List[StoryCharacterId] = Field(default_factory=list)
    location_id: Optional[StoryLocationId] = None
    target_seconds: int = Field(ge=0)


class BeatSheet(StoryContent):
    """Ordered beats allocating the total episode duration."""

    artifact_type: str = "BeatSheet"
    beat_sheet_id: BeatSheetId
    title: str = Field(min_length=1)
    beats: List[Beat] = Field(default_factory=list)
    total_target_seconds: int = Field(gt=0)
    tolerance_seconds: int = Field(default=15, ge=0)
    duration_formula_version: str = DURATION_FORMULA_VERSION

    SUMMARY_FIELDS = (
        "artifact_type", "beat_sheet_id", "title",
        "beat_count", "total_target_seconds", "tolerance_seconds",
    )

    @property
    def beat_count(self) -> int:
        return len(self.beats)

    @property
    def allocated_seconds(self) -> int:
        return sum(b.target_seconds for b in self.beats)


class OutlineScene(BaseModel):
    """One planned scene inside an episode outline."""

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_id: OutlineSceneId
    order: int = Field(ge=1)
    intent: str = Field(min_length=1)
    location_id: StoryLocationId
    character_ids: List[StoryCharacterId] = Field(default_factory=list)
    conflict_change: str = ""
    visual_action: str = ""
    dialogue_budget_seconds: int = Field(default=0, ge=0)
    estimated_seconds: int = Field(ge=0)
    beat_refs: List[BeatId] = Field(default_factory=list)


class EpisodeOutline(StoryContent):
    """Production-aware narrative structure fitting the duration budget."""

    artifact_type: str = "EpisodeOutline"
    outline_id: EpisodeOutlineId
    title: str = Field(min_length=1)
    language: str = "vi"
    audience_band: str = "5-8"
    target_duration_seconds: int = Field(gt=0)
    tolerance_seconds: int = Field(default=15, ge=0)
    scenes: List[OutlineScene] = Field(default_factory=list)
    duration_formula_version: str = DURATION_FORMULA_VERSION

    SUMMARY_FIELDS = (
        "artifact_type", "outline_id", "title", "language", "audience_band",
        "scene_count", "total_estimated_seconds", "target_duration_seconds",
    )

    @property
    def scene_count(self) -> int:
        return len(self.scenes)

    @property
    def total_estimated_seconds(self) -> int:
        return sum(s.estimated_seconds for s in self.scenes)
