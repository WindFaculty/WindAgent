"""Plan B B6 screenplay pipeline service (S8).

``ScreenplayGenerationService`` — write the structured ``ScreenplayDraft``
from a validated ``EpisodeOutline``: fail closed when the outline does not
validate against its own upstream (beats/canon/world), invoke the catalog
prompt ``story.screenplay.structured`` through ``StoryModelBoundary``
(schema-first, bounded repair), build the immutable draft, validate
format/dialogue attribution/canon/beat coverage/duration, then render the
canonical text view. Structure is never auto-fixed; findings fail closed
with a typed ``ScreenplayValidationFailure``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_core.domain.story.bibles import CharacterCanon, WorldBible
from windagent_core.domain.story.outline import (
    BeatSheet,
    EpisodeOutline,
    validate_episode_outline,
)
from windagent_core.domain.story.screenplay import (
    ScreenplayDraft,
    validate_screenplay_draft,
)
from windagent_intelligence.story.prompts import (
    StoryModelBoundary,
    StoryModelProvenance,
)
from windagent_intelligence.story.screenplay.renderer import render_screenplay_text

__all__ = [
    "DEFAULT_TARGET_DURATION_SECONDS",
    "DEFAULT_TOLERANCE_SECONDS",
    "ScreenplayValidationFailure",
    "ScreenplayGenerationResult",
    "ScreenplayGenerationService",
]

DEFAULT_TARGET_DURATION_SECONDS = 240
DEFAULT_TOLERANCE_SECONDS = 15


class ScreenplayValidationFailure(StudioValidationError):
    """Model output was schema-valid but failed screenplay validation (typed)."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


@dataclass(frozen=True)
class ScreenplayGenerationResult:
    draft: ScreenplayDraft
    rendered_text: str
    provenance: StoryModelProvenance
    validation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft": self.draft.to_canonical_dict(),
            "rendered_text": self.rendered_text,
            "validation": self.validation,
            "provenance": self.provenance.to_dict(),
        }


def _outline_summary(outline: EpisodeOutline) -> str:
    ledger = [
        {
            "order": scene.order,
            "outline_scene_id": scene.scene_id.value,
            "location_id": scene.location_id.value,
            "character_ids": [character_id.value for character_id in scene.character_ids],
            "source_beat_ids": [beat_id.value for beat_id in scene.beat_refs],
            "estimated_seconds": scene.estimated_seconds,
            "intent": scene.intent,
        }
        for scene in outline.scenes
    ]
    return json.dumps(ledger, ensure_ascii=False, separators=(",", ":"))


def _beats_summary(beat_sheet: BeatSheet) -> str:
    return "\n".join(
        f"- {b.beat_id.value}|{b.role}|{b.target_seconds}s|{b.description}"
        for b in beat_sheet.beats
    )


def _characters_summary(canon: CharacterCanon) -> str:
    return ", ".join(f"{c.character_id.value} ({c.name})" for c in canon.characters)


def _locations_summary(world: WorldBible) -> str:
    return ", ".join(f"{loc.location_id.value} ({loc.name})" for loc in world.recurring_locations)


class ScreenplayGenerationService:
    """Generate + validate a structured ScreenplayDraft from an EpisodeOutline."""

    def __init__(self, boundary: StoryModelBoundary) -> None:
        self.boundary = boundary

    async def generate(
        self,
        episode_outline: EpisodeOutline,
        *,
        beat_sheet: Optional[BeatSheet] = None,
        canon: Optional[CharacterCanon] = None,
        world: Optional[WorldBible] = None,
        target_duration_seconds: Optional[int] = None,
        language: str = "vi",
        audience_band: str = "5-8",
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
        route_lock_id: Optional[str] = None,
    ) -> ScreenplayGenerationResult:
        if beat_sheet is not None:
            outline_report = validate_episode_outline(
                episode_outline,
                beat_sheet=beat_sheet,
                canon=canon,
                world=world,
            )
            if not outline_report.is_pass():
                raise ScreenplayValidationFailure(
                    "EpisodeOutline failed validation; cannot write on an invalid outline.",
                    details={"issues": [i.to_dict() for i in outline_report.issues]},
                )

        target = target_duration_seconds or episode_outline.target_duration_seconds
        result = await self.boundary.invoke(
            "story.screenplay.structured",
            variables={
                "outline_summary": _outline_summary(episode_outline),
                "beats_summary": _beats_summary(beat_sheet) if beat_sheet else "",
                "characters": _characters_summary(canon) if canon else "",
                "locations": _locations_summary(world) if world else "",
                "language": language,
                "audience_band": audience_band,
                "target_duration_seconds": target,
                "tolerance_seconds": tolerance_seconds,
                "min_scenes": 3,
                "max_scenes": 12,
            },
            route_lock_id=route_lock_id,
        )
        draft = ScreenplayDraft(**result.data)
        report = validate_screenplay_draft(
            draft,
            outline=episode_outline,
            beat_sheet=beat_sheet,
            canon=canon,
            world=world,
        )
        if not report.is_pass():
            raise ScreenplayValidationFailure(
                "ScreenplayDraft failed validation; structure is never auto-fixed.",
                details={"issues": [i.to_dict() for i in report.issues]},
            )
        rendered_text = render_screenplay_text(
            draft,
            character_names={c.character_id.value: c.name for c in canon.characters} if canon else None,
            location_names={
                loc.location_id.value: loc.name for loc in world.recurring_locations
            }
            if world
            else None,
        )
        return ScreenplayGenerationResult(
            draft=draft,
            rendered_text=rendered_text,
            provenance=result.provenance,
            validation=report.summary(),
        )
