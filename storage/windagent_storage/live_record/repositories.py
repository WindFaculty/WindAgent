"""Live Record repository adapters (live_record.contract/v0.1).

Async SQLAlchemy adapters behind the ``*RepositoryPort`` protocols in
``windagent_core.contracts.live_record.ports``. Conventions follow
``windagent_storage.studio.repositories``:

- Optimistic concurrency on mutable rows via guarded UPDATE on
  ``optimistic_version``; constraint violations map to domain errors.
- Plan scenes/actions/profile/bundles are JSON columns mapped 1:1 to the
  frozen pydantic value objects.
- Timeline events are append-only with a per-take monotonic ``seq``.

Unlike the studio adapters these sessions may run with ``autoflush=False``
and perform read-after-write inside one use case (preparation-revision
allocation, event sequence assignment), so every write method ends with a
``flush()`` — staged SQL becomes visible to later queries in the SAME
transaction while the unit of work still controls commit/rollback.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.contracts.live_record.errors import LiveRecordValidationError
from windagent_core.contracts.live_record.ids import (
    DirectorSessionId,
    LiveExecutionPlanId,
    RecordingTakeId,
)
from windagent_core.domain.live_record.lifecycle import LiveExecutionPlanStatus
from windagent_core.domain.live_record.plan import (
    ExpectedVisualState,
    LiveExecutionPlan,
    PreparedAction,
    RecordingProfile,
    RecordingScene,
)
from windagent_core.domain.live_record.runtime import (
    DirectorSessionRecord,
    RecordingEventRecord,
    RecordingSegmentRecord,
    RecordingTakeRecord,
)
from windagent_storage.orm.live_record_models import (
    DirectorSessionORM,
    LiveExecutionPlanORM,
    LiveRecordEventORM,
    LiveRecordSegmentORM,
    LiveRecordTakeORM,
)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=None) if dt and dt.tzinfo else dt


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _loads(raw: Optional[str], fallback: object) -> object:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return fallback


# ─── Plan mappers ────────────────────────────────────────────────────────────


def _plan_to_orm(plan: LiveExecutionPlan) -> dict:
    return {
        "plan_id": str(plan.plan_id),
        "episode_id": plan.episode_id,
        "episode_revision_id": plan.episode_revision_id,
        "preparation_revision": plan.preparation_revision,
        "plan_hash": plan.plan_hash,
        "status": plan.status.value,
        "director_role": plan.director_role,
        "recording_profile_json": _dumps(plan.recording_profile.model_dump()),
        "scenes_json": _dumps([scene.model_dump() for scene in plan.scenes]),
        "actions_json": _dumps([action.model_dump() for action in plan.actions]),
        "payload_bundles_json": _dumps(plan.payload_bundles),
        "source_workspace_hash": plan.source_workspace_hash,
        "created_at": _naive(plan.created_at),
        "frozen_at": _naive(plan.frozen_at),
        "optimistic_version": plan.optimistic_version,
    }


def _plan_from_orm(row: LiveExecutionPlanORM) -> LiveExecutionPlan:
    profile_raw = _loads(row.recording_profile_json, {})
    scenes_raw = _loads(row.scenes_json, [])
    actions_raw = _loads(row.actions_json, [])
    bundles_raw = _loads(row.payload_bundles_json, {})
    return LiveExecutionPlan.model_validate(
        {
            "plan_id": LiveExecutionPlanId(row.plan_id),
            "episode_id": row.episode_id,
            "episode_revision_id": row.episode_revision_id,
            "preparation_revision": row.preparation_revision,
            "plan_hash": row.plan_hash,
            "status": LiveExecutionPlanStatus(row.status),
            "director_role": row.director_role,
            "recording_profile": RecordingProfile.model_validate(profile_raw),
            "scenes": [RecordingScene.model_validate(s) for s in scenes_raw],
            "actions": [
                PreparedAction.model_validate(
                    {**a, "expected_after": ExpectedVisualState.model_validate(a["expected_after"]) if a.get("expected_after") else None}
                )
                for a in actions_raw
            ],
            "payload_bundles": bundles_raw if isinstance(bundles_raw, dict) else {},
            "source_workspace_hash": row.source_workspace_hash,
            "created_at": _aware(row.created_at),
            "frozen_at": _aware(row.frozen_at),
            "optimistic_version": row.optimistic_version,
        }
    )


class SqlLiveExecutionPlanRepository:
    """Canonical persistence for immutable-after-FROZEN execution plans."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, plan_id: LiveExecutionPlanId) -> Optional[LiveExecutionPlan]:
        row = (
            await self.session.execute(
                select(LiveExecutionPlanORM).where(LiveExecutionPlanORM.plan_id == str(plan_id))
            )
        ).scalar_one_or_none()
        return _plan_from_orm(row) if row is not None else None

    async def save(self, plan: LiveExecutionPlan) -> LiveExecutionPlan:
        existing = (
            await self.session.execute(
                select(LiveExecutionPlanORM).where(LiveExecutionPlanORM.plan_id == str(plan.plan_id))
            )
        ).scalar_one_or_none()
        if existing is None:
            self.session.add(LiveExecutionPlanORM(**_plan_to_orm(plan)))
            await self.session.flush()
            return plan
        expected = plan.optimistic_version - 1
        result = await self.session.execute(
            update(LiveExecutionPlanORM)
            .where(LiveExecutionPlanORM.plan_id == str(plan.plan_id))
            .where(LiveExecutionPlanORM.optimistic_version == expected)
            .values(**_plan_to_orm(plan))
        )
        if result.rowcount == 0:
            raise LiveRecordValidationError(
                "Execution plan changed since it was read; optimistic version mismatch.",
                details={
                    "plan_id": str(plan.plan_id),
                    "expected_version": expected,
                    "current_version": existing.optimistic_version,
                },
            )
        await self.session.flush()
        return plan

    async def list_by_episode(self, episode_id: str) -> List[LiveExecutionPlan]:
        stmt = (
            select(LiveExecutionPlanORM)
            .where(LiveExecutionPlanORM.episode_id == episode_id)
            .order_by(LiveExecutionPlanORM.preparation_revision.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_plan_from_orm(r) for r in rows]

    async def next_preparation_revision(self, episode_id: str) -> int:
        current = (
            await self.session.execute(
                select(func.max(LiveExecutionPlanORM.preparation_revision)).where(
                    LiveExecutionPlanORM.episode_id == episode_id
                )
            )
        ).scalar_one_or_none()
        return (current or 0) + 1


# ─── Runtime record repositories ─────────────────────────────────────────────


def _take_to_orm(take: RecordingTakeRecord) -> dict:
    return {
        "take_id": take.take_id,
        "execution_plan_id": take.execution_plan_id,
        "execution_plan_hash": take.execution_plan_hash,
        "episode_id": take.episode_id,
        "status": take.session_status,
        "started_at": _naive(take.started_at),
        "ended_at": _naive(take.ended_at),
        "optimistic_version": take.optimistic_version,
        "metadata_json": _dumps(take.metadata),
    }


def _take_from_orm(row: LiveRecordTakeORM) -> RecordingTakeRecord:
    return RecordingTakeRecord.model_validate(
        {
            "take_id": row.take_id,
            "execution_plan_id": row.execution_plan_id,
            "execution_plan_hash": row.execution_plan_hash,
            "episode_id": row.episode_id,
            "session_status": row.status,
            "started_at": _aware(row.started_at),
            "ended_at": _aware(row.ended_at),
            "optimistic_version": row.optimistic_version,
            "metadata": _loads(row.metadata_json, {}),
        }
    )


class SqlRecordingTakeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, take_id: RecordingTakeId) -> Optional[RecordingTakeRecord]:
        row = (
            await self.session.execute(
                select(LiveRecordTakeORM).where(LiveRecordTakeORM.take_id == str(take_id))
            )
        ).scalar_one_or_none()
        return _take_from_orm(row) if row is not None else None

    async def save(self, take: RecordingTakeRecord) -> RecordingTakeRecord:
        existing = (
            await self.session.execute(
                select(LiveRecordTakeORM).where(LiveRecordTakeORM.take_id == take.take_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            self.session.add(LiveRecordTakeORM(**_take_to_orm(take)))
            await self.session.flush()
            return take
        expected = take.optimistic_version - 1
        result = await self.session.execute(
            update(LiveRecordTakeORM)
            .where(LiveRecordTakeORM.take_id == take.take_id)
            .where(LiveRecordTakeORM.optimistic_version == expected)
            .values(**_take_to_orm(take))
        )
        if result.rowcount == 0:
            raise LiveRecordValidationError(
                "Recording take changed since it was read; optimistic version mismatch.",
                details={"take_id": take.take_id},
            )
        await self.session.flush()
        return take

    async def list_by_plan(self, execution_plan_id: str) -> List[RecordingTakeRecord]:
        stmt = (
            select(LiveRecordTakeORM)
            .where(LiveRecordTakeORM.execution_plan_id == execution_plan_id)
            .order_by(LiveRecordTakeORM.created_at)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_take_from_orm(r) for r in rows]


class SqlRecordingSegmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, segment: RecordingSegmentRecord) -> RecordingSegmentRecord:
        existing = (
            await self.session.execute(
                select(LiveRecordSegmentORM).where(
                    LiveRecordSegmentORM.segment_id == segment.segment_id
                )
            )
        ).scalar_one_or_none()
        values = {
            "segment_id": segment.segment_id,
            "take_id": segment.take_id,
            "segment_index": segment.segment_index,
            "file_token": segment.file_token,
            "started_at": _naive(segment.started_at),
            "ended_at": _naive(segment.ended_at),
            "duration_sec": segment.duration_sec,
            "is_playable": segment.is_playable,
            "manifest_json": _dumps(segment.manifest),
        }
        if existing is None:
            self.session.add(LiveRecordSegmentORM(**values))
            await self.session.flush()
            return segment
        for key, value in values.items():
            setattr(existing, key, value)
        await self.session.flush()
        return segment

    async def list_by_take(self, take_id: str) -> List[RecordingSegmentRecord]:
        stmt = (
            select(LiveRecordSegmentORM)
            .where(LiveRecordSegmentORM.take_id == take_id)
            .order_by(LiveRecordSegmentORM.segment_index)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        def _from(r: LiveRecordSegmentORM) -> RecordingSegmentRecord:
            return RecordingSegmentRecord.model_validate(
                {
                    "segment_id": r.segment_id,
                    "take_id": r.take_id,
                    "segment_index": r.segment_index,
                    "file_token": r.file_token,
                    "started_at": _aware(r.started_at),
                    "ended_at": _aware(r.ended_at),
                    "duration_sec": r.duration_sec,
                    "is_playable": r.is_playable,
                    "manifest": _loads(r.manifest_json, {}),
                }
            )

        return [_from(r) for r in rows]


class SqlRecordingEventRepository:
    """Append-only timeline store with per-take monotonic sequence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(self, event: RecordingEventRecord) -> RecordingEventRecord:
        # Flush first so previously staged events count toward the max-seq scan.
        await self.session.flush()
        next_seq = (
            await self.session.execute(
                select(func.max(LiveRecordEventORM.seq)).where(
                    LiveRecordEventORM.take_id == event.take_id
                )
            )
        ).scalar_one_or_none()
        seq = (next_seq or 0) + 1
        self.session.add(
            LiveRecordEventORM(
                take_id=event.take_id,
                seq=seq,
                event_type=event.event_type,
                t=event.t,
                scene_id=event.scene_id,
                cue_id=event.cue_id,
                action_id=event.action_id,
                segment_id=event.segment_id,
                execution_id=event.execution_id,
                marker_type=event.marker_type,
                detail=event.detail,
                payload_json=_dumps(event.payload),
            )
        )
        await self.session.flush()
        return event.model_copy(update={"seq": seq})

    async def list_by_take(self, take_id: str) -> List[RecordingEventRecord]:
        stmt = (
            select(LiveRecordEventORM)
            .where(LiveRecordEventORM.take_id == take_id)
            .order_by(LiveRecordEventORM.seq)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        def _from(r: LiveRecordEventORM) -> RecordingEventRecord:
            return RecordingEventRecord.model_validate(
                {
                    "take_id": r.take_id,
                    "seq": r.seq,
                    "event_type": r.event_type,
                    "t": r.t,
                    "scene_id": r.scene_id,
                    "cue_id": r.cue_id,
                    "action_id": r.action_id,
                    "segment_id": r.segment_id,
                    "execution_id": r.execution_id,
                    "marker_type": r.marker_type,
                    "detail": r.detail,
                    "payload": _loads(r.payload_json, {}),
                }
            )

        return [_from(r) for r in rows]


class SqlDirectorSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, session_id: DirectorSessionId) -> Optional[DirectorSessionRecord]:
        row = (
            await self.session.execute(
                select(DirectorSessionORM).where(DirectorSessionORM.session_id == str(session_id))
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return DirectorSessionRecord.model_validate(
            {
                "session_id": row.session_id,
                "execution_plan_id": row.execution_plan_id,
                "execution_plan_hash": row.execution_plan_hash,
                "provider_id": row.provider_id,
                "model_id": row.model_id,
                "connection_state": row.connection_state,
                "started_at": _aware(row.started_at),
                "expires_at": _aware(row.expires_at),
                "metadata": _loads(row.metadata_json, {}),
            }
        )

    async def save(self, session: DirectorSessionRecord) -> DirectorSessionRecord:
        existing = (
            await self.session.execute(
                select(DirectorSessionORM).where(DirectorSessionORM.session_id == session.session_id)
            )
        ).scalar_one_or_none()
        values = {
            "session_id": session.session_id,
            "execution_plan_id": session.execution_plan_id,
            "execution_plan_hash": session.execution_plan_hash,
            "provider_id": session.provider_id,
            "model_id": session.model_id,
            "connection_state": session.connection_state,
            "started_at": _naive(session.started_at),
            "expires_at": _naive(session.expires_at),
            "metadata_json": _dumps(session.metadata),
        }
        if existing is None:
            self.session.add(DirectorSessionORM(**values))
            await self.session.flush()
            return session
        for key, value in values.items():
            setattr(existing, key, value)
        await self.session.flush()
        return session


# ─── Factory functions (allowlisted construction points) ─────────────────────


def create_sql_live_execution_plan_repository(session: AsyncSession) -> SqlLiveExecutionPlanRepository:
    return SqlLiveExecutionPlanRepository(session)


def create_sql_recording_take_repository(session: AsyncSession) -> SqlRecordingTakeRepository:
    return SqlRecordingTakeRepository(session)


def create_sql_recording_segment_repository(session: AsyncSession) -> SqlRecordingSegmentRepository:
    return SqlRecordingSegmentRepository(session)


def create_sql_recording_event_repository(session: AsyncSession) -> SqlRecordingEventRepository:
    return SqlRecordingEventRepository(session)


def create_sql_director_session_repository(session: AsyncSession) -> SqlDirectorSessionRepository:
    return SqlDirectorSessionRepository(session)
