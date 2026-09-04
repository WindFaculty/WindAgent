"""Immutable Live Record commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from windagent.platform.commands import Command

from .models import (
    DirectorSessionView,
    LiveExecutionPlanView,
    RecordingEventView,
    RecordingSegmentView,
    RecordingTakeView,
)


@dataclass(frozen=True, slots=True)
class CreateExecutionPlan(Command[LiveExecutionPlanView]):
    episode_id: str
    episode_revision_id: str
    scenes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    actions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    recording_profile: dict[str, Any] = field(default_factory=dict)
    payload_bundles: dict[str, str] = field(default_factory=dict)
    source_workspace_hash: str = ""
    preparation_revision: int | None = None
    plan_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdatePlanContent(Command[LiveExecutionPlanView]):
    plan_id: str
    scenes: tuple[dict[str, Any], ...] | None = None
    actions: tuple[dict[str, Any], ...] | None = None
    payload_bundles: dict[str, str] | None = None
    source_workspace_hash: str | None = None
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class TransitionPlan(Command[LiveExecutionPlanView]):
    plan_id: str
    target: str  # PREPARED / VALIDATED / FROZEN / STALE / INVALID
    expected_version: int | None = None
    current_episode_revision_id: str | None = None


@dataclass(frozen=True, slots=True)
class CreateTake(Command[RecordingTakeView]):
    plan_id: str
    episode_id: str | None = None


@dataclass(frozen=True, slots=True)
class AppendTakeEvent(Command[RecordingEventView]):
    take_id: str
    event_type: str
    t: float = 0.0
    scene_id: str | None = None
    cue_id: str | None = None
    action_id: str | None = None
    segment_id: str | None = None
    execution_id: str | None = None
    marker_type: str | None = None
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CreateSegment(Command[RecordingSegmentView]):
    take_id: str
    segment_index: int = 0
    file_token: str = ""
    started_at: str | None = None
    ended_at: str | None = None
    duration_sec: float | None = None
    is_playable: bool = False
    manifest: dict[str, Any] = field(default_factory=dict)
    segment_id: str | None = None


@dataclass(frozen=True, slots=True)
class BootstrapDirectorSession(Command[DirectorSessionView]):
    execution_plan_id: str
    episode_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    connection_state: str = "CONNECTING"


@dataclass(frozen=True, slots=True)
class RefreshDirectorSession(Command[DirectorSessionView]):
    session_id: str
    connection_state: str | None = None


@dataclass(frozen=True, slots=True)
class PrepareRecordingPackage(Command[LiveExecutionPlanView]):
    episode_id: str
    episode_revision_id: str
    scenes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    recording_profile: dict[str, Any] | None = None
    source_workspace_hash: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DispatchPreparedAction(Command[dict[str, Any]]):
    plan_id: str
    action_id: str


@dataclass(frozen=True, slots=True)
class RecordActionResult(Command[dict[str, Any]]):
    plan_id: str
    take_id: str
    action_id: str
    status: str
    execution_id: str
    idempotency_key: str
    t: float = 0.0
    detail: str = ""
    before_hash_observed: str | None = None
    after_hash_observed: str | None = None
    observed: dict[str, Any] = field(default_factory=dict)
    scene_id: str | None = None
    cue_id: str | None = None
