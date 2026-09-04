"""Immutable production revision and derivation service."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import (
    StudioArtifactHashMismatchError,
    StudioLockedRevisionError,
    StudioStaleRevisionError,
    StudioValidationError,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class RevisionStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    LOCKED = "LOCKED"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class LockState(StrEnum):
    UNLOCKED = "UNLOCKED"
    LOCKED = "LOCKED"


class InvalidationIntent(StrEnum):
    NONE = "NONE"
    DOWNSTREAM = "DOWNSTREAM"


def canonical_content_hash(*, content: Any, schema_version: str = "studio.artifact/v1alpha1") -> str:
    payload = {"schema_version": schema_version, "content": content}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ProductionRevision(BaseModel):
    """Immutable revision of an Episode's story content."""

    model_config = ConfigDict(frozen=True, extra="allow")

    revision_id: str = Field(min_length=1)
    series_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    parent_revision_id: str | None = None
    creator: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    content_hash: str = Field(min_length=64, max_length=64)
    status: RevisionStatus = RevisionStatus.DRAFT
    lock_state: LockState = LockState.UNLOCKED
    invalidation_intent: InvalidationIntent | None = None
    summary: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)
    optimistic_version: int = Field(default=0, ge=0)

    @field_validator("creator", "actor")
    @classmethod
    def _actor_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Revision creator/actor cannot be blank.")
        return v.strip()

    @property
    def locked(self) -> bool:
        return self.lock_state == LockState.LOCKED


class RevisionService:
    """Domain service enforcing immutability, stale-write, and lock rules."""

    @staticmethod
    def derive_revision(
        *,
        parent: ProductionRevision,
        series_id: str,
        episode_id: str,
        new_content_hash: str,
        creator: str,
        actor: str | None = None,
        invalidation_intent: InvalidationIntent | None = None,
        summary: str = "",
        expected_parent_version: int | None = None,
    ) -> ProductionRevision:
        if expected_parent_version is not None and parent.optimistic_version != expected_parent_version:
            raise StudioStaleRevisionError(
                "Cannot derive from a stale parent revision.",
                context={
                    "parent_revision_id": parent.revision_id,
                    "expected_version": expected_parent_version,
                    "current_version": parent.optimistic_version,
                },
            )
        if parent.locked and invalidation_intent in (None, InvalidationIntent.NONE):
            raise StudioLockedRevisionError(
                "Cannot mutate a locked revision; pass an explicit invalidation intent to derive a new revision.",
                context={"parent_revision_id": parent.revision_id},
            )
        if len(new_content_hash) != 64:
            raise StudioValidationError("new_content_hash must be a 64-char SHA-256 hex digest.")
        derived_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{parent.revision_id}|{new_content_hash}"))
        return ProductionRevision(
            revision_id=derived_id,
            series_id=series_id,
            episode_id=episode_id,
            parent_revision_id=parent.revision_id,
            creator=creator,
            actor=actor or creator,
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
            raise StudioStaleRevisionError(
                "Cannot lock a stale revision.",
                context={
                    "revision_id": revision.revision_id,
                    "expected_version": expected_version,
                    "current_version": revision.optimistic_version,
                },
            )
        if expected_content_hash is not None and expected_content_hash != revision.content_hash:
            raise StudioArtifactHashMismatchError(
                "Lock hash does not match the canonical revision content hash.",
                context={
                    "revision_id": revision.revision_id,
                    "expected_hash": expected_content_hash,
                    "canonical_hash": revision.content_hash,
                },
            )
        if revision.locked and revision.status == RevisionStatus.LOCKED:
            return revision
        return revision.model_copy(
            update={
                "lock_state": LockState.LOCKED,
                "status": RevisionStatus.LOCKED,
                "optimistic_version": revision.optimistic_version + 1,
            }
        )

    @staticmethod
    def record_stale_write_guard(
        *,
        revision: ProductionRevision,
        expected_content_hash: str | None = None,
        expected_version: int | None = None,
    ) -> None:
        if expected_version is not None and revision.optimistic_version != expected_version:
            raise StudioStaleRevisionError(
                "Write guard failed: revision version is stale.",
                context={
                    "revision_id": revision.revision_id,
                    "expected_version": expected_version,
                    "current_version": revision.optimistic_version,
                },
            )
        if expected_content_hash is not None and expected_content_hash != revision.content_hash:
            raise StudioArtifactHashMismatchError(
                "Write guard failed: content hash is stale.",
                context={
                    "revision_id": revision.revision_id,
                    "expected_hash": expected_content_hash,
                    "canonical_hash": revision.content_hash,
                },
            )


__all__ = [
    "InvalidationIntent",
    "LockState",
    "ProductionRevision",
    "RevisionService",
    "RevisionStatus",
    "canonical_content_hash",
    "utc_now",
]

