"""Live Record repository ports (live_record.contract/v0.1).

Async repository protocols the application service depends on; SQL adapters
live in ``windagent_storage.live_record.repositories``. The plan aggregate owns
scenes/actions as value objects, so persistence ports cover plan/take/segment/
event/director-session records only.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from windagent_core.contracts.live_record.ids import (
    DirectorSessionId,
    LiveExecutionPlanId,
    RecordingTakeId,
)
from windagent_core.domain.live_record.plan import LiveExecutionPlan
from windagent_core.domain.live_record.runtime import (
    DirectorSessionRecord,
    RecordingEventRecord,
    RecordingSegmentRecord,
    RecordingTakeRecord,
)


@runtime_checkable
class LiveExecutionPlanRepositoryPort(Protocol):
    async def get(self, plan_id: LiveExecutionPlanId) -> Optional[LiveExecutionPlan]:
        """Return the plan or None when absent."""
        ...

    async def save(self, plan: LiveExecutionPlan) -> LiveExecutionPlan:
        """Insert or guarded-update by optimistic_version; returns the plan."""
        ...

    async def list_by_episode(self, episode_id: str) -> List[LiveExecutionPlan]:
        ...

    async def next_preparation_revision(self, episode_id: str) -> int:
        """Max preparation_revision for the episode plus one (>= 1)."""
        ...


@runtime_checkable
class RecordingTakeRepositoryPort(Protocol):
    async def get(self, take_id: RecordingTakeId) -> Optional[RecordingTakeRecord]:
        ...

    async def save(self, take: RecordingTakeRecord) -> RecordingTakeRecord:
        ...

    async def list_by_plan(self, execution_plan_id: str) -> List[RecordingTakeRecord]:
        ...


@runtime_checkable
class RecordingSegmentRepositoryPort(Protocol):
    async def save(self, segment: RecordingSegmentRecord) -> RecordingSegmentRecord:
        ...

    async def list_by_take(self, take_id: str) -> List[RecordingSegmentRecord]:
        ...


@runtime_checkable
class RecordingEventRepositoryPort(Protocol):
    async def append(self, event: RecordingEventRecord) -> RecordingEventRecord:
        """Append one timeline row; assigns the per-take sequence."""
        ...

    async def list_by_take(self, take_id: str) -> List[RecordingEventRecord]:
        """All events ordered by seq."""
        ...


@runtime_checkable
class DirectorSessionRepositoryPort(Protocol):
    async def get(self, session_id: DirectorSessionId) -> Optional[DirectorSessionRecord]:
        ...

    async def save(self, session: DirectorSessionRecord) -> DirectorSessionRecord:
        ...


__all__ = [
    "LiveExecutionPlanRepositoryPort",
    "RecordingTakeRepositoryPort",
    "RecordingSegmentRepositoryPort",
    "RecordingEventRepositoryPort",
    "DirectorSessionRepositoryPort",
]
