"""Live Record domain events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.time import utc_now
from windagent.kernel.types import Version

EVENT_PLAN_CREATED: Final[str] = "live_record.plan.created"
EVENT_PLAN_UPDATED: Final[str] = "live_record.plan.updated"
EVENT_PLAN_TRANSITIONED: Final[str] = "live_record.plan.transitioned"
EVENT_PLAN_FROZEN: Final[str] = "live_record.plan.frozen"
EVENT_TAKE_CREATED: Final[str] = "live_record.take.created"
EVENT_TAKE_TRANSITIONED: Final[str] = "live_record.take.transitioned"
EVENT_SEGMENT_CREATED: Final[str] = "live_record.segment.created"
EVENT_EVENT_APPENDED: Final[str] = "live_record.event.appended"
EVENT_DIRECTOR_SESSION_CREATED: Final[str] = "live_record.director_session.created"
EVENT_DIRECTOR_SESSION_REFRESHED: Final[str] = "live_record.director_session.refreshed"
EVENT_PRIVACY_SCAN_COMPLETED: Final[str] = "live_record.privacy_scan.completed"

EVENT_VERSION: Final[int] = 1


def _entity_id(value: str) -> EntityId:
    try:
        return EntityId(value)
    except ValueError:
        import uuid

        return EntityId(str(uuid.uuid5(uuid.NAMESPACE_URL, value)))


def _envelope(event_type: str, aggregate_type: str, aggregate_id: str, payload: dict[str, Any]) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=_entity_id(aggregate_id),
        sequence=0,
        event_version=Version(EVENT_VERSION),
        occurred_at=utc_now(),
        payload=payload,
    )


def plan_created(plan_id: str, episode_id: str) -> EventEnvelope:
    return _envelope(EVENT_PLAN_CREATED, "LiveExecutionPlan", plan_id, {"plan_id": plan_id, "episode_id": episode_id})


def plan_updated(plan_id: str) -> EventEnvelope:
    return _envelope(EVENT_PLAN_UPDATED, "LiveExecutionPlan", plan_id, {"plan_id": plan_id})


def plan_transitioned(plan_id: str, from_status: str, to_status: str) -> EventEnvelope:
    return _envelope(EVENT_PLAN_TRANSITIONED, "LiveExecutionPlan", plan_id, {"plan_id": plan_id, "from_status": from_status, "to_status": to_status})


def plan_frozen(plan_id: str, plan_hash: str) -> EventEnvelope:
    return _envelope(EVENT_PLAN_FROZEN, "LiveExecutionPlan", plan_id, {"plan_id": plan_id, "plan_hash": plan_hash})


def take_created(take_id: str, plan_id: str) -> EventEnvelope:
    return _envelope(EVENT_TAKE_CREATED, "RecordingTake", take_id, {"take_id": take_id, "plan_id": plan_id})


def take_transitioned(take_id: str, from_status: str, to_status: str) -> EventEnvelope:
    return _envelope(EVENT_TAKE_TRANSITIONED, "RecordingTake", take_id, {"take_id": take_id, "from_status": from_status, "to_status": to_status})


def segment_created(segment_id: str, take_id: str) -> EventEnvelope:
    return _envelope(EVENT_SEGMENT_CREATED, "RecordingSegment", segment_id, {"segment_id": segment_id, "take_id": take_id})


def event_appended(take_id: str, seq: int, event_type: str) -> EventEnvelope:
    return _envelope(EVENT_EVENT_APPENDED, "RecordingEvent", f"{take_id}:{seq}", {"take_id": take_id, "seq": seq, "event_type": event_type})


def director_session_created(session_id: str, plan_id: str) -> EventEnvelope:
    return _envelope(EVENT_DIRECTOR_SESSION_CREATED, "DirectorSession", session_id, {"session_id": session_id, "plan_id": plan_id})


def director_session_refreshed(session_id: str) -> EventEnvelope:
    return _envelope(EVENT_DIRECTOR_SESSION_REFRESHED, "DirectorSession", session_id, {"session_id": session_id})


def privacy_scan_completed(plan_id: str, status: str) -> EventEnvelope:
    return _envelope(EVENT_PRIVACY_SCAN_COMPLETED, "LiveExecutionPlan", plan_id, {"plan_id": plan_id, "status": status})


@dataclass(frozen=True, slots=True)
class LiveRecordEventFactory:
    def plan_created(self, plan_id: str, episode_id: str) -> EventEnvelope:
        return plan_created(plan_id, episode_id)

    def plan_updated(self, plan_id: str) -> EventEnvelope:
        return plan_updated(plan_id)

    def plan_transitioned(self, plan_id: str, from_status: str, to_status: str) -> EventEnvelope:
        return plan_transitioned(plan_id, from_status, to_status)

    def plan_frozen(self, plan_id: str, plan_hash: str) -> EventEnvelope:
        return plan_frozen(plan_id, plan_hash)

    def take_created(self, take_id: str, plan_id: str) -> EventEnvelope:
        return take_created(take_id, plan_id)

    def take_transitioned(self, take_id: str, from_status: str, to_status: str) -> EventEnvelope:
        return take_transitioned(take_id, from_status, to_status)

    def segment_created(self, segment_id: str, take_id: str) -> EventEnvelope:
        return segment_created(segment_id, take_id)

    def event_appended(self, take_id: str, seq: int, event_type: str) -> EventEnvelope:
        return event_appended(take_id, seq, event_type)

    def director_session_created(self, session_id: str, plan_id: str) -> EventEnvelope:
        return director_session_created(session_id, plan_id)

    def director_session_refreshed(self, session_id: str) -> EventEnvelope:
        return director_session_refreshed(session_id)

    def privacy_scan_completed(self, plan_id: str, status: str) -> EventEnvelope:
        return privacy_scan_completed(plan_id, status)
