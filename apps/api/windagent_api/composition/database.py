"""Database composer for the API composition root (Phase 7).

Owns the ``DatabaseManager``, the production backup-evidence gate, the
canonical Alembic migration, and the demo canonical-model persistence adapter.
No execution runtime or worktree authority is composed here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM

logger = logging.getLogger("windagent.api.composition.database")


@dataclass
class DatabaseBundle:
    """Typed result of the database composer."""

    db: DatabaseManager


class DatabaseComposer:
    """Constructs the database manager and applies the canonical schema."""

    async def compose(self, db_url: str, release_telemetry: Any) -> DatabaseBundle:
        db = DatabaseManager(db_url, release_telemetry=release_telemetry)
        try:
            if os.getenv("WINDAGENT_ENV", "").lower() == "production":
                self._require_production_backup_evidence(db)
            # Phase 1 (G1.1): runtime bootstraps schema through the canonical
            # Alembic migration workflow instead of ad-hoc create_all.
            await db.upgrade_to_head(BaseORM.metadata)
        except Exception as ex:
            if os.getenv("WINDAGENT_ENV") == "production":
                # Fail closed: a partially-migrated schema must not serve traffic.
                raise
            logger.warning(f"Database migration warning: {ex}")
        return DatabaseBundle(db=db)

    @staticmethod
    def _require_production_backup_evidence(db: DatabaseManager) -> None:
        """Fail closed when a production migration lacks verified backup evidence."""
        if db.db_url.startswith("sqlite+aiosqlite:///"):
            backup_root = os.getenv("WINDAGENT_RELEASE_BACKUP_ROOT")
            if not backup_root:
                raise RuntimeError(
                    "WINDAGENT_RELEASE_BACKUP_ROOT is required before a production migration"
                )
            # ``create_pre_migration_backup`` is synchronous (file copy); it
            # returns None for a brand-new database with no state to preserve.
            backup = db.create_pre_migration_backup(backup_root)
            if backup is not None:
                logger.info("Created pre-migration SQLite backup at %s", backup)
        else:
            evidence = os.getenv("WINDAGENT_EXTERNAL_BACKUP_EVIDENCE")
            if not evidence or not Path(evidence).exists():
                raise RuntimeError(
                    "WINDAGENT_EXTERNAL_BACKUP_EVIDENCE must reference a verified "
                    "PostgreSQL backup before a production migration"
                )


def make_demo_canonical_model_persister(
    sync_session_factory: Callable[[], Any],
) -> Callable[[], None]:
    """Return an idempotent callable that persists the demo canonical models.

    The ORM mapping lives behind this composition adapter so
    ``v3_demo_seed.py`` stays application logic with no ORM/database imports.
    """
    import json

    from windagent_storage.orm.v3_models import CanonicalModelV3ORM
    from windagent_api.services.v3_demo_seed import _MODELS

    def persist() -> None:
        with sync_session_factory() as session:
            for m in _MODELS:
                existing = (
                    session.query(CanonicalModelV3ORM).filter_by(id=m["id"]).first()
                )
                if existing is not None:
                    continue
                session.add(
                    CanonicalModelV3ORM(
                        id=m["id"],
                        vendor=m.get("vendor", "").lower(),
                        family=m.get("family", ""),
                        canonical_name=m.get("name", m["id"]),
                        revision="latest",
                        context_window=m.get("context_window", 128000),
                        capabilities_json=json.dumps(m.get("capabilities", [])),
                        enabled=True,
                    )
                )
            session.commit()

    return persist


__all__ = ["DatabaseBundle", "DatabaseComposer", "make_demo_canonical_model_persister"]