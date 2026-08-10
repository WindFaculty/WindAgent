"""
Compatibility adapters between legacy video-production content models and
canonical Story models (Plan B B1; B0 reuse decisions REUSE/WRAP).

Conversion is explicit and loss-reporting: nothing is silently dropped.
"""

from __future__ import annotations

from typing import Any, Dict

from windagent_core.domain.story.ideation.models import (
    CreativeBrief,
    IdeaCandidate,
)
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief as VideoCreativeBrief,
)

__all__ = [
    "from_video_brief",
    "brief_normalization_loss",
    "project_to_video_concept",
]

# Fields the legacy brief carries that canonical normalization keeps verbatim.
_LEGACY_TO_CANONICAL_FIELDS = (
    "title", "genre", "logline", "tone", "audience",
    "target_duration_seconds", "aspect_ratio",
)


def from_video_brief(video_brief: VideoCreativeBrief) -> CreativeBrief:
    """Normalize a legacy CreativeBrief into the canonical model.

    Legacy fields map losslessly; the canonical additions
    (language, audience band, theme, constraints, prohibited_content) default
    to neutral values and are refined by B3 generation.
    """
    data: Dict[str, Any] = {f: getattr(video_brief, f) for f in _LEGACY_TO_CANONICAL_FIELDS}
    data["brief_id"] = video_brief.brief_id
    data["production_constraints"] = dict(video_brief.production_constraints)
    return CreativeBrief(**data)


def brief_normalization_loss(video_brief: VideoCreativeBrief) -> Dict[str, Any]:
    """Document what normalization cannot infer from the legacy shape."""
    return {
        "language": "defaulted to 'vi' (legacy brief has no language field)",
        "audience_min_age/audience_max_age": "defaulted 0-99; parse 'audience' in B3",
        "theme": "empty until B3 normalization",
        "constraints/prohibited_content": "empty until B3 normalization",
        "brief_id": str(video_brief.brief_id),
    }


def project_to_video_concept(
    candidate: IdeaCandidate,
    loss: Dict[str, Any] | None = None,
) -> Any:
    """Project a canonical candidate onto the legacy StoryConcept (explicit loss)."""
    concept, projected_loss = candidate.to_story_concept()
    if loss is not None:
        loss.update(projected_loss)
    return concept
