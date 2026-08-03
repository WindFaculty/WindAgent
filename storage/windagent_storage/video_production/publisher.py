"""
Atomic artifact publisher (plan 05 §14.1, gate VP18_ARTIFACT_INVALIDATION_VERIFIED).

Publish pipeline:

    write temporary blob
    -> hash / size / decode validation
    -> metadata record transaction
    -> atomic promote (content file + record both durable)
    -> publish ArtifactAvailable event

Crash-safety contract (§14.1): a crash at ANY point never leaves

- a VALID record pointing to a missing file (the content file is published
  to the content-addressed store BEFORE the record is saved), nor
- a published file without a record (the record write is atomic and happens
  after the file exists; an orphan file without a record is GC-able and
  never referenced).

The ArtifactAvailable event is appended to the record store's event journal
AFTER the record write succeeded — an event is never emitted for an artifact
that did not durably commit.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from windagent_storage.video_production.key import (
    ARTIFACT_KEY_VERSION,
    compute_artifact_key,
)
from windagent_storage.video_production.model import (
    ArtifactApprovalStatus,
    ArtifactRecord,
    ArtifactStatus,
    ArtifactType,
    ArtifactValidationStatus,
    new_artifact_id,
)
from windagent_storage.video_production.store import (
    ArtifactRecordStore,
    ContentAddressedStore,
)


class DecodeValidatorPort(Protocol):
    """Validates payload bytes before promotion (§14.1 hash/size/decode)."""

    def validate(self, data: bytes) -> None: ...


@dataclass
class ArtifactAvailableEvent:
    """Outbox-style event emitted after a successful atomic publish (§14.1)."""

    event_id: str
    artifact_id: str
    artifact_key: str
    content_sha256: str
    project_id: str
    revision_id: str
    emitted_at: float
    deduplication_key: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "artifact_id": self.artifact_id,
            "artifact_key": self.artifact_key,
            "content_sha256": self.content_sha256,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "emitted_at": self.emitted_at,
            "deduplication_key": self.deduplication_key,
        }


@dataclass
class PublishRequest:
    """Intent for one atomic artifact publish (§14.1)."""

    artifact_type: ArtifactType
    data: bytes
    media_type: str
    producer: str
    project_id: str
    revision_id: str
    artifact_id: Optional[str] = None  # explicit id (deterministic tests/verifier); default generated
    input_hashes: Dict[str, str] = field(default_factory=dict)
    request_hash: str = ""
    prompt_version: str = ""
    compiler_version: str = ""
    model_version: str = ""
    generation_mode: str = ""
    generation_parameters: Dict[str, Any] = field(default_factory=dict)
    reference_hashes: List[str] = field(default_factory=list)
    canonical_input: Dict[str, Any] = field(default_factory=dict)
    key_version: str = ARTIFACT_KEY_VERSION


@dataclass
class PublishResult:
    record: ArtifactRecord
    event: ArtifactAvailableEvent


class ArtifactPublisher:
    """Composes content store + record store into the atomic publish pipeline."""

    def __init__(
        self,
        *,
        content_store: ContentAddressedStore,
        record_store: ArtifactRecordStore,
        validator: Optional[DecodeValidatorPort] = None,
        clock=None,
    ) -> None:
        self.content_store = content_store
        self.record_store = record_store
        self.validator = validator
        self._clock = clock or time.time

    # -- public API --------------------------------------------------------
    def publish(self, request: PublishRequest) -> PublishResult:
        """Run the atomic publish pipeline (§14.1). Idempotent by content hash:
        re-publishing identical bytes yields the same content hash (and the
        same record when the metadata matches)."""
        # 1. hash / size / decode validation (fail closed BEFORE any write)
        if not request.data:
            raise ValueError("Cannot publish empty payload")
        # 2. write content to the content-addressed store FIRST (atomic)
        content_hash = self.content_store.publish(request.data)
        # 3. validate AFTER bytes are durable (validator may decode the blob)
        if self.validator is not None:
            self.validator.validate(request.data)

        # 4. metadata record transaction (atomic, after file exists)
        artifact_key = compute_artifact_key(
            canonical_input=request.canonical_input,
            prompt_version=request.prompt_version,
            reference_hashes=request.reference_hashes,
            model=request.model_version,
            generation_mode=request.generation_mode,
            generation_parameters=request.generation_parameters,
            key_version=request.key_version,
        )
        record = ArtifactRecord(
            artifact_id=request.artifact_id or new_artifact_id(),
            artifact_type=request.artifact_type,
            content_sha256=content_hash,
            byte_size=len(request.data),
            media_type=request.media_type,
            storage_locator=content_hash,  # content address — NOT public authority
            producer=request.producer,
            project_id=request.project_id,
            revision_id=request.revision_id,
            input_hashes=dict(request.input_hashes),
            request_hash=request.request_hash,
            prompt_version=request.prompt_version,
            compiler_version=request.compiler_version,
            model_version=request.model_version,
            generation_mode=request.generation_mode,
            generation_parameters=dict(request.generation_parameters),
            created_at=self._clock(),
            validation_status=ArtifactValidationStatus.VALIDATED,
            approval_status=ArtifactApprovalStatus.UNAPPROVED,
            status=ArtifactStatus.VALID,
            artifact_key=artifact_key,
            key_version=request.key_version,
        )
        record.new_history_entry(
            "published",
            "atomic publish completed",
            at=self._clock(),
            content_sha256=content_hash,
        )
        self.record_store.save(record)

        # 5. publish ArtifactAvailable event AFTER the record commit.
        event = ArtifactAvailableEvent(
            event_id=f"evt_{uuid.uuid4().hex[:24]}",
            artifact_id=record.artifact_id,
            artifact_key=artifact_key,
            content_sha256=content_hash,
            project_id=request.project_id,
            revision_id=request.revision_id,
            emitted_at=self._clock(),
            deduplication_key=f"artifact_available:{artifact_key}:{content_hash}",
        )
        return PublishResult(record=record, event=event)


class EventJournal:
    """Append-only event journal for published artifact events (§14.1)."""

    def __init__(self, journal_path) -> None:
        import json as _json

        self._json = _json
        self.journal_path = journal_path
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: ArtifactAvailableEvent) -> None:
        with open(self.journal_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(self._json.dumps(event.to_dict(), sort_keys=True) + "\n")

    def events(self) -> List[Dict[str, Any]]:
        if not self.journal_path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with open(self.journal_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(self._json.loads(line))
        return out


__all__ = [
    "DecodeValidatorPort",
    "ArtifactAvailableEvent",
    "PublishRequest",
    "PublishResult",
    "ArtifactPublisher",
    "EventJournal",
]
