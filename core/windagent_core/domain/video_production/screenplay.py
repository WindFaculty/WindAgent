"""
Screenplay-related aggregates: CreativeBrief, StoryConcept, DialogueLine,
and Screenplay.

The package serializes scenes INSIDE the screenplay (road_map.md Phase 3
package example: ``"screenplay": {"scenes": []}``) and keeps dialogue lines
at the top level of the package. Scenes reference locations, characters, and
dialogue lines by stable ID.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import ScreenplayStatus
from windagent_core.domain.video_production.ids import (
    CharacterId,
    CreativeBriefId,
    DialogueLineId,
    SceneId,
    ScreenplayId,
    StoryConceptId,
)
from windagent_core.domain.video_production.scene import Scene


class CreativeBrief(BaseModel):
    """Creative direction and production constraints for a project."""

    model_config = ConfigDict(frozen=True, extra="allow")

    brief_id: CreativeBriefId
    title: str = Field(min_length=1)
    genre: str = ""
    logline: str = ""
    tone: str = ""
    audience: str = ""
    target_duration_seconds: int = Field(gt=0, default=60)
    aspect_ratio: str = "16:9"
    production_constraints: Dict[str, Any] = Field(default_factory=dict)


class StoryConcept(BaseModel):
    """High-level story concept used to seed screenplay generation."""

    model_config = ConfigDict(frozen=True, extra="allow")

    concept_id: StoryConceptId
    title: str = Field(min_length=1)
    premise: str = ""
    synopsis: str = ""
    themes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DialogueLine(BaseModel):
    """A single line of dialogue bound to a scene and character."""

    model_config = ConfigDict(frozen=True, extra="allow")

    dialogue_id: DialogueLineId
    scene_id: SceneId
    character_id: CharacterId
    order: int = Field(ge=1)
    text: str = Field(min_length=1)
    delivery: str = ""


class Screenplay(BaseModel):
    """Ordered scenes (embedded) forming the screenplay."""

    model_config = ConfigDict(frozen=True, extra="allow")

    screenplay_id: ScreenplayId
    title: str = Field(min_length=1)
    logline: str = ""
    status: ScreenplayStatus = ScreenplayStatus.DRAFT
    scenes: List[Scene] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def scene_ids(self) -> List[SceneId]:
        return [s.scene_id for s in self.scenes]

    @property
    def dialogue_line_ids(self) -> List[DialogueLineId]:
        return [d.dialogue_id for s in self.scenes for d in s.dialogue_line_ids]


__all__ = [
    "CreativeBrief",
    "StoryConcept",
    "DialogueLine",
    "Screenplay",
]
