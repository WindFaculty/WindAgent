"""Phase 5 unit tests: TransactionScope lifecycle and old-system semantics."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from windagent.platform.persistence import (
    IsolationLevel,
    TransactionOutcome,
    TransactionScope,
    TransactionScopeError,
)

_METADATA = MetaData()
NOTES = Table(
    "notes",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(100), nullable=False),
)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(_METADATA.create_all)
    yield engine
    await engine.dispose()


async def _titles(connection: AsyncConnection) -> list[str]:
    rows = await connection.execute(select(NOTES.c.title))
    return list(rows.scalars().all())


async def test_commit_persists_work(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        async with TransactionScope(connection) as scope:
            await connection.execute(insert(NOTES).values(title="committed"))
            await scope.commit()
        assert scope.outcome is TransactionOutcome.COMMITTED

    async with engine.connect() as connection:
        assert await _titles(connection) == ["committed"]


async def test_exception_rolls_back_and_propagates(engine: AsyncEngine) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with engine.connect() as connection:
            async with TransactionScope(connection):
                await connection.execute(insert(NOTES).values(title="doomed"))
                raise RuntimeError("boom")
    async with engine.connect() as connection:
        assert await _titles(connection) == []


async def test_uncommitted_work_is_discarded_not_silently_committed(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        async with TransactionScope(connection) as scope:
            await connection.execute(insert(NOTES).values(title="forgotten"))
            # no explicit commit
        assert scope.outcome is TransactionOutcome.ROLLED_BACK

    async with engine.connect() as connection:
        assert await _titles(connection) == []


async def test_explicit_rollback_discards_work(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        async with TransactionScope(connection) as scope:
            await connection.execute(insert(NOTES).values(title="dropped"))
            await scope.rollback()
        assert scope.outcome is TransactionOutcome.ROLLED_BACK

    async with engine.connect() as connection:
        assert await _titles(connection) == []


async def test_scope_rejects_an_already_active_transaction(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.begin()
        with pytest.raises(TransactionScopeError, match="own its transaction boundary"):
            async with TransactionScope(connection):
                pass


async def test_operations_after_terminal_outcome_are_rejected(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        async with TransactionScope(connection) as scope:
            await scope.rollback()
            with pytest.raises(TransactionScopeError, match="commit"):
                await scope.commit()


async def test_isolation_level_is_forwarded_to_the_connection(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        async with TransactionScope(
            connection, isolation_level=IsolationLevel.SERIALIZABLE
        ) as scope:
            await connection.execute(insert(NOTES).values(title="serial"))
            await scope.commit()

    async with engine.connect() as connection:
        assert await _titles(connection) == ["serial"]
