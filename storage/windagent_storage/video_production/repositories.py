"""
Repositories for Video Production API V2 Foundation (Stage B).

Provides durable async SQLAlchemy repository ports for Projects, Revisions,
Idempotency Records, Production Events, and Read Models.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_storage.video_production.video_production_models import (
    IdempotencyRecordORM,
    ProductionEventORM,
    ProductionProjectORM,
    ProductionRevisionORM,
    ProjectionCheckpointORM,
    WorkspaceReadModelORM,
)


class ProductionProjectRepository:
    """Repository for video production projects and revisions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        stmt = select(ProductionProjectORM).where(ProductionProjectORM.id == project_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "active_revision_id": row.active_revision_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def save_project(
        self, project_id: str, name: str, status: str, active_revision_id: str
    ) -> dict[str, Any]:
        stmt = select(ProductionProjectORM).where(ProductionProjectORM.id == project_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if not row:
            row = ProductionProjectORM(
                id=project_id,
                name=name,
                status=status,
                active_revision_id=active_revision_id,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.name = name
            row.status = status
            row.active_revision_id = active_revision_id
            row.updated_at = now

        return {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "active_revision_id": row.active_revision_id,
            "updated_at": row.updated_at.isoformat(),
        }

    async def get_revision(self, revision_id: str) -> dict[str, Any] | None:
        stmt = select(ProductionRevisionORM).where(ProductionRevisionORM.id == revision_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "project_id": row.project_id,
            "parent_revision_id": row.parent_revision_id,
            "status": row.status,
            "content_hash": row.content_hash,
            "sequence": row.sequence,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def save_revision(
        self,
        revision_id: str,
        project_id: str,
        parent_revision_id: str | None,
        status: str,
        content_hash: str,
        sequence: int,
    ) -> dict[str, Any]:
        stmt = select(ProductionRevisionORM).where(ProductionRevisionORM.id == revision_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if not row:
            row = ProductionRevisionORM(
                id=revision_id,
                project_id=project_id,
                parent_revision_id=parent_revision_id,
                status=status,
                content_hash=content_hash,
                sequence=sequence,
                created_at=now,
            )
            self.session.add(row)
        else:
            row.status = status
            row.content_hash = content_hash
            row.sequence = sequence

        return {
            "id": row.id,
            "project_id": row.project_id,
            "parent_revision_id": row.parent_revision_id,
            "status": row.status,
            "content_hash": row.content_hash,
            "sequence": row.sequence,
        }


class IdempotencyRepository:
    """Repository for command idempotency checks and caching."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_record(self, scope: str, idempotency_key: str) -> dict[str, Any] | None:
        stmt = select(IdempotencyRecordORM).where(
            IdempotencyRecordORM.scope == scope,
            IdempotencyRecordORM.idempotency_key == idempotency_key,
        )
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "scope": row.scope,
            "idempotency_key": row.idempotency_key,
            "request_hash": row.request_hash,
            "response": json.loads(row.response_json or "{}"),
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def save_record(
        self,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        response: dict[str, Any],
        status: str = "COMPLETED",
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        existing = await self.get_record(scope, idempotency_key)
        if existing:
            return existing

        record_id = f"idemp_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        row = IdempotencyRecordORM(
            id=record_id,
            scope=scope,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_json=json.dumps(response),
            status=status,
            created_at=now,
            expires_at=expires_at,
        )
        self.session.add(row)
        return {
            "id": record_id,
            "scope": scope,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "response": response,
            "status": status,
        }


class ProductionEventRepository:
    """Repository for appending and replaying production domain events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append_event(
        self,
        event_id: str,
        sequence: int,
        project_id: str,
        revision_id: str,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        row = ProductionEventORM(
            event_id=event_id,
            sequence=sequence,
            project_id=project_id,
            revision_id=revision_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload_json=json.dumps(payload),
            created_at=now,
        )
        self.session.add(row)
        return {
            "event_id": event_id,
            "sequence": sequence,
            "project_id": project_id,
            "revision_id": revision_id,
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "payload": payload,
            "occurred_at": now.isoformat(),
        }

    async def get_events(
        self, project_id: str, min_sequence: int = 0, limit: int = 500
    ) -> list[dict[str, Any]]:
        stmt = (
            select(ProductionEventORM)
            .where(
                ProductionEventORM.project_id == project_id,
                ProductionEventORM.sequence > min_sequence,
            )
            .order_by(ProductionEventORM.sequence.asc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        rows = res.scalars().all()
        return [
            {
                "event_id": row.event_id,
                "sequence": row.sequence,
                "project_id": row.project_id,
                "revision_id": row.revision_id,
                "event_type": row.event_type,
                "aggregate_type": row.aggregate_type,
                "aggregate_id": row.aggregate_id,
                "payload": json.loads(row.payload_json or "{}"),
                "occurred_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    async def get_max_sequence(self, project_id: str | None = None) -> int:
        stmt = select(func.max(ProductionEventORM.sequence))
        if project_id:
            stmt = stmt.where(ProductionEventORM.project_id == project_id)
        res = await self.session.execute(stmt)
        val = res.scalar()
        return val if val is not None else 0


class WorkspaceReadModelRepository:
    """Repository for workspace snapshots and projection checkpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_read_model(self, project_id: str) -> dict[str, Any] | None:
        stmt = select(WorkspaceReadModelORM).where(WorkspaceReadModelORM.project_id == project_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        if not row:
            return None
        projection = json.loads(row.projection_json or "{}")
        projection["current_sequence"] = row.current_sequence
        return projection

    async def save_read_model(
        self, project_id: str, projection: dict[str, Any], current_sequence: int
    ) -> None:
        stmt = select(WorkspaceReadModelORM).where(WorkspaceReadModelORM.project_id == project_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if not row:
            row = WorkspaceReadModelORM(
                project_id=project_id,
                projection_json=json.dumps(projection),
                current_sequence=current_sequence,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.projection_json = json.dumps(projection)
            row.current_sequence = current_sequence
            row.updated_at = now

    async def get_checkpoint(self, projector_id: str) -> int:
        stmt = select(ProjectionCheckpointORM).where(
            ProjectionCheckpointORM.projector_id == projector_id
        )
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        return row.last_sequence if row else 0

    async def save_checkpoint(self, projector_id: str, last_sequence: int) -> None:
        stmt = select(ProjectionCheckpointORM).where(
            ProjectionCheckpointORM.projector_id == projector_id
        )
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if not row:
            row = ProjectionCheckpointORM(
                projector_id=projector_id,
                last_sequence=last_sequence,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.last_sequence = last_sequence
            row.updated_at = now
