"""Async Alembic environment for WindAgent V2.

Only PostgreSQL is canonical (plan section 8); ``sqlite://`` startup URLs are
rejected by ``Settings`` outside the isolated-test environment, so a real
migration can never silently target SQLite.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

V2_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = V2_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from windagent.platform.configuration.settings import Settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_settings = Settings()
config.set_main_option("sqlalchemy.url", _settings.database_url)


def _target_metadata() -> Any:
    """Return ORM metadata for autogenerate, or ``None`` in Phase 1.

    Phase 5 populates ``windagent.platform.persistence.metadata``.  Until then
    migrations run without autogenerate support, which is intentional: V2 does
    not import legacy schema definitions.
    """

    try:
        from windagent.platform.persistence.metadata import target_metadata
    except ImportError:
        return None
    return target_metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=_target_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=_target_metadata())
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
