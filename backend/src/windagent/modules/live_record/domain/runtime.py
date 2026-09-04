"""Runtime records for takes, segments, events, director sessions (Phase 17)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .lifecycle import TakeSessionStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


SessionStatus = TakeSessionStatus


class RecordingTakeRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    take_id: str = Field(min_length=1)
    execution_plan_id: str = Field(min_length=1)
    execution_plan_hash: str = Field(min_length=64, max_length=64)
    episode_id: str = Field(min_length=1)
    session_status: SessionStatus = SessionStatus.IDLE
    started_at: datetime | None = None
    ended_at: datetime | None = None
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecordingSegmentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    segment_id: str = Field(min_length=1)
    take_id: str = Field(min_length=1)
    segment_index: int = Field(ge=0)
    file_token: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_sec: float | None = None
    is_playable: bool = False
    manifest: dict[str, Any] = Field(default_factory=dict)


class RecordingEventRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    take_id: str = Field(min_length=1)
    seq: int = Field(default=0, ge=0)
    event_type: str = Field(min_length=1)
    t: float = Field(default=0.0, ge=0)
    scene_id: str | None = None
    cue_id: str | None = None
    action_id: str | None = None
    segment_id: str | None = None
    execution_id: str | None = None
    marker_type: str | None = None
    detail: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class DirectorSessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1)
    execution_plan_id: str = Field(min_length=1)
    execution_plan_hash: str = Field(min_length=64, max_length=64)
    provider_id: str | None = None
    model_id: str | None = None
    connection_state: str = "DISCONNECTED"
    started_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NativeCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    wgc_available: bool = False
    nvenc_available: bool = False
    audio_capture_available: bool = False
    libav_available: bool = False
    reason: str = ""


__all__ = [
    "DirectorSessionRecord",
    "NativeCapabilities",
    "RecordingEventRecord",
    "RecordingSegmentRecord",
    "RecordingTakeRecord",
    "SessionStatus",
]
