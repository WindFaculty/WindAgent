"""Production video project aggregate and immutable revision (Phase 16).

Ported semantics from ``core/domain/video_production/project.py`` and
``core/domain/video_production/production_ir``: every revision carries
``revision_id``, ``parent_revision_id``, ``content_hash`` and ``locked``,
screenplay changes declare an ``InvalidationIntent``, approvals point at a
specific revision + hash, and locked artifacts cannot be mutated without
deriving a new revision.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import (
    ProductionArtifactHashMismatchError,
    ProductionLockedRevisionError,
    ProductionStaleRevisionError,
    ProductionValidationError,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    PRODUCTION = "PRODUCTION"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class RevisionStatus(StrEnum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class InvalidationIntent(StrEnum):
    NONE = "NONE"
    INVALIDATE_SHOT_PLAN = "INVALIDATE_SHOT_PLAN"
    INVALIDATE_GENERATION = "INVALIDATE_GENERATION"
    INVALIDATE_ASSETS = "INVALIDATE_ASSETS"
    INVALIDATE_ALL = "INVALIDATE_ALL"


def canonical_content_hash(*, content: Any, schema_version: str = "production.artifact/v1") -> str:
    payload = {"schema_version": schema_version, "content": content}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class VideoProject(BaseModel):
    """Top-level aggregate owning revisions."""

    model_config = ConfigDict(frozen=True, extra="allow")

    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(default="")
    owner_id: str = Field(default="system")
    status: ProjectStatus = ProjectStatus.DRAFT
    current_revision_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ProductionValidationError("VideoProject title cannot be blank.")
        return v.strip()

    def rename(self, title: str, *, expected_version: int | None = None) -> VideoProject:
        if expected_version is not None and expected_version != self.optimistic_version:
            raise ProductionStaleRevisionError(
                "Project version mismatch.",
                context={
                    "project_id": self.project_id,
                    "expected_version": expected_version,
                    "current_version": self.optimistic_version,
                },
            )
        normalized = title.strip()
        if not normalized:
            raise ProductionValidationError("Project title cannot be blank.")
        if normalized == self.title:
            return self
        return self.model_copy(
            update={"title": normalized, "updated_at": utc_now(), "optimistic_version": self.optimistic_version + 1}
        )


class ProductionRevision(BaseModel):
    """Immutable revision of a VideoProject (content-addressed)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    revision_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    parent_revision_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    creator: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    status: RevisionStatus = RevisionStatus.DRAFT
    locked: bool = False
    invalidation_intent: InvalidationIntent | None = None
    summary: str = Field(default="")
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("creator", "actor")
    @classmethod
    def _actor_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ProductionValidationError("ProductionRevision creator/actor cannot be blank.")
        return v.strip()

    @property
    def is_locked(self) -> bool:
        return self.locked or self.status == RevisionStatus.LOCKED


class RevisionService:
    """Domain service enforcing immutability, stale-write, and lock rules."""

    @staticmethod
    def derive_revision(
        *,
        parent: ProductionRevision,
        project_id: str,
        new_content_hash: str,
        created_by: str,
        actor: str | None = None,
        invalidation_intent: InvalidationIntent | None = None,
        summary: str = "",
        expected_parent_version: int | None = None,
    ) -> ProductionRevision:
        if expected_parent_version is not None and parent.optimistic_version != expected_parent_version:
            raise ProductionStaleRevisionError(
                "Cannot derive from a stale parent revision.",
                context={
                    "parent_revision_id": parent.revision_id,
                    "expected_version": expected_parent_version,
                    "current_version": parent.optimistic_version,
                },
            )
        if parent.is_locked and invalidation_intent in (None, InvalidationIntent.NONE):
            raise ProductionLockedRevisionError(
                "Cannot mutate locked revision without an explicit downstream invalidation intent.",
                context={"revision_id": parent.revision_id, "project_id": project_id},
            )
        if len(new_content_hash) != 64:
            raise ProductionValidationError("new_content_hash must be a 64-char SHA-256 hex digest.")
        derived_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{parent.revision_id}|{new_content_hash}"))
        return ProductionRevision(
            revision_id=derived_id,
            project_id=project_id,
            parent_revision_id=parent.revision_id,
            creator=created_by,
            actor=actor or created_by,
            content_hash=new_content_hash,
            invalidation_intent=invalidation_intent,
            summary=summary,
        )

    @staticmethod
    def lock_revision(
        *,
        revision: ProductionRevision,
        expected_content_hash: str | None = None,
        expected_version: int | None = None,
    ) -> ProductionRevision:
        if expected_version is not None and revision.optimistic_version != expected_version:
            raise ProductionStaleRevisionError(
                "Cannot lock a stale revision.",
                context={
                    "revision_id": revision.revision_id,
                    "expected_version": expected_version,
                    "current_version": revision.optimistic_version,
                },
            )
        if expected_content_hash is not None and expected_content_hash != revision.content_hash:
            raise ProductionArtifactHashMismatchError(
                "Lock hash does not match canonical content hash.",
                context={
                    "revision_id": revision.revision_id,
                    "expected_hash": expected_content_hash,
                    "canonical_hash": revision.content_hash,
                },
            )
        if revision.is_locked and revision.status == RevisionStatus.LOCKED:
            return revision
        return revision.model_copy(
            update={"locked": True, "status": RevisionStatus.LOCKED, "optimistic_version": revision.optimistic_version + 1}
        )


__all__ = [
    "InvalidationIntent",
    "ProductionRevision",
    "ProjectStatus",
    "RevisionService",
    "RevisionStatus",
    "VideoProject",
    "canonical_content_hash",
    "utc_now",
]
