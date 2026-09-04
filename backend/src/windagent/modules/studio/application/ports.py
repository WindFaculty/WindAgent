"""Repository port for Studio persistence.

The port is the only boundary the application layer knows.  Both the SQL
adapter and the in-memory adapter implement it identically so handlers stay
transport-neutral and tests run without a database.
"""

from __future__ import annotations

from typing import Any, Protocol

from windagent.kernel.events import EventEnvelope

from .models import (
    ArtifactRow,
    CharacterRow,
    EpisodeRow,
    ProjectRow,
    RevisionRow,
    SeriesRow,
    StoryboardRow,
    WorldLocationRow,
    WorldPropRow,
)


class StudioStore(Protocol):
    """Durable port — one method per aggregate table."""

    # -- projects ----------------------------------------------------------
    async def insert_project(self, row: ProjectRow) -> bool: ...
    async def get_project(self, project_id: str) -> ProjectRow | None: ...
    async def list_projects(self) -> tuple[ProjectRow, ...]: ...
    async def update_project(
        self,
        project_id: str,
        *,
        title: str | None,
        description: str | None,
        series_ids_json: str | None,
        optimistic_version: int | None,
        expected_version: int | None,
        metadata_json: str | None,
    ) -> ProjectRow | None: ...

    # -- series ------------------------------------------------------------
    async def insert_series(self, row: SeriesRow) -> bool: ...
    async def get_series(self, series_id: str) -> SeriesRow | None: ...
    async def list_series(self, project_id: str | None = None) -> tuple[SeriesRow, ...]: ...
    async def update_series(
        self,
        series_id: str,
        *,
        title: str | None,
        description: str | None,
        episode_ids_json: str | None,
        optimistic_version: int | None,
        expected_version: int | None,
        metadata_json: str | None,
    ) -> SeriesRow | None: ...

    # -- episodes -----------------------------------------------------------
    async def insert_episode(self, row: EpisodeRow) -> bool: ...
    async def get_episode(self, episode_id: str) -> EpisodeRow | None: ...
    async def list_episodes(self, series_id: str | None = None) -> tuple[EpisodeRow, ...]: ...
    async def update_episode(
        self,
        episode_id: str,
        *,
        title: str | None = None,
        logline: str | None = None,
        state: str | None = None,
        current_revision_id: str | None = None,
        active_run_id: str | None = None,
        awaiting_checkpoint: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
        metadata_json: str | None = None,
    ) -> EpisodeRow | None: ...

    # -- revisions ----------------------------------------------------------
    async def insert_revision(self, row: RevisionRow) -> bool: ...
    async def get_revision(self, revision_id: str) -> RevisionRow | None: ...
    async def list_revisions(self, episode_id: str | None = None) -> tuple[RevisionRow, ...]: ...
    async def update_revision(
        self,
        revision_id: str,
        *,
        status: str | None = None,
        lock_state: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
    ) -> RevisionRow | None: ...

    # -- artifacts ----------------------------------------------------------
    async def insert_artifact(self, row: ArtifactRow) -> bool: ...
    async def get_artifact(self, artifact_id: str) -> ArtifactRow | None: ...
    async def list_artifacts(
        self, episode_id: str | None = None, artifact_type: str | None = None
    ) -> tuple[ArtifactRow, ...]: ...

    # -- characters ---------------------------------------------------------
    async def insert_character(self, row: CharacterRow) -> bool: ...
    async def get_character(self, character_id: str) -> CharacterRow | None: ...
    async def list_characters(self, series_id: str | None = None) -> tuple[CharacterRow, ...]: ...
    async def update_character(
        self, character_id: str, *, values: dict[str, Any]
    ) -> CharacterRow | None: ...

    # -- world --------------------------------------------------------------
    async def upsert_location(self, row: WorldLocationRow) -> WorldLocationRow: ...
    async def list_locations(self, series_id: str) -> tuple[WorldLocationRow, ...]: ...
    async def upsert_prop(self, row: WorldPropRow) -> WorldPropRow: ...
    async def list_props(self, series_id: str) -> tuple[WorldPropRow, ...]: ...

    # -- storyboard ---------------------------------------------------------
    async def insert_storyboard(self, row: StoryboardRow) -> bool: ...
    async def get_storyboard(self, storyboard_id: str) -> StoryboardRow | None: ...
    async def list_storyboards(self, episode_id: str | None = None) -> tuple[StoryboardRow, ...]: ...
    async def update_storyboard(
        self, storyboard_id: str, *, panels_json: str | None, optimistic_version: int | None, expected_version: int | None, metadata_json: str | None
    ) -> StoryboardRow | None: ...


class TransactionScope(Protocol):
    """Bounded UnitOfWork scope + outbox event writer."""

    def store(self) -> StudioStore: ...
    async def record_event(
        self, envelope: EventEnvelope, *, deduplication_key: str | None = None
    ) -> bool: ...
    async def commit(self) -> None: ...
    async def __aenter__(self) -> TransactionScope: ...
    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None) -> bool: ...
