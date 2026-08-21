"""
VideoProductionUnitOfWork for Stage B Production API Foundation.

Guarantees transactional boundaries for project mutations, domain event appends,
idempotency record writes, and read-model checkpoint updates.
"""

from __future__ import annotations

from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_storage.factory import (
    create_idempotency_repository,
    create_production_event_repository,
    create_production_project_repository,
    create_workspace_read_model_repository,
)
from windagent_storage.video_production.repositories import (
    IdempotencyRepository,
    ProductionEventRepository,
    ProductionProjectRepository,
    WorkspaceReadModelRepository,
)


class VideoProductionUnitOfWork:
    """Unit of Work for Video Production API V2 operations."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: Optional[AsyncSession] = None

        self.projects: ProductionProjectRepository = None  # type: ignore
        self.idempotency: IdempotencyRepository = None  # type: ignore
        self.events: ProductionEventRepository = None  # type: ignore
        self.read_models: WorkspaceReadModelRepository = None  # type: ignore

    async def __aenter__(self) -> VideoProductionUnitOfWork:
        # Session-bound repositories are composed through the explicit storage
        # factory — the single allowlisted construction point inside the
        # infrastructure package.
        self.session = self._session_factory()
        self.projects = create_production_project_repository(self.session)
        self.idempotency = create_idempotency_repository(self.session)
        self.events = create_production_event_repository(self.session)
        self.read_models = create_workspace_read_model_repository(self.session)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self.rollback()
        if self.session:
            await self.session.close()

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session:
            await self.session.rollback()
