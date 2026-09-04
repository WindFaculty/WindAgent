"""Application view models and durable row types for Live Record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Durable rows (1:1 with tables)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LiveExecutionPlanRow:
    plan_id: str
    episode_id: str
    episode_revision_id: str
    preparation_revision: int
    plan_hash: str
    status: str
    director_role: str
    recording_profile_json: str
    scenes_json: str
    actions_json: str
    payload_bundles_json: str
    source_workspace_hash: str
    created_at: datetime | None
    frozen_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class RecordingTakeRow:
    take_id: str
    execution_plan_id: str
    execution_plan_hash: str
    episode_id: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class RecordingSegmentRow:
    segment_id: str
    take_id: str
    segment_index: int
    file_token: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_sec: float | None
    is_playable: bool
    manifest_json: str


@dataclass(frozen=True, slots=True)
class RecordingEventRow:
    take_id: str
    seq: int
    event_type: str
    t: float
    scene_id: str | None
    cue_id: str | None
    action_id: str | None
    segment_id: str | None
    execution_id: str | None
    marker_type: str | None
    detail: str
    payload_json: str
    occurred_at: datetime | None


@dataclass(frozen=True, slots=True)
class DirectorSessionRow:
    session_id: str
    execution_plan_id: str
    execution_plan_hash: str
    provider_id: str | None
    model_id: str | None
    connection_state: str
    started_at: datetime | None
    expires_at: datetime | None
    updated_at: datetime | None
    metadata_json: str


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LiveExecutionPlanView:
    plan_id: str
    episode_id: str
    episode_revision_id: str
    preparation_revision: int
    plan_hash: str
    status: str
    director_role: str
    recording_profile: dict[str, Any]
    scenes: tuple[dict[str, Any], ...]
    actions: tuple[dict[str, Any], ...]
    payload_bundles: dict[str, str]
    source_workspace_hash: str
    created_at: datetime | None
    frozen_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]
    recordable: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "episode_id": self.episode_id,
            "episode_revision_id": self.episode_revision_id,
            "preparation_revision": self.preparation_revision,
            "plan_hash": self.plan_hash,
            "status": self.status,
            "director_role": self.director_role,
            "recording_profile": self.recording_profile,
            "scenes": list(self.scenes),
            "actions": list(self.actions),
            "payload_bundles": self.payload_bundles,
            "source_workspace_hash": self.source_workspace_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
            "recordable": self.recordable,
        }


@dataclass(frozen=True, slots=True)
class RecordingTakeView:
    take_id: str
    execution_plan_id: str
    execution_plan_hash: str
    episode_id: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "take_id": self.take_id,
            "execution_plan_id": self.execution_plan_id,
            "execution_plan_hash": self.execution_plan_hash,
            "episode_id": self.episode_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class RecordingSegmentView:
    segment_id: str
    take_id: str
    segment_index: int
    file_token: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_sec: float | None
    is_playable: bool
    manifest: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "take_id": self.take_id,
            "segment_index": self.segment_index,
            "file_token": self.file_token,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_sec": self.duration_sec,
            "is_playable": self.is_playable,
            "manifest": self.manifest,
        }


@dataclass(frozen=True, slots=True)
class RecordingEventView:
    take_id: str
    seq: int
    event_type: str
    t: float
    scene_id: str | None
    cue_id: str | None
    action_id: str | None
    segment_id: str | None
    execution_id: str | None
    marker_type: str | None
    detail: str
    payload: dict[str, Any]
    occurred_at: datetime | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "take_id": self.take_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "t": self.t,
            "scene_id": self.scene_id,
            "cue_id": self.cue_id,
            "action_id": self.action_id,
            "segment_id": self.segment_id,
            "execution_id": self.execution_id,
            "marker_type": self.marker_type,
            "detail": self.detail,
            "payload": self.payload,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }


@dataclass(frozen=True, slots=True)
class DirectorSessionView:
    session_id: str
    execution_plan_id: str
    execution_plan_hash: str
    provider_id: str | None
    model_id: str | None
    connection_state: str
    started_at: datetime | None
    expires_at: datetime | None
    updated_at: datetime | None
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "execution_plan_id": self.execution_plan_id,
            "execution_plan_hash": self.execution_plan_hash,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "connection_state": self.connection_state,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }
