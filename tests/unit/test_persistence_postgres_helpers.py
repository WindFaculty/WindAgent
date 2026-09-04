"""Phase 5 unit tests: PostgreSQL helpers — SQLSTATE, CAS, upsert, locks, metadata."""

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
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from windagent.platform.persistence import (
    NAMING_CONVENTION,
    target_metadata,
)
from windagent.platform.persistence import (
    metadata as shared_metadata,
)
from windagent.platform.persistence.postgres import (
    advisory_lock_key,
    compare_and_swap_update,
    extract_sqlstate,
    is_transient_error,
    is_unique_violation,
    upsert_row,
)
from windagent.platform.persistence.postgres.locks import _to_signed_int32


class FakePostgresError(Exception):
    """Mimics asyncpg errors, which carry a ``sqlstate`` attribute."""

    def __init__(self, sqlstate: str | None) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class WrappedError(Exception):
    """Mimics SQLAlchemy DBAPI errors wrapping the driver exception."""

    def __init__(self, cause: BaseException) -> None:
        super().__init__("wrapped")
        self.orig = cause


def test_extract_sqlstate_reads_driver_and_wrapper_chain() -> None:
    direct = FakePostgresError("40001")
    assert extract_sqlstate(direct) == "40001"

    wrapped = WrappedError(direct)
    assert extract_sqlstate(wrapped) == "40001"

    assert extract_sqlstate(ValueError("no state")) is None


def test_transient_and_unique_classification() -> None:
    assert is_transient_error(FakePostgresError("40001"))
    assert is_transient_error(FakePostgresError("40P01"))
    assert is_transient_error(FakePostgresError("55P03"))
    assert is_transient_error(FakePostgresError("08006"))
    assert not is_transient_error(FakePostgresError("23505"))
    assert not is_transient_error(ValueError("application bug"))

    assert is_unique_violation(FakePostgresError("23505"))
    assert not is_unique_violation(FakePostgresError("40001"))


def test_advisory_lock_key_is_deterministic_and_in_signed_int32_range() -> None:
    first = advisory_lock_key("recovery-leader")
    second = advisory_lock_key("recovery-leader")

    assert first == second
    assert advisory_lock_key("other-section") != first
    for value in first:
        assert -(2**31) <= value < 2**31

    with pytest.raises(ValueError, match="non-empty"):
        advisory_lock_key("   ")


def test_explicit_integer_key_components_are_normalized() -> None:
    assert _to_signed_int32(3_000_000_000) == 3_000_000_000 - 2**32
    assert _to_signed_int32(-1) == -1
    assert _to_signed_int32(0) == 0
    with pytest.raises(TypeError):
        _to_signed_int32(True)


_METADATA = MetaData()
ACCOUNTS = Table(
    "accounts",
    _METADATA,
    Column("id", String(50), primary_key=True),
    Column("balance", Integer, nullable=False),
    Column("version", Integer, nullable=False, default=0),
)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(_METADATA.create_all)
    yield engine
    await engine.dispose()


async def _account_state(
    engine: AsyncEngine, account_id: str
) -> tuple[int, int]:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(ACCOUNTS.c.balance, ACCOUNTS.c.version).where(
                    ACCOUNTS.c.id == account_id
                )
            )
        ).one()
    return int(row.balance), int(row.version)


async def test_cas_update_wins_with_matching_version(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(insert(ACCOUNTS).values(id="a", balance=10, version=3))

    async with engine.begin() as connection:
        won = await compare_and_swap_update(
            connection,
            ACCOUNTS,
            key_column="id",
            key_value="a",
            expected_version=3,
            values={"balance": 25},
        )

    assert won
    assert await _account_state(engine, "a") == (25, 4)


async def test_cas_update_loses_on_stale_version(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(insert(ACCOUNTS).values(id="a", balance=10, version=5))

    async with engine.begin() as connection:
        won = await compare_and_swap_update(
            connection,
            ACCOUNTS,
            key_column="id",
            key_value="a",
            expected_version=2,
            values={"balance": 99},
        )

    assert not won
    assert await _account_state(engine, "a") == (10, 5)


async def test_cas_rejects_invalid_parameters(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        with pytest.raises(ValueError, match="expected_version"):
            await compare_and_swap_update(
                connection,
                ACCOUNTS,
                key_column="id",
                key_value="a",
                expected_version=-1,
            )
        with pytest.raises(ValueError, match="version_increment"):
            await compare_and_swap_update(
                connection,
                ACCOUNTS,
                key_column="id",
                key_value="a",
                expected_version=1,
                version_increment=0,
            )


async def test_upsert_validates_inputs_before_touching_the_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        with pytest.raises(KeyError):
            await upsert_row(
                connection,
                ACCOUNTS,
                conflict_columns=["missing"],
                values={"id": "a", "balance": 1},
            )
        with pytest.raises(ValueError, match="empty"):
            await upsert_row(connection, ACCOUNTS, conflict_columns=["id"], values={})
        with pytest.raises(ValueError, match="empty"):
            await upsert_row(
                connection, ACCOUNTS, conflict_columns=[], values={"id": "a"}
            )


def test_shared_metadata_is_the_alembic_target() -> None:
    assert target_metadata is shared_metadata
    assert {"ix", "uq", "ck", "fk", "pk"} <= set(NAMING_CONVENTION)


def test_shared_metadata_generates_deterministic_constraint_names() -> None:
    table = Table(
        "naming_probe",
        shared_metadata,
        Column("id", Integer, primary_key=True),
    )
    try:
        assert table.primary_key.name == "pk_naming_probe"
    finally:
        shared_metadata.remove(table)
