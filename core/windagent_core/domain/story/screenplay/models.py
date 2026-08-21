"""
Plan B structured screenplay content models (studio.artifact/v1alpha1): S8.

Structured JSON is the authority; canonical screenplay TEXT is a derived view
(B6). Scenes/beats/canon references are stable IDs; dialogue keeps the legacy
``DialogueLine`` field vocabulary (``dialogue_id``, ``scene_id``,
``character_id``, ``order``, ``text``, ``delivery``) so V2 conversion maps
losslessly, plus timing and source refs.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.story.canonical import StoryContent
from windagent_core.domain.story.ids import (
    BeatId,
    DialogueLineId,
    DraftSceneId,
    OutlineSceneId,
    ScreenplayDraftId,
    StoryCharacterId,
    StoryLocationId,
)
from windagent_core.domain.story.outline.duration import DURATION_FORMULA_VERSION

__all__ = [
    "DraftDialogueLine",
    "DraftScene",
    "ScreenplayDraft",
]

TRANSITIONS = frozenset({"CUT TO:", "DISSOLVE TO:", "FADE IN:", "FADE OUT:", "MATCH CUT:"})


class DraftDialogueLine(BaseModel):
    """One dialogue line inside a structured draft scene.

    Field vocabulary mirrors the legacy ``DialogueLine`` (lossless mapping);
    character/scene refs use canonical Story IDs.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    dialogue_id: DialogueLineId
    scene_id: DraftSceneId
    character_id: StoryCharacterId
    order: int = Field(ge=1)
    text: str = Field(min_length=1)
    delivery: str = ""
    estimated_seconds: int = Field(default=0, ge=0)


class DraftScene(BaseModel):
    """One structured screenplay scene with timing and source refs."""

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_id: DraftSceneId
    order: int = Field(ge=1)
    outline_scene_id: OutlineSceneId
    location_id: StoryLocationId
    character_ids: List[StoryCharacterId] = Field(default_factory=list)
    action_description: str = ""
    dialogue: List[DraftDialogueLine] = Field(default_factory=list)
    narration: str = ""
    transition: str = "CUT TO:"
    estimated_seconds: int = Field(default=0, ge=0)
    source_beat_ids: List[BeatId] = Field(default_factory=list)

    @property
    def dialogue_count(self) -> int:
        return len(self.dialogue)


class ScreenplayDraft(StoryContent):
    """The authoritative structured screenplay draft (3-5 minute episode)."""

    artifact_type: str = "ScreenplayDraft"
    draft_id: ScreenplayDraftId
    title: str = Field(min_length=1)
    logline: str = ""
    language: str = "vi"
    audience_band: str = "5-8"
    target_duration_seconds: int = Field(gt=0)
    tolerance_seconds: int = Field(default=15, ge=0)
    scenes: List[DraftScene] = Field(default_factory=list)
    duration_formula_version: str = DURATION_FORMULA_VERSION

    SUMMARY_FIELDS = (
        "artifact_type", "draft_id", "title", "logline", "language",
        "audience_band", "scene_count", "dialogue_count",
        "total_estimated_seconds", "target_duration_seconds",
    )

    @property
    def scene_count(self) -> int:
        return len(self.scenes)

    @property
    def dialogue_count(self) -> int:
        return sum(s.dialogue_count for s in self.scenes)

    @property
    def total_estimated_seconds(self) -> int:
        return sum(s.estimated_seconds for s in self.scenes)

    def to_summary(self) -> dict:
        data = super().to_summary()
        data["scene_count"] = self.scene_count
        data["dialogue_count"] = self.dialogue_count
        data["total_estimated_seconds"] = self.total_estimated_seconds
        return data
