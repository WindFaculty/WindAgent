"""Content-addressed artifact envelope (studio.artifact/v1alpha1).

Ownership mirrors the frozen boundary: Plan A (Studio) owns envelope,
identity, hash, and lock invariants; content schemas are owned under
``story/``; the API never re-introduces them in TypeScript.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import StudioValidationError

ARTIFACT_SCHEMA_VERSION = "studio.artifact/v1alpha1"


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_content_hash(*, content: Any, schema_version: str = ARTIFACT_SCHEMA_VERSION) -> str:
    payload = {"schema_version": schema_version, "content": content}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ArtifactType(StrEnum):
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
    STORYBOARD = "Storyboard"


class StoryArtifactEnvelope(BaseModel):
    """Immutable content-addressed envelope for every Story artifact."""

    model_config = ConfigDict(frozen=True, extra="allow")

    artifact_id: str = Field(min_length=1)
    artifact_type: ArtifactType
    schema_version: str = ARTIFACT_SCHEMA_VERSION
    series_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    revision_id: str | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    input_artifact_refs: tuple[str, ...] = Field(default_factory=tuple)
    prompt_id: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    model_route_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    canonical_model_id: str | None = None
    provider_model_id: str | None = None
    output_schema_contract: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = Field(default="system", min_length=1)
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
        series_id: str,
        episode_id: str,
        content: Any,
        revision_id: str | None = None,
        input_artifact_refs: tuple[str, ...] | None = None,
        created_by: str = "system",
        artifact_id: str | None = None,
        **metadata: Any,
    ) -> StoryArtifactEnvelope:
        content_hash = canonical_content_hash(content=content, schema_version=ARTIFACT_SCHEMA_VERSION)
        resolved_id = artifact_id or str(uuid.uuid4())
        return cls(
            artifact_id=resolved_id,
            artifact_type=artifact_type,
            schema_version=ARTIFACT_SCHEMA_VERSION,
            series_id=series_id,
            episode_id=episode_id,
            revision_id=revision_id,
            content_hash=content_hash,
            input_artifact_refs=input_artifact_refs or (),
            created_by=created_by,
            content=content,
            **metadata,
        )

    def is_detached(self) -> bool:
        return self.content_hash == canonical_content_hash(
            content=self.content, schema_version=self.schema_version
        )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ArtifactType",
    "StoryArtifactEnvelope",
    "canonical_content_hash",
    "utc_now",
]

