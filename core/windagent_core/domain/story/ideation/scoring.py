"""
Deterministic idea scoring rubric (Plan B B3; versioned, provider-free).

Dimensions (B0 taxonomy): age fit, clarity, emotional arc, originality,
duration fit, production feasibility, safety, brief adherence. Weights are
documented constants; tie-breaking is deterministic; everything is testable
outside a provider (cross-cutting rule 5).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.story.ideation.models import (
    CreativeBrief,
    IdeaCandidate,
    IdeaCandidateSet,
)

__all__ = [
    "SCORE_RUBRIC_VERSION",
    "SCORE_DIMENSION_WEIGHTS",
    "SCORE_DIMENSIONS",
    "SELECTION_POLICY_AUTO",
    "SELECTION_POLICY_HUMAN_REQUIRED",
    "SELECTION_POLICIES",
    "selection_allowed",
    "normalize_score",
    "score_dimension",
    "score_candidate_set",
    "tie_break_candidates",
]

SCORE_RUBRIC_VERSION = "score_rubric/v1"

#: Frozen selection policy vocabulary (B3). Selection itself is always an A
#: command bound to the set hash/revision; these constants only decide
#: whether automation MAY auto-select or MUST wait for a human.
SELECTION_POLICY_AUTO = "AUTO_WHEN_POLICY_ALLOWS"
SELECTION_POLICY_HUMAN_REQUIRED = "HUMAN_REQUIRED"
SELECTION_POLICIES = (SELECTION_POLICY_AUTO, SELECTION_POLICY_HUMAN_REQUIRED)

# Frozen deterministic weights (sums to 1.0). Model-assisted dimensions
# (CLARITY/EMOTIONAL_ARC/ORIGINALITY) are seeded with the deterministic
# signals available at B1 time; B3 wires model-assisted values through the
# same rubric without changing weights.
SCORE_DIMENSION_WEIGHTS: Dict[str, float] = {
    "AGE_FIT": 0.20,
    "SAFETY": 0.20,
    "BRIEF_ADHERENCE": 0.20,
    "DURATION_FIT": 0.15,
    "PRODUCTION_FEASIBILITY": 0.10,
    "CLARITY": 0.05,
    "EMOTIONAL_ARC": 0.05,
    "ORIGINALITY": 0.05,
}

SCORE_DIMENSIONS = tuple(SCORE_DIMENSION_WEIGHTS)

# Deterministic signal estimators (documented; replaced by model-assisted
# values when a real provider runs, never silently).
_AGE_BAND_OK = {"5-8": {"nguy hiểm", "bạo lực", "sợ hãi", "khủng bố"}}


def normalize_score(value: float) -> float:
    """Clamp a score into [0.0, 1.0] with 3-decimal rounding (deterministic)."""
    return round(max(0.0, min(1.0, float(value))), 3)


def score_dimension(
    *,
    brief: CreativeBrief,
    candidate: IdeaCandidate,
    dimension: str,
    model_value: Optional[float] = None,
) -> float:
    """Deterministic per-dimension score.

    ``model_value`` (model-assisted) overrides only the dimensions whose
    rubric is model-assisted; deterministic dimensions always use the
    deterministic estimator so scoring math stays testable.
    """
    if dimension == "SAFETY":
        return 1.0 if candidate.safety_ok else 0.0
    if dimension == "AGE_FIT":
        return normalize_score(candidate.age_fit)
    if dimension == "BRIEF_ADHERENCE":
        return normalize_score(candidate.brief_adherence)
    if dimension == "DURATION_FIT":
        # 1.0 inside [target-tol, target+tol], linear falloff to 0 at 50% off.
        target = float(brief.target_duration_seconds)
        tol = max(30.0, target * 0.15)
        estimated = float(candidate.content.get("estimated_seconds", target))
        if abs(estimated - target) <= tol:
            return 1.0
        deviation = abs(estimated - target)
        return normalize_score(max(0.0, 1.0 - (deviation - tol) / target))
    if dimension == "PRODUCTION_FEASIBILITY":
        # Deterministic signal: scene/character/location counts within bounds.
        scenes = int(candidate.content.get("scene_count", 5))
        characters = int(candidate.content.get("character_count", 2))
        locations = int(candidate.content.get("location_count", 2))
        ok = 1 <= scenes <= 12 and 1 <= characters <= 8 and 1 <= locations <= 8
        return 1.0 if ok else 0.5
    if dimension == "CLARITY":
        length = len(candidate.logline or candidate.summary)
        return normalize_score(min(1.0, max(0.3, length / 220.0)))
    if dimension == "EMOTIONAL_ARC":
        if model_value is not None:
            return normalize_score(model_value)
        return 0.6  # neutral seed; model-assisted in B3
    if dimension == "ORIGINALITY":
        if model_value is not None:
            return normalize_score(model_value)
        return 0.6  # neutral seed; model-assisted in B3
    raise KeyError(f"unknown score dimension {dimension!r}")


def _score_candidate(
    *,
    brief: CreativeBrief,
    candidate: IdeaCandidate,
    model_values: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    dims: Dict[str, float] = {}
    for dim in SCORE_DIMENSIONS:
        model_value = (model_values or {}).get(dim)
        dims[dim] = score_dimension(
            brief=brief, candidate=candidate, dimension=dim, model_value=model_value
        )
    return dims


def score_candidate_set(
    brief: CreativeBrief,
    candidate_set: IdeaCandidateSet,
    model_values: Optional[Dict[str, Dict[str, float]]] = None,
) -> IdeaCandidateSet:
    """Annotate every candidate with deterministic score dimensions.

    Never mutates the input set: returns a new immutable set (rule 4/7).
    """
    scored: List[IdeaCandidate] = []
    for candidate in candidate_set.candidates:
        dims = _score_candidate(
            brief=brief,
            candidate=candidate,
            model_values=(model_values or {}).get(candidate.candidate_id),
        )
        total = normalize_score(sum(dims[d] * SCORE_DIMENSION_WEIGHTS[d] for d in SCORE_DIMENSIONS))
        scored.append(
            candidate.model_copy(
                update={
                    "score_dimensions": dims,
                    "score": total,
                    "age_fit": dims["AGE_FIT"],
                    "brief_adherence": dims["BRIEF_ADHERENCE"],
                    "safety_ok": candidate.safety_ok and dims["SAFETY"] == 1.0,
                }
            )
        )
    recommended = tie_break_candidates(scored)
    return candidate_set.model_copy(
        update={
            "candidates": scored,
            "evaluated": True,
            "scoring_rubric_version": SCORE_RUBRIC_VERSION,
            "recommended_candidate_id": recommended.candidate_id if recommended else None,
        }
    )


def tie_break_candidates(candidates: List[IdeaCandidate]) -> Optional[IdeaCandidate]:
    """Deterministic tie-break: highest total, then highest AGE_FIT, then lexicographic ID."""
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (
            -float(c.score or 0.0),
            -float(c.score_dimensions.get("AGE_FIT", 0.0)),
            c.candidate_id,
        ),
    )


def selection_allowed(policy: str, candidate_set: IdeaCandidateSet) -> bool:
    """Whether automation MAY auto-select the recommendation under ``policy``.

    Fails closed: unknown policies and unevaluated/invalid sets never allow
    auto-selection (B3 rule: never silently select under human-required
    policy; an invalid set is never selectable). The actual selection command
    stays an A command bound to the set hash/revision.
    """
    if policy not in SELECTION_POLICIES:
        return False
    if policy == SELECTION_POLICY_HUMAN_REQUIRED:
        return False
    if not candidate_set.evaluated:
        return False
    if not candidate_set.recommended_candidate_id:
        return False
    return all(c.safety_ok for c in candidate_set.candidates)
