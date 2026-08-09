"""
ProductionAsset Aggregate Root and Immutable AssetRevision Entity (Stage D UI20).

Models the universal production resource aggregate:
- ProductionAsset represents business entity identity, active pointers, tags, and lifecycle states.
- AssetRevision represents immutable, content-addressed asset snapshots carrying sha256 bytes checksum,
  preview artifacts, validation results, and provenance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.asset_lifecycle import (
    AssetLifecycleState,
    AssetStateMachine,
)
from windagent_core.domain.video_production.enums import (
    AssetProcessingState,
    AssetSourceType,
    LicenseState,
    MediaType,
    ProductionAssetKind,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssetRevision(BaseModel):
    """Immutable content-addressed snapshot of an asset (Stage D UI20)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    revision_id: str = Field(default_factory=lambda: f"rev_{uuid4().hex[:12]}")
    asset_id: str
    supersedes_revision_id: Optional[str] = None
    content_hash: str = Field(min_length=64, max_length=64)
    media_type: MediaType = MediaType.IMAGE
    mime_type: str = "image/png"
    size_bytes: int = Field(ge=0)
    normalized_format: Optional[str] = None
    preview_artifacts: Dict[str, Any] = Field(default_factory=dict)
    validation_report: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ProductionAsset(BaseModel):
    """Universal Production Asset Aggregate Root (Stage D UI20)."""

    model_config = ConfigDict(extra="allow")

    asset_id: str = Field(default_factory=lambda: f"ast_{uuid4().hex[:12]}")
    kind: ProductionAssetKind = ProductionAssetKind.OTHER
    name: str
    description: str = ""
    lifecycle_state: AssetLifecycleState = AssetLifecycleState.DISCOVERED
    processing_state: AssetProcessingState = AssetProcessingState.IDLE
    active_revision_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source_type: AssetSourceType = AssetSourceType.UPLOADED
    license_state: LicenseState = LicenseState.UNKNOWN
    project_bindings: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def update_lifecycle_state(
        self,
        target_state: AssetLifecycleState,
        *,
        new_review_record: bool = False,
    ) -> None:
        """Validate and transition business lifecycle state (UI21)."""
        AssetStateMachine.require_transition(
            self.lifecycle_state, target_state, new_review_record=new_review_record
        )
        self.lifecycle_state = target_state
        self.updated_at = utc_now()

    def update_processing_state(self, target_state: AssetProcessingState) -> None:
        """Transition operational processing state (UI21)."""
        self.processing_state = target_state
        self.updated_at = utc_now()

    def set_active_revision(self, revision_id: str) -> None:
        """Explicit pointer update for active revision (UI20)."""
        self.active_revision_id = revision_id
        self.updated_at = utc_now()

    def is_eligible_for_production(self) -> bool:
        """Server-side license governance eligibility check (UI26).

        Assets with UNKNOWN or REJECTED license state fail-closed and cannot be rendered
        or published in final production.
        """
        if self.license_state in (LicenseState.UNKNOWN, LicenseState.REJECTED):
            return False
        if self.lifecycle_state == AssetLifecycleState.REJECTED:
            return False
        return True


__all__ = [
    "utc_now",
    "AssetRevision",
    "ProductionAsset",
]
