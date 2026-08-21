"""Deterministic CreativeBrief normalization (Plan B B3 step 1).

Turns a raw/legacy brief into the canonical normalized shape: audience band
parsed from the ``audience`` string, language default, theme, constraints, and
age-band default prohibited content. Pure domain logic — no provider, no I/O;
everything is deterministic and testable (cross-cutting rule 5).

Normalization is immutable: it always returns a NEW ``CreativeBrief``; the
input is never mutated.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from windagent_core.domain.story.ideation.models import (
    CreativeBrief,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "AGE_BAND_DEFAULT_PROHIBITED",
    "parse_audience_band",
    "normalize_creative_brief",
]

DEFAULT_LANGUAGE = "vi"

#: Deterministic age-band default prohibited content (documented rubric).
#: Explicit ``prohibited_content`` on the brief is UNIONED with these; the
#: safe direction is to over-restrict for young audiences, never relax.
AGE_BAND_DEFAULT_PROHIBITED: Dict[str, List[str]] = {
    "0-8": ["bạo lực", "khủng bố", "sợ hãi"],
    "9-13": ["khủng bố", "bạo lực tả thực"],
    "14-99": [],
}

_AUDIENCE_BAND_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")


def parse_audience_band(audience: str) -> Optional[Tuple[int, int]]:
    """Parse an ``"<min>-<max>"`` audience string (e.g. ``"5-8"``).

    Returns ``None`` when the string is not a strict ``int-int`` band; the
    caller keeps the current ages instead of guessing (never silently
    accept malformed input).
    """
    if not audience or not audience.strip():
        return None
    match = _AUDIENCE_BAND_RE.match(audience)
    if match is None:
        return None
    low, high = int(match.group(1)), int(match.group(2))
    if low > high:
        return None
    return low, high


def _band_key(max_age: int) -> str:
    # Conservative: use the strictest band that contains the declared max age.
    if max_age <= 8:
        return "0-8"
    if max_age <= 13:
        return "9-13"
    return "14-99"


def normalize_creative_brief(
    brief: CreativeBrief,
    *,
    language: Optional[str] = None,
    theme: Optional[str] = None,
    constraints: Optional[List[str]] = None,
    prohibited_content: Optional[List[str]] = None,
    audience_band: Optional[str] = None,
) -> CreativeBrief:
    """Return a normalized copy of ``brief`` with every B3 field resolved.

    Resolution order (documented): explicit keyword argument wins, then the
    brief's own field, then the deterministic default. The returned
    ``normalization_report`` (as ``metadata`` entry) records what was
    inferred so callers can audit normalization decisions.

    - ``audience`` band: parsed into ``audience_min_age``/``audience_max_age``
      when ``audience_band`` is not given explicitly.
    - ``language``: default ``"vi"``.
    - ``prohibited_content``: union of the given list and the age-band
      defaults for the resolved band (deduped, order-preserving).
    """
    band = audience_band if audience_band is not None else brief.audience
    parsed = parse_audience_band(band) if band else None
    min_age = parsed[0] if parsed is not None else brief.audience_min_age
    max_age = parsed[1] if parsed is not None else brief.audience_max_age

    resolved_language = language if language is not None else (brief.language or DEFAULT_LANGUAGE)
    resolved_theme = theme if theme is not None else brief.theme

    given_prohibited = list(
        prohibited_content if prohibited_content is not None else brief.prohibited_content
    )
    band_defaults = list(AGE_BAND_DEFAULT_PROHIBITED[_band_key(max_age)])
    merged_prohibited: List[str] = []
    for term in band_defaults + given_prohibited:
        if term and term not in merged_prohibited:
            merged_prohibited.append(term)

    resolved_constraints = list(constraints if constraints is not None else brief.constraints)

    report = {
        "normalization_version": "brief_normalization/v1",
        "audience_band_parsed": band if parsed is not None else None,
        "audience_band_kept": parsed is None,
        "language": resolved_language,
        "theme": resolved_theme,
        "prohibited_merged": merged_prohibited,
        "prohibited_from_age_band": band_defaults,
    }

    metadata = dict(brief.production_constraints)
    metadata["normalization_report"] = report
    return brief.model_copy(
        update={
            "language": resolved_language,
            "theme": resolved_theme,
            "audience": band if band is not None else brief.audience,
            "audience_min_age": min_age,
            "audience_max_age": max_age,
            "constraints": resolved_constraints,
            "prohibited_content": merged_prohibited,
            "production_constraints": metadata,
        }
    )
