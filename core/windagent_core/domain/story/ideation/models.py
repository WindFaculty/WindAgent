"""
Plan B ideation content models (studio.artifact/v1alpha1): S4-S5.

- ``CreativeBrief`` — normalized creative direction (B3 normalization target).
- ``IdeaCandidate`` — one idea candidate with deterministic score dimensions.
- ``IdeaCandidateSet`` — frozen set of exactly 3-5 distinct candidates.
- ``SelectedIdea`` — hash-bound selection result (selection is an A command).

Compatibility: the field inventories of the legacy video-production content
models are preserved or explicitly mapped (B0 pin); ``IdeaCandidate`` /
``IdeaCandidateSet`` keep the exact construction surface A's envelope tests
rely on (``candidate_id``, ``title``, ``score``, ``score_dimensions``,
``content``; count rule 3-5 raising ``StudioValidationError``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_core.domain.story.canonical import StoryContent
from windagent_core.domain.story.ids import (
    CreativeBriefId,
    SelectedIdeaId,
)
from windagent_core.domain.video_production.ids import StoryConceptId

__all__ = [
    "CreativeBrief",
    "IdeaCandidate",
    "IdeaCandidateSet",
    "SelectedIdea",
    "MIN_IDEA_CANDIDATES",
    "MAX_IDEA_CANDIDATES",
    "AGE_BAND_SEPARATOR",
]

MIN_IDEA_CANDIDATES = 3
MAX_IDEA_CANDIDATES = 5
AGE_BAND_SEPARATOR = "-"


class CreativeBrief(StoryContent):
    """Normalized creative direction for one episode (B3 normalization target).

    Preserves every pinned legacy field (``brief_id``, ``title``, ``genre``,
    ``logline``, ``tone``, ``audience``, ``target_duration_seconds``,
    ``aspect_ratio``, ``production_constraints``) and adds the frozen
    normalized fields: ``language``, audience band, ``theme``, ``constraints``,
    ``prohibited_content``.
    """

    artifact_type: str = "CreativeBrief"
    brief_id: CreativeBriefId
    title: str = Field(min_length=1)
    genre: str = ""
    logline: str = ""
    tone: str = ""
    audience: str = ""
    audience_min_age: int = Field(default=0, ge=0)
    audience_max_age: int = Field(default=99, ge=0)
    language: str = "vi"
    theme: str = ""
    target_duration_seconds: int = Field(gt=0, default=240)
    aspect_ratio: str = "16:9"
    constraints: List[str] = Field(default_factory=list)
    prohibited_content: List[str] = Field(default_factory=list)
    production_constraints: Dict[str, Any] = Field(default_factory=dict)

    SUMMARY_FIELDS = (
        "artifact_type", "brief_id", "title", "genre", "logline", "tone",
        "audience", "language", "theme", "target_duration_seconds",
    )

    def audience_band(self) -> str:
        return f"{self.audience_min_age}{AGE_BAND_SEPARATOR}{self.audience_max_age}"


class IdeaCandidate(StoryContent):
    """A single idea candidate with deterministic score dimensions."""

    artifact_type: str = "IdeaCandidate"
    candidate_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = ""
    premise: str = ""
    logline: str = ""
    themes: List[str] = Field(default_factory=list)
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    score_dimensions: Dict[str, float] = Field(default_factory=dict)
    brief_adherence: float = Field(default=0.0, ge=0.0, le=1.0)
    age_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    safety_ok: bool = True
    content: Dict[str, Any] = Field(default_factory=dict)

    SUMMARY_FIELDS = (
        "artifact_type", "candidate_id", "title", "summary", "score",
        "score_dimensions", "age_fit", "safety_ok",
    )

    def to_story_concept(self, concept_id: Optional[StoryConceptId] = None) -> Any:
        """Compatibility projection to the legacy single-concept shape.

        Explicit loss metadata (B0 rule): the legacy model has no scores,
        safety, or adherence fields; the caller receives them as a tuple.
        """
        from windagent_core.domain.video_production.screenplay import StoryConcept

        concept = StoryConcept(
            concept_id=concept_id or StoryConceptId.generate("sc"),
            title=self.title,
            premise=self.premise or self.summary,
            synopsis=self.summary,
            themes=self.themes,
            metadata={"candidate_id": self.candidate_id},
        )
        loss = {
            "dropped": ["score", "score_dimensions", "age_fit", "safety_ok", "brief_adherence"],
            "note": "Legacy StoryConcept carries no deterministic score fields.",
        }
        return concept, loss


class IdeaCandidateSet(StoryContent):
    """A frozen candidate set containing exactly 3-5 distinct candidates."""

    artifact_type: str = "IdeaCandidateSet"
    candidates: List[IdeaCandidate] = Field(default_factory=list)
    evaluated: bool = False
    scoring_rubric_version: Optional[str] = None
    recommended_candidate_id: Optional[str] = None

    SUMMARY_FIELDS = (
        "artifact_type", "evaluated", "scoring_rubric_version",
        "recommended_candidate_id", "candidate_count",
    )

    @field_validator("candidates")
    @classmethod
    def _validate_candidate_count(cls, candidates: List[IdeaCandidate]) -> List[IdeaCandidate]:
        if not (MIN_IDEA_CANDIDATES <= len(candidates) <= MAX_IDEA_CANDIDATES):
            raise StudioValidationError(
                f"IdeaCandidateSet must contain {MIN_IDEA_CANDIDATES}-"
                f"{MAX_IDEA_CANDIDATES} candidates; got {len(candidates)}."
            )
        return candidates

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    def summary(self) -> Dict[str, Any]:
        data = self.to_summary()
        data["candidate_count"] = self.candidate_count
        return data

    @property
    def distinct_ids(self) -> bool:
        ids = [c.candidate_id for c in self.candidates]
        return len(ids) == len(set(ids))


class SelectedIdea(StoryContent):
    """Hash-bound selection result; selection itself is an A command.

    ``candidate_id`` references a candidate inside the source
    ``IdeaCandidateSet`` artifact (identified by ``source_set_id``); hash
    binding lives on the A envelope input refs, never inside this content.
    """

    artifact_type: str = "SelectedIdea"
    selected_idea_id: SelectedIdeaId
    source_set_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = ""
    rationale: str = ""
    score: Optional[float] = None
    score_dimensions: Dict[str, float] = Field(default_factory=dict)
    selection_policy: str = "AUTO_WHEN_POLICY_ALLOWS"  # frozen vocabulary

    SUMMARY_FIELDS = (
        "artifact_type", "selected_idea_id", "source_set_id", "candidate_id",
        "title", "summary", "score", "selection_policy",
    )
