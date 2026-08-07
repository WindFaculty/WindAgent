"""
VP3D Phase 1 — Production IR event protocol.

Minimal event taxonomy for the engine-neutral IR lifecycle (plan §4 backlog
item 6):

- ProductionIrCreated
- ProductionIrLocked
- EngineJobSubmitted
- EngineJobCompleted
- EngineJobFailed
- DerivedArtifactPublished

The taxonomy is additive to the legacy VideoProductionEventCatalog: historical
generative-video streams keep using `video_production.*`, IR/engine streams
use `video_production_ir.*`. No dual-write beyond the Stage A compatibility
window.

Consumers must be idempotent by event_id; duplicate events never create
duplicate engine jobs or artifacts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.domain.video_production.ids import (
    EngineJobId,
    ProductionIrId,
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.domain.video_production.errors import UnsupportedMajorVersionError

PRODUCTION_IR_EVENT_SCHEMA_VERSION = "1.0.0"
SUPPORTED_IR_EVENT_MAJOR_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProductionIrEventCatalog:
    """Dotted taxonomy of canonical Production IR / engine events."""

    IR_CREATED = "video_production_ir.created"
    IR_LOCKED = "video_production_ir.locked"
    ENGINE_JOB_SUBMITTED = "video_production_ir.engine_job_submitted"
    ENGINE_JOB_COMPLETED = "video_production_ir.engine_job_completed"
    ENGINE_JOB_FAILED = "video_production_ir.engine_job_failed"
    DERIVED_ARTIFACT_PUBLISHED = "video_production_ir.derived_artifact_published"

    ALL_EVENTS: Set[str] = {
        IR_CREATED,
        IR_LOCKED,
        ENGINE_JOB_SUBMITTED,
        ENGINE_JOB_COMPLETED,
        ENGINE_JOB_FAILED,
        DERIVED_ARTIFACT_PUBLISHED,
    }


class ProductionIrEventEnvelope(BaseModel):
    """Immutable event envelope for the Production IR protocol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(min_length=1)
    schema_version: str = PRODUCTION_IR_EVENT_SCHEMA_VERSION
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    ir_id: ProductionIrId
    aggregate_id: str = Field(min_length=1)
    causation_id: Optional[str] = None
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = Field(default_factory=utc_now)
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        if v not in ProductionIrEventCatalog.ALL_EVENTS:
            raise ValueError(f"Unknown Production IR event type {v!r}.")
        return v

    @field_validator("schema_version")
    @classmethod
    def _validate_major(cls, v: str) -> str:
        major = int(v.split(".")[0])
        if major != SUPPORTED_IR_EVENT_MAJOR_VERSION:
            raise UnsupportedMajorVersionError(
                f"Unsupported Production IR event schema major version {major}; "
                f"supported is {SUPPORTED_IR_EVENT_MAJOR_VERSION}."
            )
        return v

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "project_id": str(self.project_id),
            "revision_id": str(self.revision_id),
            "ir_id": str(self.ir_id),
            "aggregate_id": self.aggregate_id,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProductionIrEventEnvelope":
        return cls.model_validate(data)


# ----------------------------------------------------------------------
# Valid event transitions
# ----------------------------------------------------------------------
IR_EVENT_TRANSITIONS: Dict[str, Set[str]] = {
    ProductionIrEventCatalog.IR_CREATED: {ProductionIrEventCatalog.IR_LOCKED},
    ProductionIrEventCatalog.IR_LOCKED: {ProductionIrEventCatalog.ENGINE_JOB_SUBMITTED},
    ProductionIrEventCatalog.ENGINE_JOB_SUBMITTED: {
        ProductionIrEventCatalog.ENGINE_JOB_COMPLETED,
        ProductionIrEventCatalog.ENGINE_JOB_FAILED,
        ProductionIrEventCatalog.ENGINE_JOB_SUBMITTED,  # idempotent resubmit
    },
    ProductionIrEventCatalog.ENGINE_JOB_FAILED: {
        ProductionIrEventCatalog.ENGINE_JOB_SUBMITTED,  # retry
        ProductionIrEventCatalog.ENGINE_JOB_FAILED,
    },
    ProductionIrEventCatalog.ENGINE_JOB_COMPLETED: {
        ProductionIrEventCatalog.DERIVED_ARTIFACT_PUBLISHED,
    },
    ProductionIrEventCatalog.DERIVED_ARTIFACT_PUBLISHED: set(),
}


class ProductionIrEventTransitions:
    """Legal transition enforcement for Production IR events."""

    TERMINAL_EVENTS: Set[str] = {ProductionIrEventCatalog.DERIVED_ARTIFACT_PUBLISHED}

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        if current == target:
            return not cls.is_terminal(current)
        return target in IR_EVENT_TRANSITIONS.get(current, set())

    @classmethod
    def validate_sequence(cls, event_types: list[str]) -> Optional[str]:
        for idx in range(1, len(event_types)):
            if not cls.can_transition(event_types[idx - 1], event_types[idx]):
                return (
                    f"Illegal Production IR transition "
                    f"{event_types[idx - 1]} -> {event_types[idx]} at step {idx}."
                )
        return None

    @classmethod
    def is_terminal(cls, event_type: str) -> bool:
        return event_type in cls.TERMINAL_EVENTS


class IrEventIdempotencyGuard:
    """Tracks processed IR event_ids to enforce idempotent consumption."""

    def __init__(self) -> None:
        self._processed: Set[str] = set()

    def process(self, envelope: ProductionIrEventEnvelope) -> bool:
        if envelope.event_id in self._processed:
            return False
        self._processed.add(envelope.event_id)
        return True


__all__ = [
    "utc_now",
    "PRODUCTION_IR_EVENT_SCHEMA_VERSION",
    "SUPPORTED_IR_EVENT_MAJOR_VERSION",
    "ProductionIrEventCatalog",
    "ProductionIrEventEnvelope",
    "IR_EVENT_TRANSITIONS",
    "ProductionIrEventTransitions",
    "IrEventIdempotencyGuard",
]
