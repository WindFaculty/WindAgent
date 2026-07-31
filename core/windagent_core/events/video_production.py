"""
Video Production event protocol (Phase 3).

Event taxonomy for the roadmap event catalog:
VideoProjectCreated, ConceptApproved, ScreenplayGenerated, ScreenplayLocked,
CharacterBibleApproved, LocationBibleApproved, CinematicPlanGenerated,
ShotPlanLocked, GenerationSubmitted, GenerationCompleted, GenerationRejected,
HumanActionRequired, SequenceCompleted, FinalVideoPublished.

Every event envelope carries:
  event_id, event_type, schema_version, project_id, revision_id,
  aggregate_id, causation_id, correlation_id, occurred_at, payload.

Consumers must be idempotent by event_id; duplicate events never create
duplicate generations or approvals.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.domain.video_production.errors import UnsupportedMajorVersionError

VIDEO_PRODUCTION_EVENT_SCHEMA_VERSION = "1.0.0"
SUPPORTED_EVENT_MAJOR_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VideoProductionEventCatalog:
    """Dotted taxonomy of canonical video production events."""

    PROJECT_CREATED = "video_production.project_created"
    CONCEPT_APPROVED = "video_production.concept_approved"
    SCREENPLAY_GENERATED = "video_production.screenplay_generated"
    SCREENPLAY_LOCKED = "video_production.screenplay_locked"
    CHARACTER_BIBLE_APPROVED = "video_production.character_bible_approved"
    LOCATION_BIBLE_APPROVED = "video_production.location_bible_approved"
    CINEMATIC_PLAN_GENERATED = "video_production.cinematic_plan_generated"
    SHOT_PLAN_LOCKED = "video_production.shot_plan_locked"
    GENERATION_SUBMITTED = "video_production.generation_submitted"
    GENERATION_COMPLETED = "video_production.generation_completed"
    GENERATION_REJECTED = "video_production.generation_rejected"
    HUMAN_ACTION_REQUIRED = "video_production.human_action_required"
    SEQUENCE_COMPLETED = "video_production.sequence_completed"
    FINAL_VIDEO_PUBLISHED = "video_production.final_video_published"

    ALL_EVENTS: Set[str] = {
        PROJECT_CREATED,
        CONCEPT_APPROVED,
        SCREENPLAY_GENERATED,
        SCREENPLAY_LOCKED,
        CHARACTER_BIBLE_APPROVED,
        LOCATION_BIBLE_APPROVED,
        CINEMATIC_PLAN_GENERATED,
        SHOT_PLAN_LOCKED,
        GENERATION_SUBMITTED,
        GENERATION_COMPLETED,
        GENERATION_REJECTED,
        HUMAN_ACTION_REQUIRED,
        SEQUENCE_COMPLETED,
        FINAL_VIDEO_PUBLISHED,
    }


class VideoProductionEventEnvelope(BaseModel):
    """Immutable event envelope for the video production protocol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(min_length=1)
    schema_version: str = VIDEO_PRODUCTION_EVENT_SCHEMA_VERSION
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    aggregate_id: str = Field(min_length=1)
    causation_id: Optional[str] = None
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = Field(default_factory=utc_now)
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        if v not in VideoProductionEventCatalog.ALL_EVENTS:
            raise ValueError(f"Unknown video production event type {v!r}.")
        return v

    @field_validator("schema_version")
    @classmethod
    def _validate_major(cls, v: str) -> str:
        major = int(v.split(".")[0])
        if major != SUPPORTED_EVENT_MAJOR_VERSION:
            raise UnsupportedMajorVersionError(
                f"Unsupported event schema major version {major}; supported is {SUPPORTED_EVENT_MAJOR_VERSION}."
            )
        return v

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "project_id": str(self.project_id),
            "revision_id": str(self.revision_id),
            "aggregate_id": self.aggregate_id,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VideoProductionEventEnvelope:
        return cls.model_validate(data)


