"""SQL concrete repository for the namespaced durable V3 resource authority.

Implements ``windagent_core.contracts.repositories.v3_resource_repository``.
All methods stage work on the supplied ``AsyncSession``; the caller owns the
transaction boundary (Unit of Work) so writes, idempotency lookup, and
optimistic concurrency share one transaction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.contracts.repositories.v3_resource_repository import (
    V3ResourceRepositoryPort,
)
from windagent_storage.orm.v3_models import V3ResourceORM


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row: V3ResourceORM) -> Dict[str, Any]:
    data = json.loads(row.data_json) if row.data_json else {}
    data["version"] = row.version
    data["created_at"] = row.created_at.isoformat() if row.created_at else ""
    data["updated_at"] = row.updated_at.isoformat() if row.updated_at else ""
    return data


class SQLV3ResourceRepository(V3ResourceRepositoryPort):
    """SQLAlchemy implementation of the namespaced V3 resource port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, namespace: str, resource_id: str) -> Optional[Dict[str, Any]]:
        row = (
            await self._session.execute(
                select(V3ResourceORM).where(
                    V3ResourceORM.namespace == namespace,
                    V3ResourceORM.resource_id == resource_id,
                )
            )
        ).scalar_one_or_none()
        return _row_to_dict(row) if row else None

    async def list(self, namespace: str) -> List[Dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(V3ResourceORM)
                .where(V3ResourceORM.namespace == namespace)
                .order_by(V3ResourceORM.updated_at.desc())
            )
        ).scalars().all()
        return [_row_to_dict(row) for row in rows]

    async def create(
        self,
        namespace: str,
        resource_id: str,
        data: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if idempotency_key:
            existing = await self.find_by_idempotency(namespace, idempotency_key)
            if existing is not None:
                return existing

        now = _utc_now()
        payload = {k: v for k, v in data.items() if k not in ("version", "created_at", "updated_at")}
        row = V3ResourceORM(
            namespace=namespace,
            resource_id=resource_id,
            data_json=json.dumps(payload),
            version=1,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError:
            # A concurrent create raced us on the unique (namespace, resource_id)
            # or (namespace, idempotency_key) constraint. Roll back the failed
            # insert and return the deterministic existing row instead of
            # surfacing a 500 under the uniqueness race.
            await self._session.rollback()
            if idempotency_key:
                existing = await self.find_by_idempotency(namespace, idempotency_key)
                if existing is not None:
                    return existing
            existing = await self.get(namespace, resource_id)
            if existing is not None:
                return existing
            raise
        return _row_to_dict(row)

    async def update(
        self,
        namespace: str,
        resource_id: str,
        data: Dict[str, Any],
        expected_version: int,
    ) -> Optional[Dict[str, Any]]:
        """Atomic compare-and-swap update.

        Uses a single ``UPDATE ... WHERE namespace/resource_id/version =
        expected_version`` statement so two concurrent transactions cannot both
        pass the version check. Exactly one row must change; otherwise the
        resource is missing or the version is stale and ``None`` is returned.
        """
        payload = {k: v for k, v in data.items() if k not in ("version", "created_at", "updated_at")}
        result = await self._session.execute(
            update(V3ResourceORM)
            .where(
                V3ResourceORM.namespace == namespace,
                V3ResourceORM.resource_id == resource_id,
                V3ResourceORM.version == expected_version,
            )
            .values(
                data_json=json.dumps(payload),
                version=V3ResourceORM.version + 1,
                updated_at=_utc_now(),
            )
        )
        if result.rowcount != 1:
            return None
        await self._session.flush()
        return await self.get(namespace, resource_id)

    async def delete(self, namespace: str, resource_id: str) -> bool:
        row = (
            await self._session.execute(
                select(V3ResourceORM).where(
                    V3ResourceORM.namespace == namespace,
                    V3ResourceORM.resource_id == resource_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def find_by_idempotency(
        self, namespace: str, idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        row = (
            await self._session.execute(
                select(V3ResourceORM).where(
                    V3ResourceORM.namespace == namespace,
                    V3ResourceORM.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return _row_to_dict(row) if row else None


__all__ = ["SQLV3ResourceRepository"]
