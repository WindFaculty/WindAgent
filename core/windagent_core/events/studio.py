"""
Canonical Studio event protocol (studio.contract/v0.1).

Dotted, lower-case event taxonomy owned exclusively by Plan A
(docs/plans/studio_roadmap_01/fixtures/studio_contract_v0.1/events.json). Each
event carries: event_id, event_type, schema_version, aggregate_id, aggregate_type,
sequence, occurred_at, correlation_id, causation_id, studio_run_id, revision_ref,
artifact_refs, and a redaction-safe payload. Task finalization publishes through
the transactional outbox; consumer read models must be idempotent by event ID and
sequence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.contracts.studio.ids import ArtifactId, StudioRunId

STUDIO_EVENT_SCHEMA_VERSION = "studio.event/v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StudioEventCatalog:
    """Frozen dotted taxonomy of canonical Studio events."""

    SERIES_CREATED = "studio.series.created"
    EPISODE_CREATED = "studio.episode.created"
    REVISION_DERIVED = "studio.revision.derived"
    ARTIFACT_CREATED = "studio.artifact.created"
    IDEA_CANDIDATES_GENERATED = "studio.idea.candidates_generated"
    IDEA_SELECTED = "studio.idea.selected"
    APPROVAL_REQUESTED = "studio.approval.requested"
    APPROVAL_RECORDED = "studio.approval.recorded"
    STORY_REVIEW_COMPLETED = "studio.story.review_completed"
    STORY_REVISION_REQUESTED = "studio.story.revision_requested"
    SCREENPLAY_LOCKED = "studio.screenplay.locked"
    EPISODE_READY_FOR_PRODUCTION = "studio.episode.ready_for_production"
    RUN_STARTED = "studio.run.started"
    RUN_COMPLETED = "studio.run.completed"
    TASK_SUBMITTED = "studio.task.submitted"
    TASK_COMPLETED = "studio.task.completed"
    RUN_FAILED = "studio.run.failed"
    RUN_CANCELLED = "studio.run.cancelled"

    ALL_EVENTS: Set[str] = {
        SERIES_CREATED,
        EPISODE_CREATED,
        REVISION_DERIVED,
        ARTIFACT_CREATED,
        IDEA_CANDIDATES_GENERATED,
        IDEA_SELECTED,
        APPROVAL_REQUESTED,
        APPROVAL_RECORDED,
        STORY_REVIEW_COMPLETED,
        STORY_REVISION_REQUESTED,
        SCREENPLAY_LOCKED,
        EPISODE_READY_FOR_PRODUCTION,
        RUN_STARTED,
        RUN_COMPLETED,
        TASK_SUBMITTED,
        TASK_COMPLETED,
        RUN_FAILED,
        RUN_CANCELLED,
    }


class StudioEventEnvelope(BaseModel):
    """Immutable canonical Studio event envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(min_length=1)
    schema_version: str = STUDIO_EVENT_SCHEMA_VERSION
    aggregate_id: str = Field(min_length=1)
    aggregate_type: str = Field(default="studio", min_length=1)
    sequence: int = Field(default=0, ge=0)
    occurred_at: datetime = Field(default_factory=utc_now)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    studio_run_id: Optional[StudioRunId] = None
    revision_ref: Optional[str] = None
    artifact_refs: List[ArtifactId] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        if v not in StudioEventCatalog.ALL_EVENTS:
            raise ValueError(f"Unknown Studio event type {v!r}.")
        return v

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "studio_run_id": str(self.studio_run_id) if self.studio_run_id else None,
            "revision_ref": self.revision_ref,
            "artifact_refs": [str(a) for a in self.artifact_refs],
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StudioEventEnvelope:
        return cls.model_validate(data)


__all__ = [
    "utc_now",
    "STUDIO_EVENT_SCHEMA_VERSION",
    "StudioEventCatalog",
    "StudioEventEnvelope",
]
