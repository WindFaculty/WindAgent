"""Phase 5 integration: persistence semantics on real PostgreSQL.

Requires the canonical database (``docker compose up -d postgres``) and is
skipped automatically when it is unreachable.  CI runs these tests against
a dedicated PostgreSQL 16 service container.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
    text,
)
from sqlalchemy.engine import make_url
from windagent.platform.persistence import (
    Database,
    SqlUnitOfWork,
    check_database_health,
)
from windagent.platform.persistence.postgres import (
    compare_and_swap_update,
    try_advisory_xact_lock,
    upsert_row,
)

pytestmark = [pytest.mark.postgres]

V2_ROOT = Path(__file__).resolve().parents[2]


async def test_health_reports_canonical_server_metadata(database: Database) -> None:
    report = await check_database_health(database.engine)

    assert report.is_healthy
    assert report.database_name == "windagent_v2"
    assert report.server_version is not None
    assert "PostgreSQL" in report.server_version


async def test_foundation_migration_round_trip_on_a_throwaway_database(
    database: Database,
    database_url: str,
) -> None:
    """The clean migration chain applies and reverts on real PostgreSQL.

    Uses a dedicated throwaway database so the shared development database
    keeps its canonical head revision untouched.
    """
    import subprocess
    import sys

    probe_name = f"windagent_v2_migration_probe_{os.getpid()}"
    probe_url = (
        make_url(database_url).set(database=probe_name).render_as_string(hide_password=False)
    )

    environment = {
        **os.environ,
        "WINDAGENT_DATABASE_URL": probe_url,
        "WINDAGENT_ENVIRONMENT": "development",
    }

    def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=V2_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )

    try:
        async with database.engine.connect() as connection:
            admin = await connection.execution_options(isolation_level="AUTOCOMMIT")
            await admin.execute(text(f'DROP DATABASE IF EXISTS "{probe_name}"'))
            await admin.execute(text(f'CREATE DATABASE "{probe_name}"'))

        upgrade = alembic("upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stderr

        probe = Database.from_url(probe_url)
        try:
            async with probe.engine.connect() as connection:
                version = (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
                tables = (
                    await connection.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public' ORDER BY table_name"
                        )
                    )
                ).scalars().all()
            assert version == "0013"
            assert {
                "platform_events",
                "platform_outbox",
                "platform_jobs",
                "platform_job_attempts",
            } <= set(tables)
            assert "production_projects" in tables
            assert "production_edls" in tables
            assert "memory_records" in tables
            assert "workspace_workspaces" in tables
            assert "workspace_members" in tables
            assert "quality_datasets" in tables
            assert "quality_evaluation_runs" in tables
        finally:
            await probe.engine.dispose()

        downgrade = alembic("downgrade", "base")
        assert downgrade.returncode == 0, downgrade.stderr
    finally:
        async with database.engine.connect() as connection:
            admin = await connection.execution_options(isolation_level="AUTOCOMMIT")
            await admin.execute(text(f'DROP DATABASE IF EXISTS "{probe_name}"'))


async def test_unit_of_work_commits_against_postgres(database: Database) -> None:
    metadata = MetaData()
    notes = Table(
        "integration_uow_notes",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("title", String(100), nullable=False),
    )
    async with database.engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    try:
        unit_of_work = database.unit_of_work()
        assert isinstance(unit_of_work, SqlUnitOfWork)
        async with unit_of_work:
            await unit_of_work.session.execute(insert(notes).values(id=1, title="pg"))
            await unit_of_work.commit()

        async with database.engine.connect() as connection:
            titles = list((await connection.execute(select(notes.c.title))).scalars())
        assert titles == ["pg"]
    finally:
        async with database.engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)


async def test_cas_and_upsert_on_live_postgres(database: Database) -> None:
    metadata = MetaData()
    accounts = Table(
        "integration_cas_accounts",
        metadata,
        Column("id", String(50), primary_key=True),
        Column("balance", Integer, nullable=False),
        Column("version", Integer, nullable=False, default=0),
    )
    async with database.engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        await connection.execute(
            insert(accounts).values(id="a", balance=0, version=0)
        )
    try:
        async with database.engine.begin() as connection:
            won = await compare_and_swap_update(
                connection,
                accounts,
                key_column="id",
                key_value="a",
                expected_version=0,
                values={"balance": 42},
            )
        assert won

        async with database.engine.begin() as connection:
            stale = await compare_and_swap_update(
                connection,
                accounts,
                key_column="id",
                key_value="a",
                expected_version=0,
                values={"balance": 7},
            )
        assert not stale

        async with database.engine.begin() as connection:
            await upsert_row(
                connection,
                accounts,
                conflict_columns=["id"],
                values={"id": "b", "balance": 1, "version": 0},
                update_columns=["balance"],
            )
        async with database.engine.connect() as connection:
            rows = (await connection.execute(select(accounts))).all()
        assert {row.id for row in rows} == {"a", "b"}
    finally:
        async with database.engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)


async def test_transaction_scoped_advisory_lock_excludes_other_connections(
    database: Database,
) -> None:
    async with database.engine.connect() as leader:
        async with leader.begin():
            assert await try_advisory_xact_lock(leader, "phase5-leader") is True

            async with database.engine.connect() as follower:
                async with follower.begin():
                    assert await try_advisory_xact_lock(follower, "phase5-leader") is False

    async with database.engine.connect() as next_leader:
        async with next_leader.begin():
            assert await try_advisory_xact_lock(next_leader, "phase5-leader") is True
