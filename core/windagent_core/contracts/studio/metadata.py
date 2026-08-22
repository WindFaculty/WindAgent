"""Studio series/episode presentation metadata authority (P0.4).

The frozen ``studio.command/v1`` commands carry a free-form ``metadata`` dict
which is persisted as-is today. P0 standardizes the presentation fields INSIDE
that existing metadata (per the P0.0.3 freeze decision): known keys are typed
and validated, unknown keys pass through untouched — no second command
contract, no breaking change to ``CreateSeriesCommand``/``CreateEpisodeCommand``.

Generation semantics (P0.4): once an episode leaves DRAFT, the fields that
feed story generation become immutable — editing them requires deriving a new
revision instead of silently mutating the context of an existing run.
"""

from __future__ import annotations

from typing import Any, Dict

from windagent_core.contracts.studio.errors import StudioValidationError

SERIES_METADATA_SCHEMA_VERSION = "studio.series-metadata/v1"
EPISODE_METADATA_SCHEMA_VERSION = "studio.episode-metadata/v1"

#: Known series presentation keys -> expected Python type (None allowed).
SERIES_METADATA_FIELDS: Dict[str, tuple[type, ...]] = {
    "target_audience": (str,),
    "language": (str,),
    "genre": (str,),
    "tone": (str,),
    "narrative_style": (str,),
    "content_constraints": (list, str),
    # AUTO | REQUIRE_HUMAN | CONDITIONAL (validated as string; policy values
    # are enforced by the approval-policy authority at run time).
    "approval_policy": (str,),
}

#: Known episode presentation keys -> expected Python type (None allowed).
EPISODE_METADATA_FIELDS: Dict[str, tuple[type, ...]] = {
    "logline": (str,),
    "creative_brief": (dict, str),
    "target_duration": (int, float, str),
    "target_audience": (str,),
    "episode_constraints": (list, str),
}

#: Episode metadata keys that feed story generation. Once the episode leaves
#: DRAFT these become immutable; a change must derive a new revision.
GENERATION_AFFECTING_EPISODE_FIELDS = frozenset(
    {
        "creative_brief",
        "logline",
        "target_duration",
        "target_audience",
        "episode_constraints",
    }
)

_APPROVAL_POLICIES = {"AUTO", "REQUIRE_HUMAN", "CONDITIONAL"}


def _validate_known_fields(
    metadata: Dict[str, Any],
    schema: Dict[str, tuple[type, ...]],
    *,
    label: str,
) -> None:
    for key, value in metadata.items():
        if key not in schema or value is None:
            continue
        expected = schema[key]
        if isinstance(value, bool) and int in expected and bool not in expected:
            raise StudioValidationError(
                f"{label} metadata field {key!r} must be numeric, got boolean.",
                details={"field": key, "expected": "int|float", "got": "bool"},
            )
        if not isinstance(value, expected):
            raise StudioValidationError(
                f"{label} metadata field {key!r} has invalid type "
                f"{type(value).__name__}.",
                details={
                    "field": key,
                    "expected": "|".join(t.__name__ for t in expected),
                    "got": type(value).__name__,
                },
            )
        if key == "approval_policy" and str(value).strip().upper() not in _APPROVAL_POLICIES:
            raise StudioValidationError(
                f"{label} metadata field 'approval_policy' must be one of "
                f"{sorted(_APPROVAL_POLICIES)}.",
                details={"field": "approval_policy", "got": str(value)[:64]},
            )


def validate_series_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Validate known series presentation keys; unknown keys pass through."""
    _validate_known_fields(metadata or {}, SERIES_METADATA_FIELDS, label="Series")
    return dict(metadata or {})


def validate_episode_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Validate known episode presentation keys; unknown keys pass through."""
    _validate_known_fields(metadata or {}, EPISODE_METADATA_FIELDS, label="Episode")
    return dict(metadata or {})


def immutable_field_conflict(
    patch: Dict[str, Any], current_metadata: Dict[str, Any]
) -> list[str]:
    """Generation-affecting keys whose value would actually change.

    Only REAL changes conflict: resubmitting an identical value is a no-op,
    not a mutation.
    """
    conflicts: list[str] = []
    for key in patch:
        if key not in GENERATION_AFFECTING_EPISODE_FIELDS:
            continue
        if patch[key] != current_metadata.get(key):
            conflicts.append(key)
    return sorted(conflicts)


__all__ = [
    "SERIES_METADATA_SCHEMA_VERSION",
    "EPISODE_METADATA_SCHEMA_VERSION",
    "SERIES_METADATA_FIELDS",
    "EPISODE_METADATA_FIELDS",
    "GENERATION_AFFECTING_EPISODE_FIELDS",
    "validate_series_metadata",
    "validate_episode_metadata",
    "immutable_field_conflict",
]
