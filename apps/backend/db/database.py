"""Async SQLAlchemy database wrapper for the WindAgent backend.

Responsibilities:
  - Build an async engine (aiosqlite driver).
  - Provide an `async with session_factory() as session:` context.
  - Create tables on first startup.
  - Expose `dispose()` for clean shutdown.

Usage in lifespan:

    db = Database("sqlite+aiosqlite:///./windagent.db")
    await db.init_models()
    app.state.db = db
    yield
    await db.dispose()
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db.models import Base, seed_canonical_models


log = logging.getLogger(__name__)


DEFAULT_DB_URL = "sqlite+aiosqlite:///./windagent.db"


class Database:
    """Thin async SQLAlchemy wrapper. One instance per app."""

    def __init__(self, url: str = DEFAULT_DB_URL, *, echo: bool = False) -> None:
        self.url = url
        self.engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            future=True,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def init_models(self) -> None:
        """Create all tables that don't exist yet. Idempotent.

        Phase 2: also backfill canonical_models/bindings from the legacy
        catalog, and add an event sequence column for durable replay.
        All steps are non-destructive on an existing database.
        """
        from sqlalchemy import text

        from windagent_storage.orm.v2_orchestration_models import BaseORM as V2BaseORM
        from windagent_storage.orm.models import BaseORM as RootBaseORM

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(V2BaseORM.metadata.create_all)
            await conn.run_sync(RootBaseORM.metadata.create_all)
# Legacy column addition (idempotent).
            try:
                await conn.execute(
                    text("ALTER TABLE model_providers ADD COLUMN api_key VARCHAR(255)")
                )
            except Exception:
                pass
            # Event sequence for WebSocket replay (ban_ke_hoach §6.1).
            try:
                await conn.execute(
                    text("ALTER TABLE execution_events ADD COLUMN event_seq INTEGER")
                )
            except Exception:
                pass
            # Idempotent migrations for model_routing_rules columns
            for col_def in [
                ("name", "VARCHAR(128) DEFAULT 'Route'"),
                ("description", "TEXT"),
                ("final_fallback_model_id", "VARCHAR(128)"),
                ("status", "VARCHAR(32) DEFAULT 'Active'"),
                ("priority", "INTEGER DEFAULT 1"),
                ("tags_json", "TEXT DEFAULT '[]'"),
            ]:
                try:
                    await conn.execute(text(f"ALTER TABLE model_routing_rules ADD COLUMN {col_def[0]} {col_def[1]}"))
                except Exception:
                    pass
            # Phase 10: provider_model_bindings.equivalence_level (default exact_revision).
            try:
                await conn.execute(
                    text("ALTER TABLE provider_model_bindings ADD COLUMN equivalence_level VARCHAR(32) DEFAULT 'exact_revision' NOT NULL")
                )
            except Exception:
                pass

        # Backfill canonical model registry from existing catalog rows.
        try:
            created = await seed_canonical_models(self)
            if created:
                log.info("seeded %d canonical model(s) from existing catalog", created)
        except Exception:
            log.exception("canonical model seed failed (non-fatal)")
        log.info("database schema initialised (%s)", self.url)

    async def dispose(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session, commit on clean exit, rollback on exception."""
        async with self.session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
