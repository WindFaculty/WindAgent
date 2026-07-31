"""
Asset domain models: content-addressed ReferenceAsset and the published
FinalDeliverable.

Assets ALWAYS carry a content hash (SHA-256). Assets sourced from the
internet must carry an acquisition/provenance record (road_map.md Phase 7).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import AssetSourceType, LicenseState, MediaType
from windagent_core.domain.video_production.ids import (
    FinalDeliverableId,
    ProductionRevisionId,
    ReferenceAssetId,
    VideoProjectId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssetAcquisitionRecord(BaseModel):
    """Provenance of an acquired asset."""

    model_config = ConfigDict(frozen=True, extra="allow")

    source_type: AssetSourceType
    source_url: Optional[str] = None
    acquired_at: datetime = Field(default_factory=utc_now)
    license_state: LicenseState = LicenseState.UNKNOWN
    notes: str = ""


class ReferenceAsset(BaseModel):
    """Content-addressed asset referenced by bibles, shots, and candidates."""

    model_config = ConfigDict(frozen=True, extra="allow")

    asset_id: ReferenceAssetId
    content_hash: str = Field(min_length=64, max_length=64)
    media_type: MediaType = MediaType.IMAGE
    mime_type: str = "image/png"
    size_bytes: int = Field(ge=0)
    source_type: AssetSourceType = AssetSourceType.UPLOADED
    source_url: Optional[str] = None
    license_state: LicenseState = LicenseState.UNKNOWN
    acquisition: Optional[AssetAcquisitionRecord] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FinalDeliverable(BaseModel):
    """Published final video deliverable bound to a revision."""

    model_config = ConfigDict(frozen=True, extra="allow")

    deliverable_id: FinalDeliverableId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    content_hash: str = Field(min_length=64, max_length=64)
    mime_type: str = "video/mp4"
    duration_seconds: float = Field(ge=0)
    uri: str = ""
    published_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "utc_now",
    "AssetAcquisitionRecord",
    "ReferenceAsset",
    "FinalDeliverable",
]
