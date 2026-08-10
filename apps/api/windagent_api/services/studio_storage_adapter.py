"""
Plan C1 storage adapters: bind the A3 SQL Studio repositories to the frozen
read ports used by ``StudioApplicationService``.

One session per call, opened from the container's async session factory and
closed after the query. These adapters are the production read path for
/api/v3/studio until A4 wires command authority; writes remain fail-closed
until the orchestrator seam lands.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.events.studio import StudioEventEnvelope
from windagent_storage.studio.repositories import (
    SqlApprovalRepository,
    SqlEpisodeRepository,
    SqlSeriesProjectRepository,
    SqlStoryArtifactRepository,
    SqlStudioEventRepository,
    SqlStudioRevisionRepository,
    SqlStudioRunRepository,
)


class SqlSeriesReadAdapter:
    """SeriesProjectRepositoryPort read surface."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, series_id: SeriesProjectId) -> Optional[Any]:
        async with self._session_factory() as session:
            return await SqlSeriesProjectRepository(session).get(series_id)

    async def list(self, cursor: Optional[str] = None, limit: int = 100) -> List[Any]:
        async with self._session_factory() as session:
            return await SqlSeriesProjectRepository(session).list(cursor=cursor, limit=limit)


class SqlEpisodeReadAdapter:
    """EpisodeRepositoryPort read surface."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, episode_id: EpisodeId) -> Optional[Any]:
        async with self._session_factory() as session:
            return await SqlEpisodeRepository(session).get(episode_id)

    async def list_by_series(self, series_id: SeriesProjectId) -> List[Any]:
        async with self._session_factory() as session:
            return await SqlEpisodeRepository(session).list_by_series(series_id)


class SqlRevisionReadAdapter:
    """ProductionRevisionRepositoryPort read surface."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, revision_id: ProductionRevisionId) -> Optional[Any]:
        async with self._session_factory() as session:
            return await SqlStudioRevisionRepository(session).get(revision_id)

    async def latest_for_episode(self, episode_id: EpisodeId) -> Optional[Any]:
        async with self._session_factory() as session:
            return await SqlStudioRevisionRepository(session).latest_for_episode(episode_id)


class SqlArtifactReadAdapter:
    """StoryArtifactRepositoryPort read surface."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, artifact_id: ArtifactId) -> Optional[Any]:
        async with self._session_factory() as session:
            return await SqlStoryArtifactRepository(session).get(artifact_id)

    async def find_by_hash(self, content_hash: str) -> Optional[Any]:
        async with self._session_factory() as session:
            return await SqlStoryArtifactRepository(session).find_by_hash(content_hash)

    async def list_for_episode(self, episode_id: EpisodeId) -> List[Any]:
        async with self._session_factory() as session:
            return await SqlStoryArtifactRepository(session).list_for_episode(episode_id)


class SqlApprovalReadAdapter:
    """ApprovalRepositoryPort read surface."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def decisions_for_revision(
        self, revision_id: ProductionRevisionId
    ) -> List[Any]:
        async with self._session_factory() as session:
            return await SqlApprovalRepository(session).decisions_for_revision(revision_id)


class SqlRunQueryAdapter:
    """StudioRunQueryPort over the durable run table."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_run(self, run_id: StudioRunId) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            return await SqlStudioRunRepository(session).get(run_id)

    async def get_run_tasks(self, run_id: StudioRunId) -> List[Dict[str, Any]]:
        run = await self.get_run(run_id)
        if run is None:
            return []
        return list(run.get("dag", {}).get("tasks", []))


class SqlEventQueryAdapter:
    """StudioEventQueryPort over the durable event store."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def events_after(
        self, run_id: StudioRunId, after_sequence: int = 0, limit: int = 100
    ) -> List[StudioEventEnvelope]:
        async with self._session_factory() as session:
            return await SqlStudioEventRepository(session).events_after(
                run_id, after_sequence=after_sequence, limit=limit
            )

    async def latest_sequence(self, run_id: StudioRunId) -> int:
        async with self._session_factory() as session:
            return await SqlStudioEventRepository(session).latest_sequence(run_id)


__all__ = [
    "SqlSeriesReadAdapter",
    "SqlEpisodeReadAdapter",
    "SqlRevisionReadAdapter",
    "SqlArtifactReadAdapter",
    "SqlApprovalReadAdapter",
    "SqlRunQueryAdapter",
    "SqlEventQueryAdapter",
]
