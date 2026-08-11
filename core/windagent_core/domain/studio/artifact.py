"""
Canonical Story artifact envelope (studio.contract/v0.1).

Ownership: Plan A owns the envelope, identity, hash, repository, and lock
invariants; Plan B owns content schemas; Plan C consumes schemas and never
redefines them in TypeScript. Every artifact is immutable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
)
from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_core.domain.studio.revision import canonical_content_hash

ARTIFACT_SCHEMA_VERSION = "studio.artifact/v1alpha1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactType(str, Enum):
    CREATIVE_BRIEF = "CreativeBrief"
    IDEA_CANDIDATE_SET = "IdeaCandidateSet"
    SELECTED_IDEA = "SelectedIdea"
    STORY_BIBLE = "StoryBible"
    WORLD_BIBLE = "WorldBible"
    CHARACTER_CANON = "CharacterCanon"
    BEAT_SHEET = "BeatSheet"
    EPISODE_OUTLINE = "EpisodeOutline"
    SCREENPLAY_DRAFT = "ScreenplayDraft"
    REVIEW_REPORT = "ReviewReport"
    REVISION_PROPOSAL = "RevisionProposal"
    LOCKED_SCREENPLAY_RECEIPT = "LockedScreenplayReceipt"
    LOCKED_SCREENPLAY_PACKAGE = "LockedScreenplayPackage"


class StoryArtifactEnvelope(BaseModel):
    """Immutable content-addressed envelope for every Story artifact."""

    model_config = ConfigDict(frozen=True, extra="allow")

    artifact_id: ArtifactId
    artifact_type: ArtifactType
    schema_version: str = ARTIFACT_SCHEMA_VERSION
    series_id: SeriesProjectId
    episode_id: EpisodeId
    revision_id: Optional[ProductionRevisionId] = None
    content_hash: str = Field(min_length=64, max_length=64)
    input_artifact_refs: List[ArtifactId] = Field(default_factory=list)
    prompt_id: Optional[str] = None
    prompt_version: Optional[str] = None
    prompt_hash: Optional[str] = None
    model_route_id: Optional[str] = None
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    canonical_model_id: Optional[str] = None
    provider_model_id: Optional[str] = None
    endpoint_id: Optional[str] = None
    provider_binding_id: Optional[str] = None
    provider_attempt_id: Optional[str] = None
    provider_request_id: Optional[str] = None
    output_schema_contract: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = Field(default_factory=lambda: "system")
    content: Any = Field(default_factory=dict)

    @field_validator("content_hash")
    @classmethod
    def _validate_hash(cls, v: str) -> str:
        if len(v) != 64:
            raise StudioValidationError("content_hash must be a 64-char SHA-256 hex digest.")
        return v

    @classmethod
    def build(
        cls,
        *,
        artifact_type: ArtifactType,
        series_id: SeriesProjectId,
        episode_id: EpisodeId,
        content: Any,
        revision_id: Optional[ProductionRevisionId] = None,
        input_artifact_refs: Optional[List[ArtifactId]] = None,
        created_by: str = "system",
        **metadata: Any,
    ) -> StoryArtifactEnvelope:
        """Build an envelope and derive its content-addressed identity/hash."""
        content_hash = canonical_content_hash(content=content, schema_version=ARTIFACT_SCHEMA_VERSION)
        return cls(
            artifact_id=ArtifactId.generate("art"),
            artifact_type=artifact_type,
            schema_version=ARTIFACT_SCHEMA_VERSION,
            series_id=series_id,
            episode_id=episode_id,
            revision_id=revision_id,
            content_hash=content_hash,
            input_artifact_refs=input_artifact_refs or [],
            created_by=created_by,
            content=content,
            **metadata,
        )

    def is_detached(self) -> bool:
        """True when the content hash is self-authored, not pre-supplied."""
        return self.content_hash == canonical_content_hash(
            content=self.content, schema_version=self.schema_version
        )


# ---------------------------------------------------------------------------
# Plan B canonical content aliases (B1)
# ---------------------------------------------------------------------------
# The canonical content models live in `windagent_core.domain.story` (Plan B).
# This A-owned envelope module re-exports them so envelope consumers keep one
# stable import path. Exactly one canonical model exists per artifact type
# (enforced by the duplicate-canonical-model checker). The import is placed
# here (after the envelope class) to avoid an import-time cycle: the B
# registry imports `ArtifactType` from this module.
from windagent_core.domain.story.ideation.models import (  # noqa: E402
    IdeaCandidate,
    IdeaCandidateSet,
)

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "utc_now",
    "ArtifactType",
    "IdeaCandidate",
    "IdeaCandidateSet",
    "StoryArtifactEnvelope",
]
