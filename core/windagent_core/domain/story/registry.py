"""
Canonical Story artifact registry (frozen location: B0 registry freeze §1).

Maps the frozen ``ArtifactType`` discriminator (A-owned enum) to the B-owned
content model, its validation codes, and its presentation summary. Exactly one
canonical content model per artifact type — the duplicate-model checker
(``find_duplicate_canonical_models``) enforces that invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Type

from pydantic import BaseModel

from windagent_core.domain.story.bibles.models import CharacterCanon, StoryBible, WorldBible
from windagent_core.domain.story.bibles.validators import (
    validate_character_canon,
    validate_story_bible,
    validate_world_bible,
)
from windagent_core.domain.story.canonical import StoryContent
from windagent_core.domain.story.ideation.models import (
    CreativeBrief,
    IdeaCandidateSet,
    SelectedIdea,
)
from windagent_core.domain.story.ideation.validators import (
    validate_creative_brief,
    validate_idea_candidate_set,
    validate_selected_idea,
)
from windagent_core.domain.story.outline.models import BeatSheet, EpisodeOutline
from windagent_core.domain.story.outline.validators import (
    validate_beat_sheet,
    validate_episode_outline,
)
from windagent_core.domain.story.review.models import (
    LockedScreenplayPackage,
    LockedScreenplayReceipt,
    ReviewReport,
    RevisionProposal,
    StoryDiff,
)
from windagent_core.domain.story.review.validators import (
    validate_locked_package,
    validate_review_report,
    validate_revision_proposal,
)
from windagent_core.domain.story.screenplay.models import ScreenplayDraft
from windagent_core.domain.story.screenplay.validators import validate_screenplay_draft
from windagent_core.domain.story.validation import ValidationReport
from windagent_core.domain.studio.artifact import ArtifactType

__all__ = [
    "StoryArtifactRegistration",
    "STORY_ARTIFACT_REGISTRY",
    "find_duplicate_canonical_models",
    "registered_artifact_types",
    "content_model_for",
    "deserialize_story_artifact",
]


@dataclass(frozen=True)
class StoryArtifactRegistration:
    """One registry entry: artifact type -> content model + metadata."""

    artifact_type: ArtifactType
    content_model: Type[StoryContent]
    validation_codes: tuple[str, ...] = ()
    description: str = ""
    #: Single-argument deterministic validator (context-free structural checks).
    #: Cross-artifact contextual checks (canon/beat_sheet) live in the family
    #: validators and are exercised by unit + contract tests.
    validator: Optional[Callable[[StoryContent], ValidationReport]] = None

    @property
    def schema_name(self) -> str:
        return self.content_model.__name__


#: Frozen registry: exactly one entry per frozen Story artifact type.
STORY_ARTIFACT_REGISTRY: Dict[ArtifactType, StoryArtifactRegistration] = {
    ArtifactType.CREATIVE_BRIEF: StoryArtifactRegistration(
        ArtifactType.CREATIVE_BRIEF, CreativeBrief,
        validation_codes=("FIELD_EMPTY", "SAFETY_PROHIBITED"),
        description="Normalized creative direction (B3).",
        validator=validate_creative_brief,
    ),
    ArtifactType.IDEA_CANDIDATE_SET: StoryArtifactRegistration(
        ArtifactType.IDEA_CANDIDATE_SET, IdeaCandidateSet,
        validation_codes=(
            "IDEA_COUNT", "IDEA_DUPLICATE", "IDEA_REQUIRED_FIELD",
            "SAFETY_PROHIBITED", "SAFETY_AGE_UNSUITABLE",
        ),
        description="3-5 distinct scored idea candidates (B3).",
        validator=validate_idea_candidate_set,
    ),
    ArtifactType.SELECTED_IDEA: StoryArtifactRegistration(
        ArtifactType.SELECTED_IDEA, SelectedIdea,
        validation_codes=("REF_MISSING", "FIELD_EMPTY"),
        description="Hash-bound selected idea (selection is an A command).",
        validator=validate_selected_idea,
    ),
    ArtifactType.STORY_BIBLE: StoryArtifactRegistration(
        ArtifactType.STORY_BIBLE, StoryBible,
        validation_codes=("FIELD_EMPTY", "FIELD_TOO_LONG"),
        description="Premise/theme/tone/arc/stakes/rules (S6).",
        validator=validate_story_bible,
    ),
    ArtifactType.WORLD_BIBLE: StoryArtifactRegistration(
        ArtifactType.WORLD_BIBLE, WorldBible,
        validation_codes=("ID_UNIQUE", "WORLD_RULE_COMPLIANCE", "FIELD_EMPTY"),
        description="Setting, rules, recurring locations/objects (S6).",
        validator=validate_world_bible,
    ),
    ArtifactType.CHARACTER_CANON: StoryArtifactRegistration(
        ArtifactType.CHARACTER_CANON, CharacterCanon,
        validation_codes=(
            "ID_UNIQUE", "DUPLICATE_NAME", "REF_MISSING",
            "RELATIONSHIP_CYCLE", "UNKNOWN_REF_KIND", "FIELD_EMPTY",
        ),
        description="Stable-ID character canon with relationships (S6).",
        validator=validate_character_canon,
    ),
    ArtifactType.BEAT_SHEET: StoryArtifactRegistration(
        ArtifactType.BEAT_SHEET, BeatSheet,
        validation_codes=("ORDER_SEQUENCE", "ID_UNIQUE", "DURATION_SUM", "REF_MISSING"),
        description="Ordered beats with target-seconds allocation (S7).",
        validator=validate_beat_sheet,
    ),
    ArtifactType.EPISODE_OUTLINE: StoryArtifactRegistration(
        ArtifactType.EPISODE_OUTLINE, EpisodeOutline,
        validation_codes=(
            "ORDER_SEQUENCE", "ID_UNIQUE", "DURATION_SUM", "DURATION_BOUND",
            "BEAT_ORPHAN", "SCENE_ORPHAN", "CAUSAL_ORDER", "REF_MISSING",
        ),
        description="Production-aware scenes fitting 180-300 s (S7).",
        validator=validate_episode_outline,
    ),
    ArtifactType.SCREENPLAY_DRAFT: StoryArtifactRegistration(
        ArtifactType.SCREENPLAY_DRAFT, ScreenplayDraft,
        validation_codes=(
            "ID_UNIQUE", "ORDER_SEQUENCE", "DIALOGUE_ATTRIBUTION",
            "DIALOGUE_EMPTY", "BEAT_COVERAGE", "DURATION_SUM",
            "DURATION_BOUND", "REF_MISSING", "FIELD_EMPTY",
        ),
        description="Authoritative structured screenplay draft (S8).",
        validator=validate_screenplay_draft,
    ),
    ArtifactType.REVIEW_REPORT: StoryArtifactRegistration(
        ArtifactType.REVIEW_REPORT, ReviewReport,
        validation_codes=("REVIEW_VERDICT", "REVISION_BUDGET"),
        description="Aggregated review findings + verdict (S9).",
        validator=validate_review_report,
    ),
    ArtifactType.REVISION_PROPOSAL: StoryArtifactRegistration(
        ArtifactType.REVISION_PROPOSAL, RevisionProposal,
        validation_codes=("REVISION_STALE", "REVISION_BUDGET"),
        description="Bounded revision request (S9).",
        validator=validate_revision_proposal,
    ),
    ArtifactType.LOCKED_SCREENPLAY_RECEIPT: StoryArtifactRegistration(
        ArtifactType.LOCKED_SCREENPLAY_RECEIPT, LockedScreenplayReceipt,
        validation_codes=("LOCK_STATE",),
        description="A-issued READY_FOR_PRODUCTION receipt (S10).",
        validator=None,
    ),
    ArtifactType.LOCKED_SCREENPLAY_PACKAGE: StoryArtifactRegistration(
        ArtifactType.LOCKED_SCREENPLAY_PACKAGE, LockedScreenplayPackage,
        validation_codes=(
            "MANIFEST_MISSING_REF", "MANIFEST_HASH", "MANIFEST_DUPLICATE",
            "LOCK_STATE", "REF_MISSING",
        ),
        description="Immutable lock-ready package with lineage manifest (S10).",
        validator=validate_locked_package,
    ),
}

#: Diff artifacts are B-owned content but not frozen task I/O types; they are
#: consumed inside review/revise results, not registered as standalone
#: envelope artifacts.
STORY_SUPPLEMENTARY_MODELS: Dict[str, Type[StoryContent]] = {
    "StoryDiff": StoryDiff,
}


def registered_artifact_types() -> List[ArtifactType]:
    return list(STORY_ARTIFACT_REGISTRY)


def content_model_for(artifact_type: ArtifactType) -> Type[StoryContent]:
    try:
        return STORY_ARTIFACT_REGISTRY[artifact_type].content_model
    except KeyError as exc:
        raise KeyError(f"no canonical content model registered for {artifact_type!r}") from exc


def find_duplicate_canonical_models() -> List[str]:
    """Return schema names registered more than once (must stay empty).

    Duplicate canonical models are a contract violation: C generates exactly
    one TypeScript type per frozen artifact type.
    """
    counts: Dict[str, int] = {}
    for registration in STORY_ARTIFACT_REGISTRY.values():
        counts[registration.schema_name] = counts.get(registration.schema_name, 0) + 1
    return sorted(name for name, count in counts.items() if count > 1)


def deserialize_story_artifact(artifact_type: ArtifactType, raw: str) -> StoryContent:
    """Parse canonical JSON into the registered content model (fail closed)."""
    model = content_model_for(artifact_type)
    return model.deserialize(raw)
