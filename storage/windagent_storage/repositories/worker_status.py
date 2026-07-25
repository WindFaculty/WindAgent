"""SQL worker heartbeat adapter for Core worker ports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from windagent_core.contracts.workers import WorkerHealth, WorkerHeartbeat, WorkerStatus
from windagent_storage.orm.v2_orchestration_models import WorkerRegistrationORM


class SqlWorkerHeartbeatRepository:
    def __init__(self, session_factory: Any):
        self._session_factory = session_factory

    async def get_active_workers(self, stale_after_seconds: int) -> list[WorkerHeartbeat]:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=stale_after_seconds)
        async with self._session_factory() as session:
            result = await session.execute(
                select(WorkerRegistrationORM).where(
                    WorkerRegistrationORM.last_heartbeat_at >= cutoff,
                    WorkerRegistrationORM.health != WorkerHealth.UNHEALTHY.value,
                )
            )
            return [self._to_heartbeat(row) for row in result.scalars().all()]

    async def record_heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        async with self._session_factory() as session:
            row = await session.get(WorkerRegistrationORM, heartbeat.worker_id)
            values = {
                "runtime_type": heartbeat.runtime_type,
                "health": heartbeat.health.value,
                "active_leases": heartbeat.active_leases,
                "last_heartbeat_at": heartbeat.last_heartbeat_at.replace(tzinfo=None),
                "metadata_json": json.dumps(dict(heartbeat.metadata)),
            }
            if row is None:
                session.add(WorkerRegistrationORM(worker_id=heartbeat.worker_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()

    @staticmethod
    def _to_heartbeat(row: WorkerRegistrationORM) -> WorkerHeartbeat:
        timestamp = row.last_heartbeat_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return WorkerHeartbeat(
            worker_id=row.worker_id,
            runtime_type=row.runtime_type,
            health=WorkerHealth(row.health),
            active_leases=row.active_leases,
            last_heartbeat_at=timestamp,
            metadata=json.loads(row.metadata_json or "{}"),
        )


class SqlWorkerStatusQuery:
    def __init__(self, repository: SqlWorkerHeartbeatRepository):
        self._repository = repository

    async def get_status(self, stale_after_seconds: int = 30) -> WorkerStatus:
        workers = tuple(await self._repository.get_active_workers(stale_after_seconds))
        active_leases_count = sum(worker.active_leases for worker in workers)

        if hasattr(self._repository, "_session_factory") and self._repository._session_factory:
            now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
            try:
                async with self._repository._session_factory() as session:
                    from sqlalchemy import func
                    from windagent_storage.orm.v2_orchestration_models import ExecutionLeaseORM
                    stmt = select(func.count(ExecutionLeaseORM.lease_id)).where(
                        ExecutionLeaseORM.status == "active",
                        ExecutionLeaseORM.expires_at >= now_naive,
                    )
                    res = await session.execute(stmt)
                    sql_lease_count = res.scalar() or 0
                    if sql_lease_count > 0:
                        active_leases_count = sql_lease_count
            except Exception:
                pass

        return WorkerStatus(
            available=bool(workers),
            active_workers=len(workers),
            active_leases=active_leases_count,
            workers=workers,
        )