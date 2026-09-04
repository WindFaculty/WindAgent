"""Phase 5 unit tests: SqlUnitOfWork scope, repository composition, crash gates."""

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
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from windagent.platform.persistence import (
    CHECKPOINT_BEFORE_COMMIT,
    CHECKPOINT_BEFORE_ROLLBACK,
    SqlUnitOfWork,
    UnitOfWork,
    UnitOfWorkNotActiveError,
    UnitOfWorkStateError,
)

_METADATA = MetaData()
NOTES = Table(
    "notes",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(100), nullable=False),
)


class NoteRepository:
    """Session-bound repository standing in for a concrete module adapter."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, title: str) -> None:
        await self._session.execute(insert(NOTES).values(title=title))

    async def titles(self) -> list[str]:
        rows = await self._session.execute(select(NOTES.c.title))
        return list(rows.scalars().all())


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(_METADATA.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield factory
    await engine.dispose()


def build_unit_of_work(
    factory: async_sessionmaker[AsyncSession],
    **options: object,
) -> SqlUnitOfWork:
    unit_of_work = SqlUnitOfWork(factory, **options)  # type: ignore[arg-type]
    unit_of_work.register_repository("notes", NoteRepository)
    return unit_of_work


async def _persisted_titles(
    factory: async_sessionmaker[AsyncSession],
) -> list[str]:
    async with factory() as session:
        rows = await session.execute(select(NOTES.c.title))
        return list(rows.scalars().all())


async def test_commit_persists_and_rollback_discards(session_factory: async_sessionmaker[AsyncSession]) -> None:
    unit_of_work = build_unit_of_work(session_factory)
    async with unit_of_work:
        notes: NoteRepository = unit_of_work.repository("notes")
        await notes.add("kept")
        await unit_of_work.commit()
    assert await _persisted_titles(session_factory) == ["kept"]

    unit_of_work = build_unit_of_work(session_factory)
    async with unit_of_work:
        notes = unit_of_work.repository("notes")
        await notes.add("dropped")
        await unit_of_work.rollback()
    assert await _persisted_titles(session_factory) == ["kept"]


async def test_exception_inside_scope_rolls_back_and_propagates(session_factory: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(ValueError, match="boom"):
        async with build_unit_of_work(session_factory) as unit_of_work:
            notes: NoteRepository = unit_of_work.repository("notes")
            await notes.add("doomed")
            raise ValueError("boom")
    assert await _persisted_titles(session_factory) == []


async def test_uncommitted_scope_exit_discards_work(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with build_unit_of_work(session_factory) as unit_of_work:
        notes: NoteRepository = unit_of_work.repository("notes")
        await notes.add("forgotten")
    assert await _persisted_titles(session_factory) == []


async def test_repositories_are_session_scoped_and_cached(session_factory: async_sessionmaker[AsyncSession]) -> None:
    unit_of_work = build_unit_of_work(session_factory)
    async with unit_of_work:
        first: NoteRepository = unit_of_work.repository("notes")
        second: NoteRepository = unit_of_work.repository("notes")
        assert first is second
        await first.add("cached")


async def test_access_outside_the_scope_is_rejected(session_factory: async_sessionmaker[AsyncSession]) -> None:
    unit_of_work = build_unit_of_work(session_factory)
    with pytest.raises(UnitOfWorkNotActiveError):
        _ = unit_of_work.repository("notes")
    with pytest.raises(UnitOfWorkNotActiveError):
        _ = unit_of_work.session
    with pytest.raises(UnitOfWorkNotActiveError):
        await unit_of_work.commit()

    async with unit_of_work:
        assert unit_of_work.repository("notes") is not None
        with pytest.raises(KeyError):
            unit_of_work.repository("missing")

    with pytest.raises(UnitOfWorkNotActiveError):
        _ = unit_of_work.repository("notes")


def test_registration_rules_are_enforced(session_factory: async_sessionmaker[AsyncSession]) -> None:
    unit_of_work = SqlUnitOfWork(session_factory)
    assert isinstance(unit_of_work, UnitOfWork)

    unit_of_work.register_repository("notes", NoteRepository)
    with pytest.raises(ValueError, match="already registered"):
        unit_of_work.register_repository("notes", NoteRepository)
    with pytest.raises(TypeError):
        unit_of_work.register_repository("bad", "not-callable")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        unit_of_work.register_repository("   ", NoteRepository)


async def test_registering_after_entry_is_rejected(session_factory: async_sessionmaker[AsyncSession]) -> None:
    unit_of_work = build_unit_of_work(session_factory)
    async with unit_of_work:
        with pytest.raises(UnitOfWorkStateError, match="before the scope is entered"):
            unit_of_work.register_repository("other", NoteRepository)


async def test_double_entry_is_rejected(session_factory: async_sessionmaker[AsyncSession]) -> None:
    unit_of_work = build_unit_of_work(session_factory)
    await unit_of_work.__aenter__()
    try:
        with pytest.raises(UnitOfWorkStateError, match="already active"):
            await unit_of_work.__aenter__()
    finally:
        await unit_of_work.__aexit__(None, None, None)


async def test_checkpoint_hook_receives_named_gates(session_factory: async_sessionmaker[AsyncSession]) -> None:
    seen: list[str] = []
    unit_of_work = build_unit_of_work(session_factory, checkpoint_hook=seen.append)
    async with unit_of_work:
        await unit_of_work.commit()
        await unit_of_work.rollback()
    assert seen == [CHECKPOINT_BEFORE_COMMIT, CHECKPOINT_BEFORE_ROLLBACK]


async def test_async_checkpoint_hook_is_awaited(session_factory: async_sessionmaker[AsyncSession]) -> None:
    seen: list[str] = []

    async def hook(name: str) -> None:
        seen.append(name)

    unit_of_work = build_unit_of_work(session_factory, checkpoint_hook=hook)
    async with unit_of_work:
        await unit_of_work.commit()
    assert seen == [CHECKPOINT_BEFORE_COMMIT]


async def test_checkpoint_failure_aborts_commit_and_scopes_rollback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def hook(name: str) -> None:
        raise RuntimeError("crash gate")

    unit_of_work = build_unit_of_work(session_factory, checkpoint_hook=hook)
    with pytest.raises(RuntimeError, match="crash gate"):
        async with unit_of_work:
            notes: NoteRepository = unit_of_work.repository("notes")
            await notes.add("gate")
            await unit_of_work.commit()
    assert await _persisted_titles(session_factory) == []


async def test_missing_hook_is_a_zero_overhead_noop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    unit_of_work = build_unit_of_work(session_factory)
    async with unit_of_work:
        await unit_of_work.checkpoint("anywhere")
        await unit_of_work.commit()
