"""In-memory adapter for Live Record — mirrors SQL CAS semantics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from windagent.kernel.events import EventEnvelope

from ..application.models import (
    DirectorSessionRow,
    LiveExecutionPlanRow,
    RecordingEventRow,
    RecordingSegmentRow,
    RecordingTakeRow,
)
from ..application.ports import LiveRecordStore, TransactionScope


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryLiveRecordStore(LiveRecordStore):
    def __init__(self) -> None:
        self._plans: dict[str, LiveExecutionPlanRow] = {}
        self._takes: dict[str, RecordingTakeRow] = {}
        self._segments: dict[str, RecordingSegmentRow] = {}
        self._events: dict[str, list[RecordingEventRow]] = {}
        self._directors: dict[str, DirectorSessionRow] = {}
        self._recorded: list[EventEnvelope] = []
        self._revision_counters: dict[str, int] = {}

    # -- plans -----------------------------------------------------------
    async def insert_plan(self, row: LiveExecutionPlanRow) -> bool:
        if row.plan_id in self._plans:
            return False
        self._plans[row.plan_id] = row
        # track max revision
        cur = self._revision_counters.get(row.episode_id, 0)
        if row.preparation_revision > cur:
            self._revision_counters[row.episode_id] = row.preparation_revision
        return True

    async def get_plan(self, plan_id: str) -> LiveExecutionPlanRow | None:
        return self._plans.get(plan_id)

    async def list_plans(self, episode_id: str | None = None) -> tuple[LiveExecutionPlanRow, ...]:
        rows = list(self._plans.values())
        if episode_id is not None:
            rows = [r for r in rows if r.episode_id == episode_id]
        rows.sort(key=lambda r: r.created_at or _utc_now())
        return tuple(rows)

    async def update_plan(
        self,
        plan_id: str,
        *,
        status: str | None = None,
        plan_hash: str | None = None,
        frozen_at: Any | None = None,
        scenes_json: str | None = None,
        actions_json: str | None = None,
        payload_bundles_json: str | None = None,
        source_workspace_hash: str | None = None,
        recording_profile_json: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
        metadata_json: str | None = None,
    ) -> LiveExecutionPlanRow | None:
        existing = self._plans.get(plan_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = LiveExecutionPlanRow(
            plan_id=existing.plan_id,
            episode_id=existing.episode_id,
            episode_revision_id=existing.episode_revision_id,
            preparation_revision=existing.preparation_revision,
            plan_hash=plan_hash if plan_hash is not None else existing.plan_hash,
            status=status if status is not None else existing.status,
            director_role=existing.director_role,
            recording_profile_json=recording_profile_json if recording_profile_json is not None else existing.recording_profile_json,
            scenes_json=scenes_json if scenes_json is not None else existing.scenes_json,
            actions_json=actions_json if actions_json is not None else existing.actions_json,
            payload_bundles_json=payload_bundles_json if payload_bundles_json is not None else existing.payload_bundles_json,
            source_workspace_hash=source_workspace_hash if source_workspace_hash is not None else existing.source_workspace_hash,
            created_at=existing.created_at,
            frozen_at=frozen_at if frozen_at is not None else existing.frozen_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self._plans[plan_id] = updated
        return updated

    async def next_preparation_revision(self, episode_id: str) -> int:
        # max revision for episode +1
        max_rev = 0
        for row in self._plans.values():
            if row.episode_id == episode_id and row.preparation_revision > max_rev:
                max_rev = row.preparation_revision
        tracked = self._revision_counters.get(episode_id, 0)
        chosen = max(max_rev, tracked) + 1
        self._revision_counters[episode_id] = chosen
        return chosen

    # -- takes -----------------------------------------------------------
    async def insert_take(self, row: RecordingTakeRow) -> bool:
        if row.take_id in self._takes:
            return False
        self._takes[row.take_id] = row
        return True

    async def get_take(self, take_id: str) -> RecordingTakeRow | None:
        return self._takes.get(take_id)

    async def list_takes(self, execution_plan_id: str | None = None) -> tuple[RecordingTakeRow, ...]:
        rows = list(self._takes.values())
        if execution_plan_id is not None:
            rows = [r for r in rows if r.execution_plan_id == execution_plan_id]
        rows.sort(key=lambda r: r.created_at or _utc_now())
        return tuple(rows)

    async def update_take(self, take_id: str, *, status: str | None = None, optimistic_version: int | None = None, expected_version: int | None = None) -> RecordingTakeRow | None:
        existing = self._takes.get(take_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = RecordingTakeRow(
            take_id=existing.take_id,
            execution_plan_id=existing.execution_plan_id,
            execution_plan_hash=existing.execution_plan_hash,
            episode_id=existing.episode_id,
            status=status if status is not None else existing.status,
            started_at=existing.started_at,
            ended_at=existing.ended_at,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version,
            metadata_json=existing.metadata_json,
        )
        self._takes[take_id] = updated
        return updated

    # -- segments --------------------------------------------------------
    async def insert_segment(self, row: RecordingSegmentRow) -> bool:
        if row.segment_id in self._segments:
            return False
        self._segments[row.segment_id] = row
        return True

    async def upsert_segment(self, row: RecordingSegmentRow) -> RecordingSegmentRow:
        self._segments[row.segment_id] = row
        return row

    async def get_segment(self, segment_id: str) -> RecordingSegmentRow | None:
        return self._segments.get(segment_id)

    async def list_segments(self, take_id: str) -> tuple[RecordingSegmentRow, ...]:
        rows = [r for r in self._segments.values() if r.take_id == take_id]
        rows.sort(key=lambda r: r.segment_index)
        return tuple(rows)

    # -- events ----------------------------------------------------------
    async def append_event(self, row: RecordingEventRow) -> RecordingEventRow:
        lst = self._events.setdefault(row.take_id, [])
        # seq should match len
        lst.append(row)
        return row

    async def list_events(self, take_id: str) -> tuple[RecordingEventRow, ...]:
        lst = self._events.get(take_id, [])
        lst_sorted = sorted(lst, key=lambda r: r.seq)
        return tuple(lst_sorted)

    # -- director sessions -----------------------------------------------
    async def insert_director_session(self, row: DirectorSessionRow) -> bool:
        if row.session_id in self._directors:
            return False
        self._directors[row.session_id] = row
        return True

    async def get_director_session(self, session_id: str) -> DirectorSessionRow | None:
        return self._directors.get(session_id)

    async def update_director_session(self, session_id: str, *, connection_state: str | None = None, expires_at: Any | None = None, metadata_json: str | None = None) -> DirectorSessionRow | None:
        existing = self._directors.get(session_id)
        if existing is None:
            return None
        updated = DirectorSessionRow(
            session_id=existing.session_id,
            execution_plan_id=existing.execution_plan_id,
            execution_plan_hash=existing.execution_plan_hash,
            provider_id=existing.provider_id,
            model_id=existing.model_id,
            connection_state=connection_state if connection_state is not None else existing.connection_state,
            started_at=existing.started_at,
            expires_at=expires_at if expires_at is not None else existing.expires_at,
            updated_at=datetime.now(UTC),
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self._directors[session_id] = updated
        return updated

    async def list_director_sessions(self, execution_plan_id: str | None = None) -> tuple[DirectorSessionRow, ...]:
        rows = list(self._directors.values())
        if execution_plan_id is not None:
            rows = [r for r in rows if r.execution_plan_id == execution_plan_id]
        rows.sort(key=lambda r: r.started_at or _utc_now())
        return tuple(rows)

    @property
    def recorded_events(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._recorded)


class InMemoryTransactionScope(TransactionScope):
    def __init__(self, store: InMemoryLiveRecordStore | None = None) -> None:
        self._store = store or InMemoryLiveRecordStore()
        self._active = False

    async def __aenter__(self) -> InMemoryTransactionScope:
        self._active = True
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None) -> bool:
        self._active = False
        return False

    def store(self) -> LiveRecordStore:
        return self._store

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        self._store._recorded.append(envelope)
        return True

    async def commit(self) -> None:
        return None


def memory_scope_factory(store: InMemoryLiveRecordStore | None = None) -> Callable[[], InMemoryTransactionScope]:
    shared = store or InMemoryLiveRecordStore()

    def factory() -> InMemoryTransactionScope:
        return InMemoryTransactionScope(shared)

    factory.store = shared  # type: ignore[attr-defined]
    return factory
