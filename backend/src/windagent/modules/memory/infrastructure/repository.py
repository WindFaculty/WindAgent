"""SQL adapter for the Memory store (Phase 14)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent.kernel.events import EventEnvelope
from windagent.platform.events.outbox import TransactionalOutbox
from windagent.platform.persistence.database import Database
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

from ..application.models import MemoryRecordRow
from ..application.ports import MemoryStore
from ..domain.errors import MemoryConflictError, MemoryNotFoundError, MemoryStaleVersionError
from ..domain.models import MemoryRecord
from ..domain.scope import MemoryScope
from .tables import memory_records_table

STORE_REPOSITORY_NAME = "memory_store"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _row_to_model(row: Any) -> MemoryRecordRow:
    return MemoryRecordRow(
        memory_id=row.memory_id,
        scope=row.scope,
        key=row.key,
        project_id=row.project_id,
        session_id=row.session_id,
        value_json=row.value_json,
        provenance_source=row.provenance_source,
        tags_json=row.tags_json,
        ttl_seconds=row.ttl_seconds,
        content_hash=row.content_hash,
        learning_metadata_json=row.learning_metadata_json,
        version=row.version,
        optimistic_version=row.optimistic_version,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def make_store(session: AsyncSession) -> SqlMemoryStore:
    return SqlMemoryStore(session)


class SqlMemoryStore(MemoryStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        scope: str,
        key: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> MemoryRecordRow | None:
        stmt = select(memory_records_table).where(
            memory_records_table.c.scope == scope,
            memory_records_table.c.key == key,
        )
        if project_id is not None:
            stmt = stmt.where(memory_records_table.c.project_id == project_id)
        else:
            stmt = stmt.where(memory_records_table.c.project_id.is_(None))

        if session_id is not None:
            stmt = stmt.where(memory_records_table.c.session_id == session_id)
        else:
            stmt = stmt.where(memory_records_table.c.session_id.is_(None))

        res = await self._session.execute(stmt)
        row = res.first()
        return _row_to_model(row) if row is not None else None

    async def get_by_id(self, memory_id: str) -> MemoryRecordRow | None:
        stmt = select(memory_records_table).where(
            memory_records_table.c.memory_id == memory_id
        )
        res = await self._session.execute(stmt)
        row = res.first()
        return _row_to_model(row) if row is not None else None

    async def get_by_hash(self, content_hash: str) -> MemoryRecordRow | None:
        stmt = select(memory_records_table).where(
            memory_records_table.c.content_hash == content_hash
        )
        res = await self._session.execute(stmt)
        row = res.first()
        return _row_to_model(row) if row is not None else None

    async def insert(self, row: MemoryRecordRow) -> MemoryRecordRow:
        exists = await self.get_by_id(row.memory_id)
        if exists is not None:
            raise MemoryConflictError(f"Memory record already exists: {row.memory_id}")

        await self._session.execute(
            insert(memory_records_table).values(
                memory_id=row.memory_id,
                scope=row.scope,
                key=row.key,
                project_id=row.project_id,
                session_id=row.session_id,
                value_json=row.value_json,
                provenance_source=row.provenance_source,
                tags_json=row.tags_json,
                ttl_seconds=row.ttl_seconds,
                content_hash=row.content_hash,
                learning_metadata_json=row.learning_metadata_json,
                version=row.version,
                optimistic_version=row.optimistic_version,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
            )
        )
        return row

    async def update(self, row: MemoryRecordRow, expected_version: int) -> MemoryRecordRow:
        stmt = (
            update(memory_records_table)
            .where(
                memory_records_table.c.memory_id == row.memory_id,
                memory_records_table.c.optimistic_version == expected_version,
            )
            .values(
                scope=row.scope,
                key=row.key,
                project_id=row.project_id,
                session_id=row.session_id,
                value_json=row.value_json,
                provenance_source=row.provenance_source,
                tags_json=row.tags_json,
                ttl_seconds=row.ttl_seconds,
                content_hash=row.content_hash,
                learning_metadata_json=row.learning_metadata_json,
                version=row.version,
                optimistic_version=row.optimistic_version,
                updated_at=_as_utc(row.updated_at),
            )
        )
        result = await self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", None)
        if not rowcount or rowcount == 0:
            existing = await self.get_by_id(row.memory_id)
            if existing is None:
                raise MemoryNotFoundError(f"Memory record not found: {row.memory_id}")
            raise MemoryStaleVersionError(
                f"Memory record conflict for {row.memory_id}: expected {expected_version}, got {existing.optimistic_version}"
            )
        return row

    async def delete(self, memory_id: str) -> bool:
        stmt = delete(memory_records_table).where(
            memory_records_table.c.memory_id == memory_id
        )
        result = await self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", None)
        return bool(rowcount and rowcount > 0)

    async def delete_by_scope_key(
        self,
        scope: str,
        key: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> bool:
        existing = await self.get(scope, key, project_id, session_id)
        if existing is None:
            return False
        return await self.delete(existing.memory_id)

    async def list_records(
        self,
        scope: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecordRow]:
        stmt = select(memory_records_table)
        if scope is not None:
            stmt = stmt.where(memory_records_table.c.scope == scope)
        if project_id is not None:
            stmt = stmt.where(memory_records_table.c.project_id == project_id)
        if session_id is not None:
            stmt = stmt.where(memory_records_table.c.session_id == session_id)

        stmt = stmt.order_by(memory_records_table.c.updated_at.desc()).limit(limit).offset(offset)
        res = await self._session.execute(stmt)
        return [_row_to_model(r) for r in res.all()]

    async def count_by_scope(self) -> dict[str, int]:
        stmt = select(
            memory_records_table.c.scope,
            func.count(memory_records_table.c.memory_id).label("count"),
        ).group_by(memory_records_table.c.scope)
        res = await self._session.execute(stmt)
        return {str(row[0]): int(row[1]) for row in res.all()}

    async def evict_expired(
        self,
        reference_time: datetime | None = None,
        scope: str | None = None,
    ) -> int:
        ref = reference_time or datetime.now(UTC)
        stmt = select(memory_records_table)
        if scope is not None:
            stmt = stmt.where(memory_records_table.c.scope == scope)
        res = await self._session.execute(stmt)
        all_rows = [_row_to_model(r) for r in res.all()]

        to_delete: list[str] = []
        for row in all_rows:
            try:
                scope_enum = MemoryScope(row.scope)
            except ValueError:
                scope_enum = MemoryScope.WORKING
            rec = MemoryRecord(
                id=row.memory_id,
                scope=scope_enum,
                key=row.key,
                value=None,
                provenance_source=row.provenance_source,
                ttl_seconds=row.ttl_seconds,
                created_at=row.created_at or ref,
                updated_at=row.updated_at or ref,
            )
            if rec.is_expired(reference_time=ref):
                to_delete.append(row.memory_id)

        if to_delete:
            del_stmt = delete(memory_records_table).where(
                memory_records_table.c.memory_id.in_(to_delete)
            )
            del_res = await self._session.execute(del_stmt)
            rowcount = getattr(del_res, "rowcount", None)
            return int(rowcount or 0)
        return 0


class SqlTransactionScope:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):
            raise TypeError("transaction scope requires a SQL unit of work")
        uow.register_repository(STORE_REPOSITORY_NAME, make_store)
        self._uow = uow
        await uow.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool:
        if self._uow is not None:
            await self._uow.__aexit__(exc_type, exc_value, None)
            self._uow = None
        return False

    @property
    def store(self) -> MemoryStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return cast(MemoryStore, self._uow.repository(STORE_REPOSITORY_NAME))

    async def record_event(self, event: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        outbox = TransactionalOutbox(self._uow)
        return await outbox.record_next(event, deduplication_key=deduplication_key)

    async def commit(self) -> None:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        await self._uow.commit()

    async def rollback(self) -> None:
        if self._uow is not None:
            await self._uow.rollback()


def sql_scope_factory(database: Database) -> Callable[[], SqlTransactionScope]:
    return lambda: SqlTransactionScope(database)
