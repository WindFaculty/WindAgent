"""Plan B B5 outline pipeline services (S7).

- ``BeatGenerationService`` — expand canon into an ordered ``BeatSheet``
  allocating the episode duration budget: invoke the catalog prompt
  ``story.beats.generate`` through ``StoryModelBoundary`` (schema-first),
  build the immutable BeatSheet, then validate duration/order/roles/canon
  refs. Findings fail closed with a typed ``OutlineValidationFailure``.
- ``OutlineGenerationService`` — plan ``EpisodeOutline`` scenes from the
  BeatSheet (``story.outline.structured``): duration bounds, beat coverage,
  causal order, and canon/location references are all deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_core.domain.story.bibles import (
    CharacterCanon,
    StoryBible,
    WorldBible,
    validate_canon_set,
)
from windagent_core.domain.story.outline import (
    BeatSheet,
    EpisodeOutline,
    validate_beat_sheet,
    validate_episode_outline,
)
from windagent_intelligence.story.prompts import (
    StoryModelBoundary,
    StoryModelProvenance,
)

__all__ = [
    "DEFAULT_TARGET_DURATION_SECONDS",
    "DEFAULT_TOLERANCE_SECONDS",
    "OutlineValidationFailure",
    "BeatGenerationResult",
    "OutlineGenerationResult",
    "BeatGenerationService",
    "OutlineGenerationService",
]

DEFAULT_TARGET_DURATION_SECONDS = 240
DEFAULT_TOLERANCE_SECONDS = 15


class OutlineValidationFailure(StudioValidationError):
    """Model output was schema-valid but failed outline validation (typed)."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


@dataclass(frozen=True)
class BeatGenerationResult:
    beat_sheet: BeatSheet
    provenance: StoryModelProvenance
    validation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_sheet": self.beat_sheet.to_canonical_dict(),
            "validation": self.validation,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class OutlineGenerationResult:
    episode_outline: EpisodeOutline
    provenance: StoryModelProvenance
    validation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_outline": self.episode_outline.to_canonical_dict(),
            "validation": self.validation,
            "provenance": self.provenance.to_dict(),
        }


def _characters_summary(canon: CharacterCanon) -> str:
    return ", ".join(f"{c.character_id.value} ({c.name})" for c in canon.characters)


def _locations_summary(world: WorldBible) -> str:
    return ", ".join(f"{loc.location_id.value} ({loc.name})" for loc in world.recurring_locations)


def _beats_summary(beat_sheet: BeatSheet) -> str:
    return "\n".join(
        f"- {b.beat_id.value}|{b.role}|{b.target_seconds}s|{b.description}"
        for b in beat_sheet.beats
    )


class BeatGenerationService:
    """Generate + validate an ordered BeatSheet from the canon set."""

    def __init__(self, boundary: StoryModelBoundary) -> None:
        self.boundary = boundary

    async def generate(
        self,
        story_bible: StoryBible,
        world_bible: WorldBible,
        character_canon: CharacterCanon,
        *,
        target_duration_seconds: int = DEFAULT_TARGET_DURATION_SECONDS,
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
        audience_min_age: int = 5,
        audience_max_age: int = 8,
        language: str = "vi",
        route_lock_id: Optional[str] = None,
    ) -> BeatGenerationResult:
        canon_report = validate_canon_set(
            story_bible, world_bible, character_canon,
            audience_min_age=audience_min_age,
        )
        if not canon_report.is_pass():
            raise OutlineValidationFailure(
                "Canon set failed validation; cannot plan beats on invalid canon.",
                details={"issues": [i.to_dict() for i in canon_report.issues]},
            )

        result = await self.boundary.invoke(
            "story.beats.generate",
            variables={
                "title": story_bible.title,
                "premise": story_bible.premise,
                "arc_summary": story_bible.arc_summary,
                "characters": _characters_summary(character_canon),
                "locations": _locations_summary(world_bible),
                "language": language,
                "audience_min_age": audience_min_age,
                "audience_max_age": audience_max_age,
                "target_duration_seconds": target_duration_seconds,
                "tolerance_seconds": tolerance_seconds,
                "min_beats": 4,
                "max_beats": 12,
            },
            route_lock_id=route_lock_id,
        )
        beat_sheet = BeatSheet(**result.data)
        report = validate_beat_sheet(beat_sheet, canon=character_canon)
        if not report.is_pass():
            raise OutlineValidationFailure(
                "BeatSheet failed validation; structure is never auto-fixed.",
                details={"issues": [i.to_dict() for i in report.issues]},
            )
        return BeatGenerationResult(
            beat_sheet=beat_sheet,
            provenance=result.provenance,
            validation=report.summary(),
        )


class OutlineGenerationService:
    """Generate + validate an EpisodeOutline from a BeatSheet."""

    def __init__(self, boundary: StoryModelBoundary) -> None:
        self.boundary = boundary

    async def generate(
        self,
        beat_sheet: BeatSheet,
        *,
        canon: Optional[CharacterCanon] = None,
        world: Optional[WorldBible] = None,
        target_duration_seconds: Optional[int] = None,
        language: str = "vi",
        audience_band: str = "5-8",
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
        route_lock_id: Optional[str] = None,
    ) -> OutlineGenerationResult:
        target = target_duration_seconds or beat_sheet.total_target_seconds
        result = await self.boundary.invoke(
            "story.outline.structured",
            variables={
                "beats_summary": _beats_summary(beat_sheet),
                "language": language,
                "audience_band": audience_band,
                "target_duration_seconds": target,
                "tolerance_seconds": tolerance_seconds,
                "min_scenes": 3,
                "max_scenes": 12,
            },
            route_lock_id=route_lock_id,
        )
        outline = EpisodeOutline(**result.data)
        report = validate_episode_outline(
            outline,
            beat_sheet=beat_sheet,
            canon=canon,
            world=world,
        )
        if not report.is_pass():
            raise OutlineValidationFailure(
                "EpisodeOutline failed validation; scenes are never auto-fixed.",
                details={"issues": [i.to_dict() for i in report.issues]},
            )
        return OutlineGenerationResult(
            episode_outline=outline,
            provenance=result.provenance,
            validation=report.summary(),
        )
