"""
VideoProject aggregate and immutable ProductionRevision model.

Revision immutability contract (road_map.md Phase 3):
- Every revision carries revision_id, parent_revision_id, created_at,
  created_by, and a content hash.
- Locked artifacts cannot be mutated; any change must derive a NEW revision.
- Screenplay changes must declare a downstream invalidation intent.
- Approvals always point at a specific revision + hash.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.domain.video_production.enums import (
    InvalidationIntent,
    ProjectStatus,
    RevisionStatus,
)
from windagent_core.domain.video_production.errors import (
    LockedRevisionMutationError,
    VideoProductionProtocolError,
)
from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)


def utc_now() -> datetime:
    """Return current UTC time (aware)."""
    return datetime.now(timezone.utc)


class VideoProject(BaseModel):
    """Top-level aggregate owning revisions of a video production."""

    model_config = ConfigDict(frozen=True, extra="allow")

    project_id: VideoProjectId
    title: str = Field(min_length=1)
    status: ProjectStatus = ProjectStatus.DRAFT
    current_revision_id: Optional[ProductionRevisionId] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise VideoProductionProtocolError("VideoProject title cannot be blank.")
        return v.strip()


class ProductionRevision(BaseModel):
    """Immutable revision of a VideoProductionPackage.

    `locked=True` means the artifact is frozen: it cannot be mutated and
    cannot be re-derived without an explicit invalidation intent.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    revision_id: ProductionRevisionId
    project_id: VideoProjectId
    parent_revision_id: Optional[ProductionRevisionId] = None
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    status: RevisionStatus = RevisionStatus.DRAFT
    locked: bool = False
    invalidation_intent: Optional[InvalidationIntent] = None
    change_summary: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_by")
    @classmethod
    def _creator_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise VideoProductionProtocolError("ProductionRevision created_by cannot be blank.")
        return v.strip()


class RevisionService:
    """Domain service enforcing the revision immutability contract."""

    @staticmethod
    def derive_revision(
        *,
        parent: ProductionRevision,
        project_id: VideoProjectId,
        new_content_hash: str,
        created_by: str,
        invalidation_intent: Optional[InvalidationIntent] = None,
        change_summary: Optional[str] = None,
    ) -> ProductionRevision:
        """Derive a new revision from a parent.

        A locked parent requires an explicit invalidation intent for the
        screenplay change; otherwise the mutation is rejected.
        """
        if parent.locked and invalidation_intent in (None, InvalidationIntent.NONE):
            raise LockedRevisionMutationError(
                "Cannot mutate locked revision; derive a new revision with an "
                "explicit downstream invalidation intent.",
                details={
                    "revision_id": str(parent.revision_id),
                    "project_id": str(project_id),
                },
            )
        return ProductionRevision(
            revision_id=ProductionRevisionId.generate("rev"),
            project_id=project_id,
            parent_revision_id=parent.revision_id,
            created_by=created_by,
            content_hash=new_content_hash,
            status=RevisionStatus.DRAFT,
            invalidation_intent=invalidation_intent,
            change_summary=change_summary,
        )

    @staticmethod
    def lock(revision: ProductionRevision) -> ProductionRevision:
        """Return a locked copy of a revision (immutable; creates a new object)."""
        return revision.model_copy(update={"locked": True, "status": RevisionStatus.LOCKED})

    @staticmethod
    def is_locked(revision: ProductionRevision) -> bool:
        return revision.locked or revision.status == RevisionStatus.LOCKED


__all__ = [
    "utc_now",
    "VideoProject",
    "ProductionRevision",
    "RevisionService",
]
