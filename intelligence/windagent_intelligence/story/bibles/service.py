"""Plan B B4 canon pipeline services (S6).

- ``BibleGenerationService`` — expand a ``SelectedIdea`` into
  ``StoryBible`` + ``WorldBible`` + ``CharacterCanon`` as ONE consistent set:
  invoke the catalog prompt ``story.bibles.generate`` through
  ``StoryModelBoundary`` (schema-first), construct the three immutable
  artifacts, then cross-validate them together (``validate_canon_set``:
  referential integrity, duplicates, relationship cycles, world-rule
  conflicts, audience/safety). Findings are actionable issues — canon is
  never auto-mutated; any blocking/warning finding fails the generation with
  a typed ``BibleValidationFailure``. Approval of the set is an A checkpoint
  command, never this service.
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
from windagent_core.domain.story.ideation import SelectedIdea, validate_selected_idea
from windagent_intelligence.story.prompts import (
    StoryModelBoundary,
    StoryModelProvenance,
)

__all__ = [
    "DEFAULT_AUDIENCE_MIN_AGE",
    "DEFAULT_AUDIENCE_MAX_AGE",
    "BibleValidationFailure",
    "BibleGenerationResult",
    "BibleGenerationService",
]

DEFAULT_AUDIENCE_MIN_AGE = 5
DEFAULT_AUDIENCE_MAX_AGE = 8


class BibleValidationFailure(StudioValidationError):
    """Model output was schema-valid but failed canon cross-validation (typed)."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


@dataclass(frozen=True)
class BibleGenerationResult:
    """The three cross-validated canon artifacts + provenance + validation."""

    story_bible: StoryBible
    world_bible: WorldBible
    character_canon: CharacterCanon
    provenance: StoryModelProvenance
    validation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "story_bible": self.story_bible.to_canonical_dict(),
            "world_bible": self.world_bible.to_canonical_dict(),
            "character_canon": self.character_canon.to_canonical_dict(),
            "validation": self.validation,
            "provenance": self.provenance.to_dict(),
        }


class BibleGenerationService:
    """Generate + cross-validate the three canon artifacts as one set."""

    def __init__(self, boundary: StoryModelBoundary) -> None:
        self.boundary = boundary

    async def generate(
        self,
        selected_idea: SelectedIdea,
        *,
        language: str = "vi",
        audience_min_age: int = DEFAULT_AUDIENCE_MIN_AGE,
        audience_max_age: int = DEFAULT_AUDIENCE_MAX_AGE,
        route_lock_id: Optional[str] = None,
    ) -> BibleGenerationResult:
        idea_report = validate_selected_idea(selected_idea)
        if not idea_report.is_pass():
            raise BibleValidationFailure(
                "SelectedIdea failed validation (stale or incomplete input).",
                details={"issues": [i.to_dict() for i in idea_report.issues]},
            )

        result = await self.boundary.invoke(
            "story.bibles.generate",
            variables=self._variables(
                selected_idea,
                language=language,
                audience_min_age=audience_min_age,
                audience_max_age=audience_max_age,
            ),
            route_lock_id=route_lock_id,
        )
        story_bible = StoryBible(**result.data["story_bible"])
        world_bible = WorldBible(**result.data["world_bible"])
        character_canon = CharacterCanon(**result.data["character_canon"])

        set_report = validate_canon_set(
            story_bible,
            world_bible,
            character_canon,
            audience_min_age=audience_min_age,
        )
        if not set_report.is_pass():
            raise BibleValidationFailure(
                "Bible set failed cross-validation; canon is never auto-mutated.",
                details={"issues": [i.to_dict() for i in set_report.issues]},
            )
        return BibleGenerationResult(
            story_bible=story_bible,
            world_bible=world_bible,
            character_canon=character_canon,
            provenance=result.provenance,
            validation=set_report.summary(),
        )

    @staticmethod
    def _variables(
        selected_idea: SelectedIdea,
        *,
        language: str,
        audience_min_age: int,
        audience_max_age: int,
    ) -> Dict[str, Any]:
        return {
            "title": selected_idea.title,
            "summary": selected_idea.summary or selected_idea.title,
            "language": language,
            "audience_min_age": audience_min_age,
            "audience_max_age": audience_max_age,
        }
