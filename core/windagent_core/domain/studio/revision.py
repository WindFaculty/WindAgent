"""
Canonical Studio production revision and derivation service (studio.contract/v0.1).

``StudioProductionRevision`` is the immutable revision in the canonical
``SeriesProject -> Episode -> ProductionRevision`` hierarchy. It reuses the
existing ``ProductionRevisionId`` type and parent/hash semantics while adding
series/episode association, lock state, invalidation intent, and an optimistic
version for stale-write protection.

Migration-compatible alias: ``ProductionRevision = StudioProductionRevision`` for
new Studio code; the legacy ``windagent_core.domain.video_production.production_revision``
aggregate remains the V2 read facade.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.contracts.studio.ids import (
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
)
from windagent_core.contracts.studio.errors import (
    StudioArtifactHashMismatchError,
    StudioLockedRevisionError,
    StudioStaleRevisionError,
    StudioValidationError,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StudioRevisionStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    LOCKED = "LOCKED"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class StudioLockState(str, Enum):
    UNLOCKED = "UNLOCKED"
    LOCKED = "LOCKED"


class StudioInvalidationIntent(str, Enum):
    NONE = "NONE"
    DOWNSTREAM = "DOWNSTREAM"


def canonical_content_hash(*, content: Any, schema_version: str = "studio.artifact/v1alpha1") -> str:
    """Deterministic canonical content hash for an immutable artifact/revision.

    Uses a stable, sorted JSON serialization so equivalent structures always hash
    identically regardless of insertion order; output is a SHA-256 hex digest.
    """
    payload = {"schema_version": schema_version, "content": content}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class StudioProductionRevision(BaseModel):
    """Immutable revision of an Episode's story content."""

    model_config = ConfigDict(frozen=True, extra="allow")

    revision_id: ProductionRevisionId
    series_id: SeriesProjectId
    episode_id: EpisodeId
    parent_revision_id: Optional[ProductionRevisionId] = None
    creator: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    content_hash: str = Field(min_length=64, max_length=64)
    state: StudioRevisionStatus = StudioRevisionStatus.DRAFT
    status: StudioRevisionStatus = StudioRevisionStatus.DRAFT
    lock_state: StudioLockState = StudioLockState.UNLOCKED
    invalidation_intent: Optional[StudioInvalidationIntent] = None
    summary: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    optimistic_version: int = Field(default=0, ge=0)

    @field_validator("creator", "actor")
    @classmethod
    def _actor_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Revision creator/actor cannot be blank.")
        return v.strip()

    @property
    def locked(self) -> bool:
        return self.lock_state == StudioLockState.LOCKED

    def model_dump_json_compat(self) -> Dict[str, Any]:
        return {
            "revision_id": str(self.revision_id),
            "series_id": str(self.series_id),
            "episode_id": str(self.episode_id),
            "parent_revision_id": str(self.parent_revision_id) if self.parent_revision_id else None,
            "creator": self.creator,
            "actor": self.actor,
            "created_at": self.created_at.isoformat(),
            "content_hash": self.content_hash,
            "state": self.state.value,
            "status": self.status.value,
            "lock_state": self.lock_state.value,
            "invalidation_intent": self.invalidation_intent.value if self.invalidation_intent else None,
            "summary": self.summary,
            "metadata": self.metadata,
            "optimistic_version": self.optimistic_version,
        }


class StudioRevisionService:
    """Domain service enforcing revision immutability, stale-write, and lock rules."""

    @staticmethod
    def derive_revision(
        *,
        parent: StudioProductionRevision,
        series_id: SeriesProjectId,
        episode_id: EpisodeId,
        new_content_hash: str,
        creator: str,
        actor: Optional[str] = None,
        invalidation_intent: Optional[StudioInvalidationIntent] = None,
        summary: str = "",
        expected_parent_version: Optional[int] = None,
    ) -> StudioProductionRevision:
        """Derive a new immutable revision from a parent.

        - A stale parent (expected version mismatch) is rejected.
        - A locked parent requires an explicit invalidation intent; otherwise the
          derivation is rejected with ``StudioLockedRevisionError``. Deriving
          from a locked revision is the ONLY way to change content after lock.
        """
        if expected_parent_version is not None and (
            parent.optimistic_version != expected_parent_version
        ):
            raise StudioStaleRevisionError(
                "Cannot derive from a stale parent revision.",
                details={
                    "parent_revision_id": str(parent.revision_id),
                    "expected_version": expected_parent_version,
                    "current_version": parent.optimistic_version,
                },
            )
        if parent.locked and invalidation_intent in (None, StudioInvalidationIntent.NONE):
            raise StudioLockedRevisionError(
                "Cannot mutate a locked revision; pass an explicit invalidation intent "
                "to derive a new revision.",
                details={"parent_revision_id": str(parent.revision_id)},
            )
        if len(new_content_hash) != 64:
            raise StudioValidationError("new_content_hash must be a 64-char SHA-256 hex digest.")
        return StudioProductionRevision(
            revision_id=ProductionRevisionId.generate("rev"),
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
        revision: StudioProductionRevision,
        expected_content_hash: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> StudioProductionRevision:
        """Return an immutable locked copy of a revision.

        Rejects a stale hash or stale version so a locked receipt always binds to
        the exact canonical content.
        """
        if expected_version is not None and revision.optimistic_version != expected_version:
            raise StudioStaleRevisionError(
                "Cannot lock a stale revision.",
                details={
                    "revision_id": str(revision.revision_id),
                    "expected_version": expected_version,
                    "current_version": revision.optimistic_version,
                },
            )
        if expected_content_hash is not None and expected_content_hash != revision.content_hash:
            raise StudioArtifactHashMismatchError(
                "Lock hash does not match the canonical revision content hash.",
                details={
                    "revision_id": str(revision.revision_id),
                    "expected_hash": expected_content_hash,
                    "canonical_hash": revision.content_hash,
                },
            )
        if revision.locked and revision.status == StudioRevisionStatus.LOCKED:
            return revision
        return revision.model_copy(
            update={
                "lock_state": StudioLockState.LOCKED,
                "state": StudioRevisionStatus.LOCKED,
                "status": StudioRevisionStatus.LOCKED,
                "optimistic_version": revision.optimistic_version + 1,
            }
        )

    @staticmethod
    def record_stale_write_guard(
        *,
        revision: StudioProductionRevision,
        expected_content_hash: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> None:
        """Raise when a write targets stale content or a superseded version."""
        if expected_version is not None and revision.optimistic_version != expected_version:
            raise StudioStaleRevisionError(
                "Write guard failed: revision version is stale.",
                details={
                    "revision_id": str(revision.revision_id),
                    "expected_version": expected_version,
                    "current_version": revision.optimistic_version,
                },
            )
        if expected_content_hash is not None and expected_content_hash != revision.content_hash:
            raise StudioArtifactHashMismatchError(
                "Write guard failed: content hash is stale.",
                details={
                    "revision_id": str(revision.revision_id),
                    "expected_hash": expected_content_hash,
                    "canonical_hash": revision.content_hash,
                },
            )


__all__ = [
    "utc_now",
    "StudioRevisionStatus",
    "StudioLockState",
    "StudioInvalidationIntent",
    "canonical_content_hash",
    "StudioProductionRevision",
    "StudioRevisionService",
]