# ----------------------------------------------------------------------
# Valid event transitions
# ----------------------------------------------------------------------
EVENT_TRANSITIONS: Dict[str, Set[str]] = {
    VideoProductionEventCatalog.PROJECT_CREATED: {
        VideoProductionEventCatalog.CONCEPT_APPROVED,
    },
    VideoProductionEventCatalog.CONCEPT_APPROVED: {
        VideoProductionEventCatalog.SCREENPLAY_GENERATED,
    },
    VideoProductionEventCatalog.SCREENPLAY_GENERATED: {
        VideoProductionEventCatalog.SCREENPLAY_LOCKED,
        VideoProductionEventCatalog.SCREENPLAY_GENERATED,
    },
    VideoProductionEventCatalog.SCREENPLAY_LOCKED: {
        VideoProductionEventCatalog.CHARACTER_BIBLE_APPROVED,
        VideoProductionEventCatalog.LOCATION_BIBLE_APPROVED,
        VideoProductionEventCatalog.CINEMATIC_PLAN_GENERATED,
    },
    VideoProductionEventCatalog.CHARACTER_BIBLE_APPROVED: {
        VideoProductionEventCatalog.CINEMATIC_PLAN_GENERATED,
    },
    VideoProductionEventCatalog.LOCATION_BIBLE_APPROVED: {
        VideoProductionEventCatalog.CINEMATIC_PLAN_GENERATED,
    },
    VideoProductionEventCatalog.CINEMATIC_PLAN_GENERATED: {
        VideoProductionEventCatalog.SHOT_PLAN_LOCKED,
    },
    VideoProductionEventCatalog.SHOT_PLAN_LOCKED: {
        VideoProductionEventCatalog.GENERATION_SUBMITTED,
    },
    VideoProductionEventCatalog.GENERATION_SUBMITTED: {
        VideoProductionEventCatalog.GENERATION_COMPLETED,
        VideoProductionEventCatalog.GENERATION_REJECTED,
        VideoProductionEventCatalog.HUMAN_ACTION_REQUIRED,
    },
    VideoProductionEventCatalog.GENERATION_REJECTED: {
        VideoProductionEventCatalog.GENERATION_SUBMITTED,
        VideoProductionEventCatalog.HUMAN_ACTION_REQUIRED,
    },
    VideoProductionEventCatalog.HUMAN_ACTION_REQUIRED: {
        VideoProductionEventCatalog.GENERATION_SUBMITTED,
        VideoProductionEventCatalog.GENERATION_REJECTED,
    },
    VideoProductionEventCatalog.GENERATION_COMPLETED: {
        VideoProductionEventCatalog.SEQUENCE_COMPLETED,
    },
    VideoProductionEventCatalog.SEQUENCE_COMPLETED: {
        VideoProductionEventCatalog.FINAL_VIDEO_PUBLISHED,
        VideoProductionEventCatalog.GENERATION_SUBMITTED,
    },
    VideoProductionEventCatalog.FINAL_VIDEO_PUBLISHED: set(),
}


class VideoProductionEventTransitions:
    """Legal transition enforcement for video production events."""

    TERMINAL_EVENTS: Set[str] = {VideoProductionEventCatalog.FINAL_VIDEO_PUBLISHED}

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        if current == target:
            return not cls.is_terminal(current)
        return target in EVENT_TRANSITIONS.get(current, set())

    @classmethod
    def validate_sequence(cls, event_types: list[str]) -> Optional[str]:
        """Validate a list of event types; returns an error message or None."""
        for idx in range(1, len(event_types)):
            if not cls.can_transition(event_types[idx - 1], event_types[idx]):
                return f"Illegal transition {event_types[idx - 1]} -> {event_types[idx]} at step {idx}."
        return None

    @classmethod
    def is_terminal(cls, event_type: str) -> bool:
        return event_type in cls.TERMINAL_EVENTS


class EventIdempotencyGuard:
    """Tracks processed event_ids to enforce at-least-once/idempotent consumption."""

    def __init__(self) -> None:
        self._processed: Set[str] = set()

    def is_duplicate(self, event_id: str) -> bool:
        return event_id in self._processed

    def mark_processed(self, event_id: str) -> None:
        self._processed.add(event_id)

    def process(self, envelope: VideoProductionEventEnvelope) -> bool:
        """Return True if the event should be processed (first time)."""
        if self.is_duplicate(envelope.event_id):
            return False
        self.mark_processed(envelope.event_id)
        return True


__all__ = [
    "utc_now",
    "VIDEO_PRODUCTION_EVENT_SCHEMA_VERSION",
    "SUPPORTED_EVENT_MAJOR_VERSION",
    "VideoProductionEventCatalog",
    "VideoProductionEventEnvelope",
    "EVENT_TRANSITIONS",
    "VideoProductionEventTransitions",
    "EventIdempotencyGuard",
]
