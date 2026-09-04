"""Live Record queries (side-effect-free)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from windagent.platform.queries import Query

from .models import (
    DirectorSessionView,
    LiveExecutionPlanView,
    RecordingEventView,
    RecordingSegmentView,
    RecordingTakeView,
)


@dataclass(frozen=True, slots=True)
class GetLiveExecutionPlan(Query[LiveExecutionPlanView]):
    plan_id: str


@dataclass(frozen=True, slots=True)
class ListLiveExecutionPlans(Query[tuple[LiveExecutionPlanView, ...]]):
    episode_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetTake(Query[RecordingTakeView]):
    take_id: str


@dataclass(frozen=True, slots=True)
class ListTakes(Query[tuple[RecordingTakeView, ...]]):
    execution_plan_id: str | None = None


@dataclass(frozen=True, slots=True)
class ListTakeEvents(Query[tuple[RecordingEventView, ...]]):
    take_id: str


@dataclass(frozen=True, slots=True)
class ListTakeSegments(Query[tuple[RecordingSegmentView, ...]]):
    take_id: str


@dataclass(frozen=True, slots=True)
class GetDirectorSession(Query[DirectorSessionView]):
    session_id: str


@dataclass(frozen=True, slots=True)
class ListDirectorSessions(Query[tuple[DirectorSessionView, ...]]):
    execution_plan_id: str | None = None


@dataclass(frozen=True, slots=True)
class PrivacyScan(Query[dict[str, Any]]):
    plan_id: str


@dataclass(frozen=True, slots=True)
class ClassifyFailure(Query[dict[str, Any]]):
    failure: str


@dataclass(frozen=True, slots=True)
class StalenessCheck(Query[dict[str, Any]]):
    plan_id: str
    current_episode_revision_id: str
