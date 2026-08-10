"""Plan B narrative-structure content models and deterministic validators (S7)."""

from windagent_core.domain.story.outline.duration import (
    DEFAULT_CHARS_PER_SECOND,
    DEFAULT_TOLERANCE_SECONDS,
    DURATION_FORMULA_VERSION,
    MAX_EPISODE_SECONDS,
    MIN_EPISODE_SECONDS,
    TRANSITION_BUDGET_SECONDS,
    duration_issues,
    estimate_scene_seconds,
    estimate_text_seconds,
)
from windagent_core.domain.story.outline.models import (
    BEAT_ROLES,
    Beat,
    BeatSheet,
    EpisodeOutline,
    OutlineScene,
)
from windagent_core.domain.story.outline.validators import (
    validate_beat_sheet,
    validate_episode_outline,
)

__all__ = [
    "Beat",
    "BeatSheet",
    "OutlineScene",
    "EpisodeOutline",
    "BEAT_ROLES",
    "DURATION_FORMULA_VERSION",
    "MIN_EPISODE_SECONDS",
    "MAX_EPISODE_SECONDS",
    "DEFAULT_TOLERANCE_SECONDS",
    "DEFAULT_CHARS_PER_SECOND",
    "TRANSITION_BUDGET_SECONDS",
    "estimate_text_seconds",
    "estimate_scene_seconds",
    "duration_issues",
    "validate_beat_sheet",
    "validate_episode_outline",
]
