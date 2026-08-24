"""Phase 10 regression — schema_migration check against a REAL migrated DB.

Unit-tier health tests mock the session factory (tests/unit/observability);
this component-tier test is the only place allowed to exercise the real
SQLAlchemy/aiosqlite path end-to-end.
"""

from __future__ import annotations

import pytest

from windagent_observability.health import HealthChecker, HealthStatus


@pytest.mark.asyncio
async def test_schema_migration_real_alembic_sqlite_is_up(tmp_path):
    """Regression: a fresh DB migrated by the canonical runner must be UP.

    The legacy check queried the retired per-app ``migration_history``
    table, so every Alembic-migrated database failed readiness forever.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from windagent_storage.migrations.runner import alembic_heads, alembic_upgrade_head

    db_file = tmp_path / "health_regression.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    alembic_upgrade_head(db_url)

    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    heads = alembic_heads()
    checker = HealthChecker(
        db_session_factory=factory,
        expected_schema_head=heads[0] if len(heads) == 1 else None,
    )
    try:
        result = await checker._check_schema_migration()
    finally:
        await engine.dispose()

    assert result.status == HealthStatus.UP, result.message
    assert heads and heads[0] in result.message
