"""Live Record runtime records (live_record.contract/v0.1).

Frozen pydantic records for the recording-time lineage persisted by the API
layer: takes, segments, the append-only timeline events, and director sessions.
These are the durable mirrors of the Phase-0-frozen TS types in
``frontend/app/src/features/live-record/domain/types.ts``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

#: Mirrors ``LiveRecordSessionStatus`` (12 states) in domain/types.ts.
SessionStatus = Literal[
    "IDLE",
    "PREPARING",
    "PREFLIGHT",
    "READY",
    "RECORDING",
    "PAUSED",
    "DIRECTOR_DEGRADED",
    "RECOVERING",
    "FINALIZING",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
]


class RecordingTakeRecord(BaseModel):
    """One recording run of a frozen execution plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    take_id: str = Field(min_length=1)
    execution_plan_id: str = Field(min_length=1)
    execution_plan_hash: str = Field(min_length=64, max_length=64)
    episode_id: str = Field(min_length=1)
    session_status: SessionStatus = "IDLE"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    optimistic_version: int = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RecordingSegmentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    segment_id: str = Field(min_length=1)
    take_id: str = Field(min_length=1)
    segment_index: int = Field(ge=0)
    file_token: str = ""  # tokenized delivery ref; raw FS paths never surface here
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_sec: Optional[float] = None
    is_playable: bool = False
    manifest: Dict[str, Any] = Field(default_factory=dict)


class RecordingEventRecord(BaseModel):
    """One timeline row — ``t`` is seconds since take start (monotonic)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    take_id: str = Field(min_length=1)
    seq: int = Field(default=0, ge=0)  # assigned by the repository on append
    event_type: str = Field(min_length=1)
    t: float = Field(default=0.0, ge=0)
    scene_id: Optional[str] = None
    cue_id: Optional[str] = None
    action_id: Optional[str] = None
    segment_id: Optional[str] = None
    execution_id: Optional[str] = None
    marker_type: Optional[str] = None
    detail: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class DirectorSessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1)
    execution_plan_id: str = Field(min_length=1)
    execution_plan_hash: str = Field(min_length=64, max_length=64)
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    connection_state: str = "DISCONNECTED"
    # Required: a director session is only created once its connection starts.
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "RecordingTakeRecord",
    "RecordingSegmentRecord",
    "RecordingEventRecord",
    "DirectorSessionRecord",
]
