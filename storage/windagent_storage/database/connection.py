"""
Database Connection Manager for WindAgent Architecture V2.
Configures async SQLAlchemy engine and session factories.
"""

from __future__ import annotations
from typing import Any, AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool


class DatabaseManager:
    def __init__(
        self, db_url: str = "sqlite+aiosqlite:///windagent.db", echo: bool = False
    ):
        self.db_url = db_url
        self.echo = echo

        # PostgreSQL needs pool configuration for asyncpg; SQLite uses appropriate pool
        if db_url.startswith("postgresql+asyncpg://") or db_url.startswith(
            "postgresql+psycopg2://"
        ):
            self.engine: AsyncEngine = create_async_engine(
                self.db_url,
                echo=self.echo,
                future=True,
                pool_pre_ping=True,
            )
        elif db_url.startswith("sqlite+aiosqlite:///:memory:"):
            # In-memory SQLite needs StaticPool to share connection across sessions
            self.engine: AsyncEngine = create_async_engine(
                self.db_url,
                echo=self.echo,
                future=True,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        else:
            # File-based SQLite: NullPool avoids "database is locked" on concurrent writes
            self.engine: AsyncEngine = create_async_engine(
                self.db_url,
                echo=self.echo,
                future=True,
                poolclass=NullPool,
            )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    async def create_tables(self, base_metadata: Any) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(base_metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
