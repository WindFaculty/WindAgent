"""
Plan B canon content models (studio.artifact/v1alpha1): S6.

The three artifacts validate and promote as one consistent set; downstream
fixtures reference canon IDs, not free-form names alone. Canon IDs are new
Story IDs (``StoryCharacterId`` / ``StoryLocationId`` / ``StoryPropId``) and
map to downstream production only after Roadmap 1.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.story.canonical import StoryContent
from windagent_core.domain.story.ids import (
    StoryBibleId,
    StoryCharacterId,
    StoryLocationId,
    StoryPropId,
    WorldBibleId,
)

__all__ = [
    "StoryBible",
    "WorldBible",
    "WorldRule",
    "RecurringLocation",
    "RecurringObject",
    "CharacterCanon",
    "CharacterCanonEntry",
    "CharacterRelationship",
    "RELATIONSHIP_KINDS",
]

RELATIONSHIP_KINDS = frozenset({"friend", "family", "rival", "mentor", "neighbor", "other"})


class StoryBible(StoryContent):
    """Premise/theme/tone/arc/stakes/rules for the selected idea."""

    artifact_type: str = "StoryBible"
    bible_id: StoryBibleId
    title: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    theme: str = ""
    tone: str = ""
    arc_summary: str = ""          # beginning -> middle -> end in one paragraph
    stakes: str = ""
    story_rules: List[str] = Field(default_factory=list)   # what the world/story allows
    language: str = "vi"

    SUMMARY_FIELDS = (
        "artifact_type", "bible_id", "title", "premise", "theme", "tone", "stakes",
    )


class WorldRule(BaseModel):
    """A deterministic world/story rule with a stable ID."""

    model_config = ConfigDict(frozen=True, extra="allow")

    rule_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    kind: str = "physics"  # physics | social | magic | constraint


class RecurringLocation(BaseModel):
    """A recurring location referenced by stable Story ID."""

    model_config = ConfigDict(frozen=True, extra="allow")

    location_id: StoryLocationId
    name: str = Field(min_length=1)
    description: str = ""
    atmosphere: str = ""
    lighting: str = ""


class RecurringObject(BaseModel):
    """A recurring object/prop referenced by stable Story ID."""

    model_config = ConfigDict(frozen=True, extra="allow")

    prop_id: StoryPropId
    name: str = Field(min_length=1)
    description: str = ""
    significance: str = ""


class WorldBible(StoryContent):
    """Setting, physical/story rules, recurring locations and objects."""

    artifact_type: str = "WorldBible"
    world_id: WorldBibleId
    setting: str = Field(min_length=1)
    physical_rules: List[WorldRule] = Field(default_factory=list)
    story_rules: List[WorldRule] = Field(default_factory=list)
    recurring_locations: List[RecurringLocation] = Field(default_factory=list)
    recurring_objects: List[RecurringObject] = Field(default_factory=list)
    style_constraints: Dict[str, str] = Field(default_factory=dict)
    language: str = "vi"

    SUMMARY_FIELDS = (
        "artifact_type", "world_id", "setting",
        "location_count", "object_count",
    )

    @property
    def location_count(self) -> int:
        return len(self.recurring_locations)

    @property
    def object_count(self) -> int:
        return len(self.recurring_objects)


class CharacterRelationship(BaseModel):
    """A directed relationship between two canon characters."""

    model_config = ConfigDict(frozen=True, extra="allow")

    from_id: StoryCharacterId
    to_id: StoryCharacterId
    kind: str = "friend"
    description: str = ""

    @property
    def is_self_loop(self) -> bool:
        return self.from_id == self.to_id


class CharacterCanonEntry(BaseModel):
    """One canon character: stable ID, role, goals, traits, relationships."""

    model_config = ConfigDict(frozen=True, extra="allow")

    character_id: StoryCharacterId
    name: str = Field(min_length=1)
    role: str = "supporting"  # protagonist | deuteragonist | supporting | antagonist
    goal: str = ""
    traits: List[str] = Field(default_factory=list)
    relationships: List[CharacterRelationship] = Field(default_factory=list)
    appearance: str = ""
    voice: str = ""
    age_band: str = ""


class CharacterCanon(StoryContent):
    """Full character canon with stable IDs and cross-references."""

    artifact_type: str = "CharacterCanon"
    canon_id: str = Field(min_length=1)
    language: str = "vi"
    characters: List[CharacterCanonEntry] = Field(default_factory=list)

    SUMMARY_FIELDS = ("artifact_type", "canon_id", "character_count")

    @property
    def character_count(self) -> int:
        return len(self.characters)

    def character_by_id(self, character_id: StoryCharacterId) -> Optional[CharacterCanonEntry]:
        for entry in self.characters:
            if entry.character_id == character_id:
                return entry
        return None
