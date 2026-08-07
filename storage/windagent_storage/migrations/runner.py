"""Programmatic Alembic migration runner for WindAgent Storage (Phase 1 — G1.1).

Replaces the runtime ``create_tables`` flow with an explicit, versioned,
rollback-capable migration workflow:

- ``alembic_upgrade_head(db_url)``  — apply all pending migrations.
- ``alembic_downgrade_base(db_url)`` — roll back every migration (test DBs).
- ``alembic_current(db_url)``       — current head revision stamps.
- ``alembic_heads()``               — declared head(s) of the revision graph.
- ``verify_single_head()``          — fail fast when the graph is not linear (GAP D).

The application DB URL (async driver) is mapped to the synchronous driver
Alembic needs via ``windagent_storage.database.sync_factory.sync_db_url``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from windagent_storage.database.sync_factory import sync_db_url

_ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


class MultipleMigrationHeadsError(RuntimeError):
    """Raised when the Alembic revision graph has more than one head (GAP D)."""


class SchemaAheadOfMigrationsError(RuntimeError):
    """Raised when the database stamp is a revision Alembic does not know."""


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


def alembic_heads() -> Tuple[str, ...]:
    """Return the declared head revision(s) of the Alembic script directory.

    A healthy linear chain (0001→0009) yields exactly one head.  GAP D relies
    on this to fail fast when a second branch is accidentally introduced.
    """
    script = ScriptDirectory.from_config(_make_alembic_config("sqlite://"))
    return tuple(sorted(script.get_heads()))


def alembic_current(db_url: str) -> Tuple[str, ...]:
    """Return the revision stamp(s) currently applied on ``db_url``.

    Reads ``alembic_version`` directly so the result is a plain value that
    callers (e.g. evidence generation) can record without an Alembic CLI.
    A non-existent SQLite file is treated as an unmigrated DB (returns ``()``)
    without creating the file as a side effect.
    """
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url

    sync_url = sync_db_url(db_url)
    parsed = make_url(sync_url)
    if parsed.drivername.startswith("sqlite") and parsed.database:
        db_path = Path(parsed.database)
        if db_path.suffix and not db_path.is_file():
            return ()

    engine = create_engine(sync_url)
    try:
        inspector = inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            return ()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchall()
        return tuple(sorted(str(row[0]) for row in rows))
    finally:
        engine.dispose()


def verify_single_head(db_url: str = "sqlite://") -> Tuple[str, ...]:
    """Verify the revision graph is linear with exactly one head (GAP D).

    Returns the single head revision.  Raises ``MultipleMigrationHeadsError``
    when the graph diverges and ``SchemaAheadOfMigrationsError`` when the DB is
    stamped with an unknown revision.  ``db_url`` is only used to inspect the
    applied stamp when provided; head verification itself needs no connection.
    """
    heads = alembic_heads()
    if len(heads) != 1:
        raise MultipleMigrationHeadsError(
            f"expected exactly one Alembic head, found {len(heads)}: {heads}"
        )
    head = heads[0]
    if db_url != "sqlite://":
        known = set()
        script = ScriptDirectory.from_config(_make_alembic_config(db_url))
        for revision in script.walk_revisions():
            known.add(revision.revision)
        unknown = set(alembic_current(db_url)) - known
        if unknown:
            raise SchemaAheadOfMigrationsError(
                f"database stamped with unknown revision(s): {sorted(unknown)}"
            )
    return head
