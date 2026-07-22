"""
Database Connection Manager for WindAgent Architecture V2.
Configures async SQLAlchemy engine and session factories.
"""

from __future__ import annotations
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
)


class DatabaseManager:
    def __init__(self, db_url: str = "sqlite+aiosqlite:///windagent.db", echo: bool = False):
        self.db_url = db_url
        self.echo = echo
        self.engine: AsyncEngine = create_async_engine(
            self.db_url,
            echo=self.echo,
            future=True,
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
