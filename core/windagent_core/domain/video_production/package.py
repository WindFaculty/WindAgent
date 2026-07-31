"""
VideoProductionPackage v1 — the canonical portable artifact.

This package is the single source of truth shared between pre-production,
the Director layer, orchestration, and media providers. It is immutable
(frozen) and its canonical serialization yields a stable content hash so the
same logical content always hashes identically.

Versioning policy (see docs/video_production/protocol/versioning_policy.md):
- schema_version follows MAJOR.MINOR.PATCH.
- Unknown MAJOR versions fail closed (rejected).
- Additive compatible fields are allowed within the same MAJOR.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.domain.video_production.approval import ApprovalState
from windagent_core.domain.video_production.asset import FinalDeliverable, ReferenceAsset
from windagent_core.domain.video_production.character import CharacterBible
from windagent_core.domain.video_production.continuity import ContinuityState
from windagent_core.domain.video_production.errors import (
    UnsupportedMajorVersionError,
    VideoProductionProtocolError,
)
from windagent_core.domain.video_production.generation_job import (
    GenerationRecord,
)
from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.domain.video_production.location import LocationBible, PropBible, StyleBible
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief,
    DialogueLine,
    Screenplay,
    StoryConcept,
)
from windagent_core.domain.video_production.shot import CinematicPlan

VIDEO_PRODUCTION_PACKAGE_VERSION = "1.0.0"
SUPPORTED_MAJOR_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PackageProvenance(BaseModel):
    """Provenance metadata recorded for every package."""

    model_config = ConfigDict(frozen=True, extra="allow")

    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = Field(min_length=1)
    generator: str = "windagent-video-production-protocol"
    source_commit: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VideoProductionPackage(BaseModel):
    """Canonical v1 package artifact (immutable)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: str = VIDEO_PRODUCTION_PACKAGE_VERSION
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    creative_brief: Optional[CreativeBrief] = None
    story_concept: Optional[StoryConcept] = None
    screenplay: Optional[Screenplay] = None
    characters: List[CharacterBible] = Field(default_factory=list)
    locations: List[LocationBible] = Field(default_factory=list)
    props: List[PropBible] = Field(default_factory=list)
    style_bible: Optional[StyleBible] = None
    dialogue: List[DialogueLine] = Field(default_factory=list)
    cinematic_plan: Optional[CinematicPlan] = None
    continuity: List[ContinuityState] = Field(default_factory=list)
    assets: List[ReferenceAsset] = Field(default_factory=list)
    generation_records: List[GenerationRecord] = Field(default_factory=list)
    approvals: ApprovalState = Field(default_factory=ApprovalState)
    final_deliverable: Optional[FinalDeliverable] = None
    provenance: PackageProvenance = Field(default_factory=lambda: PackageProvenance(created_by="system"))

    @field_validator("schema_version")
    @classmethod
    def _validate_major_version(cls, v: str) -> str:
        major = int(v.split(".")[0])
        if major != SUPPORTED_MAJOR_VERSION:
            raise UnsupportedMajorVersionError(
                f"Unsupported VideoProductionPackage major version {major}; "
                f"supported major is {SUPPORTED_MAJOR_VERSION}.",
                details={"schema_version": v, "supported_major": SUPPORTED_MAJOR_VERSION},
            )
        return v

    # ------------------------------------------------------------------
    # Canonical serialization & content hash
    # ------------------------------------------------------------------
    # Operational / workflow records are append-only state: they are excluded
    # from the content hash so the SAME logical authored content always hashes
    # identically regardless of approvals, generation history, or publish time.
    CONTENT_HASH_EXCLUDED_FIELDS: ClassVar[tuple[str, ...]] = (
        "approvals",
        "provenance",
        "generation_records",
        "final_deliverable",
    )

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Return a canonical JSON-compatible dict (sorted keys, UTC ISO timestamps)."""
        return json.loads(self.model_dump_json())

    def to_content_dict(self) -> Dict[str, Any]:
        """Dict of the logical content used for content hashing.

        Approvals and provenance are append-only workflow state: they point at
        the content hash but are not part of it, so the same logical content
        always yields the same hash regardless of approval records.

        Asset acquisition timestamps are operational metadata (when an asset
        was fetched); they are stripped so the same logical content hashes
        identically no matter when it was constructed.
        """
        data = self.to_canonical_dict()
        for excluded in self.CONTENT_HASH_EXCLUDED_FIELDS:
            data.pop(excluded, None)
        # Strip operational acquisition timestamps from asset records so
        # identical logical content always hashes identically.
        for asset in data.get("assets", []):
            acquisition = asset.get("acquisition")
            if isinstance(acquisition, dict):
                acquisition.pop("acquired_at", None)
        return data

    def canonical_bytes(self) -> bytes:
        """Stable canonical bytes over the logical content (excludes approvals/provenance)."""
        canonical = json.dumps(
            self.to_content_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return canonical.encode("utf-8")

    def content_hash(self) -> str:
        """SHA-256 of the canonical serialization (stable for same logical content)."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def serialize(self) -> str:
        """Serialize the FULL package to canonical JSON string (round-trip stable)."""
        data = json.loads(self.model_dump_json())
        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def deserialize(cls, raw: str) -> VideoProductionPackage:
        """Parse canonical JSON string back into a package."""
        data = json.loads(raw)
        return cls.model_validate(data)


def parse_package_major_version(schema_version: str) -> int:
    """Extract and validate the MAJOR component of a schema version string."""
    if not schema_version or not isinstance(schema_version, str):
        raise VideoProductionProtocolError("schema_version must be a non-empty string.")
    parts = schema_version.split(".")
    try:
        major = int(parts[0])
    except (ValueError, IndexError) as exc:
        raise VideoProductionProtocolError(
            f"Malformed schema_version {schema_version!r}.",
            details={"schema_version": schema_version},
        ) from exc
    return major


def validate_package_major(schema_version: str) -> None:
    """Fail closed on unknown MAJOR version."""
    major = parse_package_major_version(schema_version)
    if major != SUPPORTED_MAJOR_VERSION:
        raise UnsupportedMajorVersionError(
            f"Unsupported VideoProductionPackage major version {major}; "
            f"supported major is {SUPPORTED_MAJOR_VERSION}.",
            details={"schema_version": schema_version, "supported_major": SUPPORTED_MAJOR_VERSION},
        )


__all__ = [
    "utc_now",
    "VIDEO_PRODUCTION_PACKAGE_VERSION",
    "SUPPORTED_MAJOR_VERSION",
    "PackageProvenance",
    "VideoProductionPackage",
    "parse_package_major_version",
    "validate_package_major",
]
