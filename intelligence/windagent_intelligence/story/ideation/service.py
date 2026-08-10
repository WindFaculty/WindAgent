"""Plan B B3 ideation pipeline services (S4-S5).

- ``IdeaGenerationService`` — normalize the brief, invoke the catalog prompt
  ``story.ideation.generate`` through ``StoryModelBoundary`` (schema-first),
  build a validated 3-5 ``IdeaCandidateSet``. Never accepts invalid output:
  schema failures come from the boundary, count/uniqueness/safety failures
  are typed ``IdeaValidationFailure``.
- ``IdeaEvaluationService`` — deterministic evaluation: validate, score with
  the frozen rubric (optional model-assisted values for the model-assisted
  dimensions), produce a recommendation. Selection policy decides whether
  automation MAY auto-select; selection itself is always an A command bound
  to the set hash/revision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_core.domain.story.ideation import (
    SELECTION_POLICY_AUTO,
    SELECTION_POLICIES,
    CreativeBrief,
    IdeaCandidate,
    IdeaCandidateSet,
    normalize_creative_brief,
    score_candidate_set,
    selection_allowed,
    validate_creative_brief,
    validate_idea_candidate_set,
)
from windagent_intelligence.story.prompts import (
    StoryModelBoundary,
    StoryModelProvenance,
)

__all__ = [
    "DEFAULT_TARGET_CANDIDATE_COUNT",
    "IdeaValidationFailure",
    "IdeaGenerationResult",
    "IdeaEvaluationResult",
    "IdeaGenerationService",
    "IdeaEvaluationService",
]

DEFAULT_TARGET_CANDIDATE_COUNT = 4


class IdeaValidationFailure(StudioValidationError):
    """Model output was schema-valid but failed domain validation (typed)."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


def _candidate_from_json(raw: Dict[str, Any], index: int) -> IdeaCandidate:
    return IdeaCandidate(
        candidate_id=str(raw["candidate_id"]),
        title=str(raw["title"]),
        summary=str(raw.get("summary", "")),
        premise=str(raw.get("premise", "")),
        logline=str(raw.get("logline", "")),
        themes=[str(t) for t in raw.get("themes", [])],
        age_fit=float(raw.get("age_fit", 0.5)),
        safety_ok=bool(raw.get("safety_ok", False)),
        content={
            "estimated_seconds": int(raw.get("estimated_seconds", 240)),
            "scene_count": int(raw.get("scene_count", 5)),
            "character_count": int(raw.get("character_count", 2)),
            "location_count": int(raw.get("location_count", 2)),
            "source_index": index,
        },
    )


@dataclass(frozen=True)
class IdeaGenerationResult:
    """Validated candidate set + the normalized brief it was generated from."""

    brief: CreativeBrief
    candidate_set: IdeaCandidateSet
    provenance: StoryModelProvenance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brief": self.brief.to_summary(),
            "candidate_set": self.candidate_set.to_summary(),
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class IdeaEvaluationResult:
    """Scored set, recommendation, and the selection-policy decision."""

    candidate_set: IdeaCandidateSet
    recommendation: Optional[str]
    selection_policy: str
    auto_selection_allowed: bool

    def to_dict(self) -> Dict[str, Any]:
        data = self.candidate_set.to_summary()
        data.update(
            {
                "recommendation": self.recommendation,
                "selection_policy": self.selection_policy,
                "auto_selection_allowed": self.auto_selection_allowed,
            }
        )
        return data


class IdeaGenerationService:
    """Generate a validated 3-5 candidate set from a CreativeBrief."""

    def __init__(self, boundary: StoryModelBoundary) -> None:
        self.boundary = boundary

    async def generate(
        self,
        brief: CreativeBrief,
        *,
        normalize: bool = True,
        target_count: int = DEFAULT_TARGET_CANDIDATE_COUNT,
        route_lock_id: Optional[str] = None,
    ) -> IdeaGenerationResult:
        if not (3 <= target_count <= 5):
            raise IdeaValidationFailure(
                f"target_count must be within 3-5; got {target_count}.",
                details={"target_count": target_count},
            )
        normalized = normalize_creative_brief(brief) if normalize else brief
        brief_report = validate_creative_brief(normalized)
        if not brief_report.is_pass():
            raise IdeaValidationFailure(
                "CreativeBrief failed normalization validation.",
                details={"issues": [i.to_dict() for i in brief_report.issues]},
            )

        variables = self._variables(normalized, target_count)
        result = await self.boundary.invoke(
            "story.ideation.generate",
            variables=variables,
            route_lock_id=route_lock_id,
        )
        candidates = [
            _candidate_from_json(raw, index)
            for index, raw in enumerate(result.data.get("candidates", []))
        ]
        candidate_set = IdeaCandidateSet(candidates=candidates)
        set_report = validate_idea_candidate_set(candidate_set, normalized)
        if not set_report.is_pass():
            raise IdeaValidationFailure(
                "Idea candidate set failed validation.",
                details={"issues": [i.to_dict() for i in set_report.issues]},
            )
        return IdeaGenerationResult(
            brief=normalized,
            candidate_set=candidate_set,
            provenance=result.provenance,
        )

    @staticmethod
    def _variables(brief: CreativeBrief, target_count: int) -> Dict[str, Any]:
        return {
            "title": brief.title,
            "genre": brief.genre or "chung",
            "logline": brief.logline,
            "tone": brief.tone or "ấm áp",
            "audience": brief.audience or brief.audience_band(),
            "audience_min_age": brief.audience_min_age,
            "audience_max_age": brief.audience_max_age,
            "language": brief.language,
            "theme": brief.theme,
            "target_duration_seconds": brief.target_duration_seconds,
            "constraints": ", ".join(brief.constraints) if brief.constraints else "không",
            "prohibited_content": ", ".join(brief.prohibited_content) if brief.prohibited_content else "không",
            "target_count": target_count,
        }


class IdeaEvaluationService:
    """Deterministic evaluation + recommendation under a selection policy."""

    def __init__(self, *, selection_policy: str = SELECTION_POLICY_AUTO) -> None:
        if selection_policy not in SELECTION_POLICIES:
            raise ValueError(
                f"unknown selection policy {selection_policy!r}; "
                f"expected one of {SELECTION_POLICIES}"
            )
        self.selection_policy = selection_policy

    def evaluate(
        self,
        brief: CreativeBrief,
        candidate_set: IdeaCandidateSet,
        *,
        model_values: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> IdeaEvaluationResult:
        report = validate_idea_candidate_set(candidate_set, brief)
        if not report.is_pass():
            raise IdeaValidationFailure(
                "Cannot evaluate an invalid candidate set.",
                details={"issues": [i.to_dict() for i in report.issues]},
            )
        scored = score_candidate_set(brief, candidate_set, model_values)
        return IdeaEvaluationResult(
            candidate_set=scored,
            recommendation=scored.recommended_candidate_id,
            selection_policy=self.selection_policy,
            auto_selection_allowed=selection_allowed(self.selection_policy, scored),
        )
