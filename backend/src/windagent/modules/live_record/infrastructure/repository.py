"""SQL adapter for the Live Record store."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from windagent.kernel.events import EventEnvelope
from windagent.platform.events.outbox import TransactionalOutbox
from windagent.platform.persistence.database import Database
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

from ..application.models import (
    DirectorSessionRow,
    LiveExecutionPlanRow,
    RecordingEventRow,
    RecordingSegmentRow,
    RecordingTakeRow,
)
from ..application.ports import LiveRecordStore
from .tables import (
    director_sessions_table,
    live_execution_plans_table,
    live_record_events_table,
    live_record_segments_table,
    live_record_takes_table,
)

STORE_REPOSITORY_NAME = "live_record_store"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def make_store(session: AsyncSession) -> SqlLiveRecordStore:
    return SqlLiveRecordStore(session)


class SqlLiveRecordStore(LiveRecordStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- plans -----------------------------------------------------------
    async def insert_plan(self, row: LiveExecutionPlanRow) -> bool:
        exists = await self._session.execute(select(live_execution_plans_table.c.plan_id).where(live_execution_plans_table.c.plan_id == row.plan_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(live_execution_plans_table).values(
                plan_id=row.plan_id,
                episode_id=row.episode_id,
                episode_revision_id=row.episode_revision_id,
                preparation_revision=row.preparation_revision,
                plan_hash=row.plan_hash,
                status=row.status,
                director_role=row.director_role,
                recording_profile_json=row.recording_profile_json,
                scenes_json=row.scenes_json,
                actions_json=row.actions_json,
                payload_bundles_json=row.payload_bundles_json,
                source_workspace_hash=row.source_workspace_hash,
                created_at=_as_utc(row.created_at),
                frozen_at=_as_utc(row.frozen_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_plan(self, plan_id: str) -> LiveExecutionPlanRow | None:
        result = await self._session.execute(select(live_execution_plans_table).where(live_execution_plans_table.c.plan_id == plan_id))
        row = result.first()
        return _plan_from_row(row) if row else None

    async def list_plans(self, episode_id: str | None = None) -> tuple[LiveExecutionPlanRow, ...]:
        stmt = select(live_execution_plans_table)
        if episode_id is not None:
            stmt = stmt.where(live_execution_plans_table.c.episode_id == episode_id)
        stmt = stmt.order_by(live_execution_plans_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_plan_from_row(row) for row in result.all())

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
        existing = await self.get_plan(plan_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if status is not None:
            values["status"] = status
        if plan_hash is not None:
            values["plan_hash"] = plan_hash
        if frozen_at is not None:
            values["frozen_at"] = _as_utc(frozen_at)
        if scenes_json is not None:
            values["scenes_json"] = scenes_json
        if actions_json is not None:
            values["actions_json"] = actions_json
        if payload_bundles_json is not None:
            values["payload_bundles_json"] = payload_bundles_json
        if source_workspace_hash is not None:
            values["source_workspace_hash"] = source_workspace_hash
        if recording_profile_json is not None:
            values["recording_profile_json"] = recording_profile_json
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if expected_version is not None:
            outcome = await self._session.execute(update(live_execution_plans_table).where(live_execution_plans_table.c.plan_id == plan_id, live_execution_plans_table.c.optimistic_version == expected_version).values(**values))
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(live_execution_plans_table).where(live_execution_plans_table.c.plan_id == plan_id).values(**values))
        return await self.get_plan(plan_id)

    async def next_preparation_revision(self, episode_id: str) -> int:
        result = await self._session.execute(select(live_execution_plans_table.c.preparation_revision).where(live_execution_plans_table.c.episode_id == episode_id).order_by(live_execution_plans_table.c.preparation_revision.desc()))
        row = result.first()
        if row is None:
            return 1
        return int(row.preparation_revision) + 1

    # -- takes -----------------------------------------------------------
    async def insert_take(self, row: RecordingTakeRow) -> bool:
        exists = await self._session.execute(select(live_record_takes_table.c.take_id).where(live_record_takes_table.c.take_id == row.take_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(live_record_takes_table).values(
                take_id=row.take_id,
                execution_plan_id=row.execution_plan_id,
                execution_plan_hash=row.execution_plan_hash,
                episode_id=row.episode_id,
                status=row.status,
                started_at=_as_utc(row.started_at),
                ended_at=_as_utc(row.ended_at),
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_take(self, take_id: str) -> RecordingTakeRow | None:
        result = await self._session.execute(select(live_record_takes_table).where(live_record_takes_table.c.take_id == take_id))
        row = result.first()
        return _take_from_row(row) if row else None

    async def list_takes(self, execution_plan_id: str | None = None) -> tuple[RecordingTakeRow, ...]:
        stmt = select(live_record_takes_table)
        if execution_plan_id is not None:
            stmt = stmt.where(live_record_takes_table.c.execution_plan_id == execution_plan_id)
        stmt = stmt.order_by(live_record_takes_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_take_from_row(row) for row in result.all())

    async def update_take(self, take_id: str, *, status: str | None = None, optimistic_version: int | None = None, expected_version: int | None = None) -> RecordingTakeRow | None:
        existing = await self.get_take(take_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if status is not None:
            values["status"] = status
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if expected_version is not None:
            outcome = await self._session.execute(update(live_record_takes_table).where(live_record_takes_table.c.take_id == take_id, live_record_takes_table.c.optimistic_version == expected_version).values(**values))
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(live_record_takes_table).where(live_record_takes_table.c.take_id == take_id).values(**values))
        return await self.get_take(take_id)

    # -- segments --------------------------------------------------------
    async def insert_segment(self, row: RecordingSegmentRow) -> bool:
        exists = await self._session.execute(select(live_record_segments_table.c.segment_id).where(live_record_segments_table.c.segment_id == row.segment_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(live_record_segments_table).values(
                segment_id=row.segment_id,
                take_id=row.take_id,
                segment_index=row.segment_index,
                file_token=row.file_token,
                started_at=_as_utc(row.started_at),
                ended_at=_as_utc(row.ended_at),
                duration_sec=row.duration_sec,
                is_playable=row.is_playable,
                manifest_json=row.manifest_json,
            )
        )
        return True

    async def upsert_segment(self, row: RecordingSegmentRow) -> RecordingSegmentRow:
        existing = await self.get_segment(row.segment_id)
        if existing is None:
            await self.insert_segment(row)
            inserted = await self.get_segment(row.segment_id)
            assert inserted is not None
            return inserted
        await self._session.execute(
            update(live_record_segments_table)
            .where(live_record_segments_table.c.segment_id == row.segment_id)
            .values(file_token=row.file_token, started_at=_as_utc(row.started_at), ended_at=_as_utc(row.ended_at), duration_sec=row.duration_sec, is_playable=row.is_playable, manifest_json=row.manifest_json)
        )
        updated = await self.get_segment(row.segment_id)
        assert updated is not None
        return updated

    async def get_segment(self, segment_id: str) -> RecordingSegmentRow | None:
        result = await self._session.execute(select(live_record_segments_table).where(live_record_segments_table.c.segment_id == segment_id))
        row = result.first()
        return _segment_from_row(row) if row else None

    async def list_segments(self, take_id: str) -> tuple[RecordingSegmentRow, ...]:
        result = await self._session.execute(select(live_record_segments_table).where(live_record_segments_table.c.take_id == take_id).order_by(live_record_segments_table.c.segment_index.asc()))
        return tuple(_segment_from_row(row) for row in result.all())

    # -- events ----------------------------------------------------------
    async def append_event(self, row: RecordingEventRow) -> RecordingEventRow:
        await self._session.execute(
            insert(live_record_events_table).values(
                take_id=row.take_id,
                seq=row.seq,
                event_type=row.event_type,
                t=row.t,
                scene_id=row.scene_id,
                cue_id=row.cue_id,
                action_id=row.action_id,
                segment_id=row.segment_id,
                execution_id=row.execution_id,
                marker_type=row.marker_type,
                detail=row.detail,
                payload_json=row.payload_json,
                occurred_at=_as_utc(row.occurred_at),
            )
        )
        fetched = await self._session.execute(select(live_record_events_table).where(live_record_events_table.c.take_id == row.take_id, live_record_events_table.c.seq == row.seq))
        r = fetched.mappings().first()
        assert r is not None
        return _event_from_row(r)

    async def list_events(self, take_id: str) -> tuple[RecordingEventRow, ...]:
        result = await self._session.execute(select(live_record_events_table).where(live_record_events_table.c.take_id == take_id).order_by(live_record_events_table.c.seq.asc()))
        return tuple(_event_from_row(row) for row in result.mappings().all())

    # -- director sessions -----------------------------------------------
    async def insert_director_session(self, row: DirectorSessionRow) -> bool:
        exists = await self._session.execute(select(director_sessions_table.c.session_id).where(director_sessions_table.c.session_id == row.session_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(director_sessions_table).values(
                session_id=row.session_id,
                execution_plan_id=row.execution_plan_id,
                execution_plan_hash=row.execution_plan_hash,
                provider_id=row.provider_id,
                model_id=row.model_id,
                connection_state=row.connection_state,
                started_at=_as_utc(row.started_at),
                expires_at=_as_utc(row.expires_at),
                updated_at=_as_utc(row.updated_at),
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_director_session(self, session_id: str) -> DirectorSessionRow | None:
        result = await self._session.execute(select(director_sessions_table).where(director_sessions_table.c.session_id == session_id))
        row = result.first()
        return _director_from_row(row) if row else None

    async def update_director_session(self, session_id: str, *, connection_state: str | None = None, expires_at: Any | None = None, metadata_json: str | None = None) -> DirectorSessionRow | None:
        existing = await self.get_director_session(session_id)
        if existing is None:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if connection_state is not None:
            values["connection_state"] = connection_state
        if expires_at is not None:
            values["expires_at"] = _as_utc(expires_at)
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        await self._session.execute(update(director_sessions_table).where(director_sessions_table.c.session_id == session_id).values(**values))
        return await self.get_director_session(session_id)

    async def list_director_sessions(self, execution_plan_id: str | None = None) -> tuple[DirectorSessionRow, ...]:
        stmt = select(director_sessions_table)
        if execution_plan_id is not None:
            stmt = stmt.where(director_sessions_table.c.execution_plan_id == execution_plan_id)
        stmt = stmt.order_by(director_sessions_table.c.started_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_director_from_row(row) for row in result.all())


class SqlTransactionScope:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):  # pragma: no cover - composition guard
            raise TypeError("transaction scope requires a SQL unit of work")
        uow.register_repository(STORE_REPOSITORY_NAME, make_store)
        self._uow = uow
        await uow.__aenter__()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None) -> bool:
        if self._uow is not None:
            await self._uow.__aexit__(exc_type, exc_value, None)
            self._uow = None
        return False

    def store(self) -> LiveRecordStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return cast(LiveRecordStore, self._uow.repository(STORE_REPOSITORY_NAME))

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        outbox = TransactionalOutbox(self._uow)
        return await outbox.record_next(envelope, deduplication_key=deduplication_key)

    async def commit(self) -> None:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        await self._uow.commit()


def sql_scope_factory(database: Database) -> Callable[[], SqlTransactionScope]:
    return lambda: SqlTransactionScope(database)


# --------------------------------------------------------------------------- #
# Row mappers
# --------------------------------------------------------------------------- #


def _plan_from_row(row: Any) -> LiveExecutionPlanRow:
    return LiveExecutionPlanRow(
        plan_id=str(row.plan_id),
        episode_id=str(row.episode_id),
        episode_revision_id=str(row.episode_revision_id),
        preparation_revision=int(row.preparation_revision),
        plan_hash=str(row.plan_hash),
        status=str(row.status),
        director_role=str(row.director_role),
        recording_profile_json=str(row.recording_profile_json),
        scenes_json=str(row.scenes_json),
        actions_json=str(row.actions_json),
        payload_bundles_json=str(row.payload_bundles_json),
        source_workspace_hash=str(row.source_workspace_hash),
        created_at=_as_utc(row.created_at),
        frozen_at=_as_utc(row.frozen_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _take_from_row(row: Any) -> RecordingTakeRow:
    return RecordingTakeRow(
        take_id=str(row.take_id),
        execution_plan_id=str(row.execution_plan_id),
        execution_plan_hash=str(row.execution_plan_hash),
        episode_id=str(row.episode_id),
        status=str(row.status),
        started_at=_as_utc(row.started_at),
        ended_at=_as_utc(row.ended_at),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _segment_from_row(row: Any) -> RecordingSegmentRow:
    return RecordingSegmentRow(
        segment_id=str(row.segment_id),
        take_id=str(row.take_id),
        segment_index=int(row.segment_index),
        file_token=str(row.file_token),
        started_at=_as_utc(row.started_at),
        ended_at=_as_utc(row.ended_at),
        duration_sec=float(row.duration_sec) if row.duration_sec is not None else None,
        is_playable=bool(row.is_playable),
        manifest_json=str(row.manifest_json),
    )


def _event_from_row(row: Any) -> RecordingEventRow:
    def _v(key: str) -> Any:
        try:
            return row[key]
        except Exception:
            return getattr(row, key)

    return RecordingEventRow(
        take_id=str(_v("take_id")),
        seq=int(_v("seq")),
        event_type=str(_v("event_type")),
        t=float(_v("t")),
        scene_id=str(_v("scene_id")) if _v("scene_id") is not None else None,
        cue_id=str(_v("cue_id")) if _v("cue_id") is not None else None,
        action_id=str(_v("action_id")) if _v("action_id") is not None else None,
        segment_id=str(_v("segment_id")) if _v("segment_id") is not None else None,
        execution_id=str(_v("execution_id")) if _v("execution_id") is not None else None,
        marker_type=str(_v("marker_type")) if _v("marker_type") is not None else None,
        detail=str(_v("detail")),
        payload_json=str(_v("payload_json")),
        occurred_at=_as_utc(_v("occurred_at")),
    )


def _director_from_row(row: Any) -> DirectorSessionRow:
    return DirectorSessionRow(
        session_id=str(row.session_id),
        execution_plan_id=str(row.execution_plan_id),
        execution_plan_hash=str(row.execution_plan_hash),
        provider_id=str(row.provider_id) if row.provider_id is not None else None,
        model_id=str(row.model_id) if row.model_id is not None else None,
        connection_state=str(row.connection_state),
        started_at=_as_utc(row.started_at),
        expires_at=_as_utc(row.expires_at),
        updated_at=_as_utc(row.updated_at),
        metadata_json=str(row.metadata_json),
    )
