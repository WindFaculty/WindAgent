"""Programmatic Alembic migration runner for WindAgent Storage (Phase 1 — G1.1).

Replaces the runtime ``create_tables`` flow with an explicit, versioned,
rollback-capable migration workflow:

- ``alembic_upgrade_head(db_url)``  — apply all pending migrations.
- ``alembic_downgrade_base(db_url)`` — roll back every migration (test DBs).
- ``alembic_current(db_url)``       — current head revision stamps.

The application DB URL (async driver) is mapped to the synchronous driver
Alembic needs via ``windagent_storage.database.sync_factory.sync_db_url``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config

from windagent_storage.database.sync_factory import sync_db_url

_ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


def _make_alembic_config(db_url: str, script_location: Optional[Path] = None) -> Config:
    """Build an Alembic ``Config`` bound to the canonical migrations directory."""
    cfg = Config()
    cfg.set_main_option("script_location", str(script_location or _ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", sync_db_url(db_url))
    return cfg


def alembic_upgrade_head(db_url: str) -> None:
    """Apply all registered migrations up to ``head`` on ``db_url``."""
    command.upgrade(_make_alembic_config(db_url), "head")


def alembic_downgrade_base(db_url: str) -> None:
    """Roll back every migration down to ``base`` on ``db_url``."""
    command.downgrade(_make_alembic_config(db_url), "base")
