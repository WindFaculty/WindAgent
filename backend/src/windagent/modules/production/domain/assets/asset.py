"""ProductionAsset aggregate and immutable AssetRevision (Phase 16).

Models the universal production resource aggregate:
- ProductionAsset represents identity, active pointers, tags, and lifecycle.
- AssetRevision represents immutable, content-addressed snapshots carrying
  sha256, preview artifacts, validation results, and provenance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .lifecycle import AssetLifecycleState, AssetStateMachine


def utc_now() -> datetime:
    return datetime.now(UTC)


class AssetKind(StrEnum):
    CHARACTER = "CHARACTER"
    ENVIRONMENT = "ENVIRONMENT"
    PROP = "PROP"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    MODEL = "MODEL"
    OTHER = "OTHER"


class MediaType(StrEnum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    MODEL = "MODEL"
    OTHER = "OTHER"


class LicenseState(StrEnum):
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMMERCIAL = "COMMERCIAL"


class AssetSourceType(StrEnum):
    UPLOADED = "UPLOADED"
    GENERATED = "GENERATED"
    INTERNET = "INTERNET"
    PROVIDER = "PROVIDER"
    LOCAL_LIBRARY = "LOCAL_LIBRARY"


class ProcessingState(StrEnum):
    IDLE = "IDLE"
    NORMALIZING = "NORMALIZING"
    NORMALIZED = "NORMALIZED"
    FAILED = "FAILED"


class AssetRevision(BaseModel):
    """Immutable content-addressed snapshot of an asset."""

    model_config = ConfigDict(frozen=True, extra="allow")

    revision_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    supersedes_revision_id: str | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    media_type: MediaType = MediaType.IMAGE
    mime_type: str = "image/png"
    size_bytes: int = Field(ge=0)
    normalized_format: str | None = None
    preview_artifacts: dict[str, Any] = Field(default_factory=dict)
    validation_report: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ProductionAsset(BaseModel):
    """Universal Production Asset Aggregate Root."""

    model_config = ConfigDict(extra="allow")

    asset_id: str = Field(min_length=1)
    project_id: str | None = None
    kind: AssetKind = AssetKind.OTHER
    name: str = Field(min_length=1)
    description: str = ""
    lifecycle_state: AssetLifecycleState = AssetLifecycleState.DISCOVERED
    processing_state: ProcessingState = ProcessingState.IDLE
    active_revision_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_type: AssetSourceType = AssetSourceType.UPLOADED
    license_state: LicenseState = LicenseState.UNKNOWN
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def transition_lifecycle(
        self,
        target: AssetLifecycleState,
        *,
        new_review_record: bool = False,
    ) -> None:
        AssetStateMachine.require_transition(self.lifecycle_state, target, new_review_record=new_review_record)
        self.lifecycle_state = target
        self.updated_at = utc_now()
        self.optimistic_version += 1

    def is_eligible_for_production(self) -> bool:
        if self.license_state in (LicenseState.UNKNOWN, LicenseState.REJECTED):
            return False
        if self.lifecycle_state == AssetLifecycleState.REJECTED:
            return False
        if self.lifecycle_state == AssetLifecycleState.QUARANTINED:
            return False
        return True


__all__ = [
    "AssetKind",
    "AssetRevision",
    "AssetSourceType",
    "LicenseState",
    "MediaType",
    "ProcessingState",
    "ProductionAsset",
    "utc_now",
]
