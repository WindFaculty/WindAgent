"""
Content-addressed artifact model (plan 05 §12, gate VP18_ARTIFACT_INVALIDATION_VERIFIED).

The artifact record is the SINGLE source of truth for an artifact. The storage
locator is only a content-addressed reference (never a public authority);
identity is the content hash + the metadata record (plan 05 §12):

    artifact_id / artifact_type / content_sha256 / byte_size / media_type /
    storage_locator / producer / project_id / revision_id / input_hashes /
    request_hash / prompt|compiler|model versions / generation parameters /
    created_at / validation_status / approval_status / superseded_by

Fail-closed properties (gate VP18):

- a record is only VALID after the content-addressed file exists AND the
  record was atomically promoted — a crash never leaves a VALID record
  pointing to a missing file, nor a published file without a record;
- invalidation NEVER deletes or mutates history: it moves a record to
  STALE / SUPERSEDED and appends an audit entry (§14.3);
- the artifact key is versioned; an algorithm change produces a NEW key
  version and old keys are never reinterpreted (§13).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ArtifactType(str, Enum):
    """Canonical artifact types produced by the video production workflow."""

    PROJECT_RECORD = "PROJECT_RECORD"
    CONCEPT_SET = "CONCEPT_SET"
    SELECTED_CONCEPT = "SELECTED_CONCEPT"
    SCREENPLAY = "SCREENPLAY"
    LOCKED_SCREENPLAY = "LOCKED_SCREENPLAY"
    CHARACTER_BIBLE = "CHARACTER_BIBLE"
    LOCATION_BIBLE = "LOCATION_BIBLE"
    PROP_BIBLE = "PROP_BIBLE"
    STYLE_BIBLE = "STYLE_BIBLE"
    REFERENCE_IMAGE = "REFERENCE_IMAGE"
    CINEMATIC_PLAN = "CINEMATIC_PLAN"
    SHOT_PLAN = "SHOT_PLAN"
    PROMPT = "PROMPT"
    FRAMES = "FRAMES"
    CLIP = "CLIP"
    CANDIDATE_SET = "CANDIDATE_SET"
    AUDIO_MIX = "AUDIO_MIX"
    BGM = "BGM"
    FINAL_CUT = "FINAL_CUT"
    FINAL_DELIVERABLE = "FINAL_DELIVERABLE"
    OTHER = "OTHER"


class ArtifactStatus(str, Enum):
    """Lifecycle status of an artifact record (plan 05 §14.3).

    Invalidation does NOT delete; it moves a record from VALID to STALE or
    SUPERSEDED and keeps the full audit history for later garbage collection
    under a retention policy.
    """

    VALID = "VALID"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"


class ArtifactValidationStatus(str, Enum):
    """Result of the atomic-publish validation pipeline (§14.1)."""

    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"


class ArtifactApprovalStatus(str, Enum):
    """Approval state of an artifact for its project/revision (§14.4)."""

    UNAPPROVED = "UNAPPROVED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


ARTIFACT_SCHEMA_VERSION = "1.0.0"


@dataclass
class ArtifactRecord:
    """Durable metadata record for one content-addressed artifact (§12)."""

    artifact_id: str
    artifact_type: ArtifactType
    content_sha256: str
    byte_size: int
    media_type: str
    storage_locator: str  # content hash — NOT a public authority
    producer: str
    project_id: str
    revision_id: str
    input_hashes: Dict[str, str] = field(default_factory=dict)
    request_hash: str = ""
    prompt_version: str = ""
    compiler_version: str = ""
    model_version: str = ""
    generation_mode: str = ""
    generation_parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    validation_status: ArtifactValidationStatus = ArtifactValidationStatus.PENDING
    approval_status: ArtifactApprovalStatus = ArtifactApprovalStatus.UNAPPROVED
    status: ArtifactStatus = ArtifactStatus.VALID
    superseded_by: Optional[str] = None
    artifact_key: str = ""
    key_version: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)

    # -- helpers -----------------------------------------------------------
    def new_history_entry(self, kind: str, reason: str, *, at: Optional[float] = None, **extra: Any) -> Dict[str, Any]:
        """Append one audit entry. `at` is clock-injectable for determinism;
        the publisher threads its injected clock through this param."""
        entry: Dict[str, Any] = {
            "kind": kind,
            "reason": reason,
            "at": at if at is not None else time.time(),
            **extra,
        }
        self.history.append(entry)
        return entry

    def mark_stale(self, reason: str, *, actor: str = "system", at: Optional[float] = None) -> None:
        """VALID -> STALE with an append-only audit entry (never deletes)."""
        if self.status == ArtifactStatus.VALID:
            self.status = ArtifactStatus.STALE
            self.new_history_entry("stale", reason, actor=actor, previous_status="VALID", at=at)

    def mark_superseded(self, superseded_by: str, reason: str, *, actor: str = "system", at: Optional[float] = None) -> None:
        """VALID/STALE -> SUPERSEDED bound to the replacement artifact id."""
        previous = self.status.value
        self.status = ArtifactStatus.SUPERSEDED
        self.superseded_by = superseded_by
        self.new_history_entry(
            "superseded", reason, actor=actor, superseded_by=superseded_by,
            previous_status=previous, at=at,
        )

    # -- serialization -----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type.value,
            "content_sha256": self.content_sha256,
            "byte_size": self.byte_size,
            "media_type": self.media_type,
            "storage_locator": self.storage_locator,
            "producer": self.producer,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "input_hashes": dict(self.input_hashes),
            "request_hash": self.request_hash,
            "prompt_version": self.prompt_version,
            "compiler_version": self.compiler_version,
            "model_version": self.model_version,
            "generation_mode": self.generation_mode,
            "generation_parameters": dict(self.generation_parameters),
            "created_at": self.created_at,
            "validation_status": self.validation_status.value,
            "approval_status": self.approval_status.value,
            "status": self.status.value,
            "superseded_by": self.superseded_by,
            "artifact_key": self.artifact_key,
            "key_version": self.key_version,
            "history": [dict(h) for h in self.history],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactRecord":
        # Fail-closed on unknown major schema versions (never reinterpret a
        # future record format under the current parser, §13 philosophy).
        schema_version = str(data.get("schema_version") or ARTIFACT_SCHEMA_VERSION)
        major = schema_version.split(".", 1)[0]
        if major != ARTIFACT_SCHEMA_VERSION.split(".", 1)[0]:
            raise ValueError(
                f"Unsupported artifact record schema version {schema_version!r}; "
                f"current major is {ARTIFACT_SCHEMA_VERSION.split('.', 1)[0]}"
            )
        return cls(
            artifact_id=data["artifact_id"],
            artifact_type=ArtifactType(data.get("artifact_type", "OTHER")),
            content_sha256=data["content_sha256"],
            byte_size=data.get("byte_size", 0),
            media_type=data.get("media_type", ""),
            storage_locator=data.get("storage_locator", ""),
            producer=data.get("producer", ""),
            project_id=data.get("project_id", ""),
            revision_id=data.get("revision_id", ""),
            input_hashes=dict(data.get("input_hashes", {})),
            request_hash=data.get("request_hash", ""),
            prompt_version=data.get("prompt_version", ""),
            compiler_version=data.get("compiler_version", ""),
            model_version=data.get("model_version", ""),
            generation_mode=data.get("generation_mode", ""),
            generation_parameters=dict(data.get("generation_parameters", {})),
            created_at=data.get("created_at", 0.0),
            validation_status=ArtifactValidationStatus(data.get("validation_status", "PENDING")),
            approval_status=ArtifactApprovalStatus(data.get("approval_status", "UNAPPROVED")),
            status=ArtifactStatus(data.get("status", "VALID")),
            superseded_by=data.get("superseded_by"),
            artifact_key=data.get("artifact_key", ""),
            key_version=data.get("key_version", ""),
            history=[dict(h) for h in data.get("history", [])],
        )


def new_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:24]}"


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ArtifactType",
    "ArtifactStatus",
    "ArtifactValidationStatus",
    "ArtifactApprovalStatus",
    "ArtifactRecord",
    "new_artifact_id",
]
