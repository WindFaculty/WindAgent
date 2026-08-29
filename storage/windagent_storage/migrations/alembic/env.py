"""Alembic migration environment for WindAgent Storage (Phase 1 — G1.1).

Bridges the async application DB URL (``sqlite+aiosqlite://`` /
``postgresql+asyncpg://``) to the synchronous driver Alembic needs
(``sqlite://`` / ``postgresql+psycopg2://``), then runs migrations against the
single canonical ``BaseORM.metadata`` (V2 canonical + V2 orchestration + V3
provider routing tables).

Phase 1 exit gates covered by this environment:
- ``alembic upgrade head`` builds a complete fresh DB (0001 baseline).
- ``alembic downgrade base`` removes every managed table on a test DB.
- Upgrade from a V2 fixture preserves needed data (0002/0003 data lanes).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the repository root importable regardless of the CWD the runner is
# invoked from (env.py lives at storage/windagent_storage/migrations/alembic/).
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from windagent_storage.orm.models import BaseORM  # noqa: E402
import windagent_storage.orm.v2_orchestration_models  # noqa: E402,F401  (registers V2 orchestration tables)
import windagent_storage.orm.v3_models  # noqa: E402,F401  (registers V3 provider/routing tables)
import windagent_storage.orm.agent_runs_stub  # noqa: E402,F401  (registers agent_runs stub for FK)
import windagent_storage.orm.agent_loop_models  # noqa: E402,F401  (registers agent loop/budget tables)
import windagent_storage.orm.delegation_models  # noqa: E402,F401  (registers delegation tables)
import windagent_storage.orm.persistent_goal_models  # noqa: E402,F401  (registers persistent goals)
import windagent_storage.orm.agent_checkpoint_models  # noqa: E402,F401  (registers agent checkpoints)
import windagent_storage.orm.multi_agent_models  # noqa: E402,F401  (registers conversations/parent_tasks/plans)
import windagent_storage.orm.memory_v2_models  # noqa: E402,F401  (registers memory v2 records)
import windagent_storage.orm.evaluation_models  # noqa: E402,F401  (registers evaluation records)
import windagent_storage.orm.experience_models  # noqa: E402,F401  (registers experience records)
import windagent_storage.orm.candidate_models  # noqa: E402,F401  (registers learning candidates and learned rules)
import windagent_storage.video_production.video_production_models  # noqa: E402,F401  (registers V2 video production tables)


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = BaseORM.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER inside a transaction for some ops; Alembic
            # handles per-revision transactions itself.
            transaction_per_migration=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
