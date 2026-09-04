"""In-memory Studio store and transaction scope for unit tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from windagent.kernel.events import EventEnvelope

from ..application.models import (
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
from ..application.ports import StudioStore


class InMemoryStudioStore(StudioStore):
    def __init__(self) -> None:
        self.projects: dict[str, ProjectRow] = {}
        self.series: dict[str, SeriesRow] = {}
        self.episodes: dict[str, EpisodeRow] = {}
        self.revisions: dict[str, RevisionRow] = {}
        self.artifacts: dict[str, ArtifactRow] = {}
        self.characters: dict[str, CharacterRow] = {}
        self.locations: dict[str, WorldLocationRow] = {}
        self.props: dict[str, WorldPropRow] = {}
        self.storyboards: dict[str, StoryboardRow] = {}
        self.events: list[EventEnvelope] = []

    # -- projects ----------------------------------------------------------
    async def insert_project(self, row: ProjectRow) -> bool:
        if row.project_id in self.projects:
            return False
        self.projects[row.project_id] = row
        return True

    async def get_project(self, project_id: str) -> ProjectRow | None:
        return self.projects.get(project_id)

    async def list_projects(self) -> tuple[ProjectRow, ...]:
        return tuple(self.projects.values())

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
    ) -> ProjectRow | None:
        existing = self.projects.get(project_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = ProjectRow(
            project_id=existing.project_id,
            title=title if title is not None else existing.title,
            description=description if description is not None else existing.description,
            owner_id=existing.owner_id,
            series_ids_json=series_ids_json if series_ids_json is not None else existing.series_ids_json,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self.projects[project_id] = updated
        return updated

    # -- series ------------------------------------------------------------
    async def insert_series(self, row: SeriesRow) -> bool:
        if row.series_id in self.series:
            return False
        self.series[row.series_id] = row
        return True

    async def get_series(self, series_id: str) -> SeriesRow | None:
        return self.series.get(series_id)

    async def list_series(self, project_id: str | None = None) -> tuple[SeriesRow, ...]:
        if project_id is None:
            return tuple(self.series.values())
        return tuple(row for row in self.series.values() if row.project_id == project_id)

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
    ) -> SeriesRow | None:
        existing = self.series.get(series_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = SeriesRow(
            series_id=existing.series_id,
            project_id=existing.project_id,
            title=title if title is not None else existing.title,
            description=description if description is not None else existing.description,
            episode_ids_json=episode_ids_json if episode_ids_json is not None else existing.episode_ids_json,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self.series[series_id] = updated
        return updated

    # -- episodes -----------------------------------------------------------
    async def insert_episode(self, row: EpisodeRow) -> bool:
        if row.episode_id in self.episodes:
            return False
        self.episodes[row.episode_id] = row
        return True

    async def get_episode(self, episode_id: str) -> EpisodeRow | None:
        return self.episodes.get(episode_id)

    async def list_episodes(self, series_id: str | None = None) -> tuple[EpisodeRow, ...]:
        if series_id is None:
            return tuple(self.episodes.values())
        return tuple(row for row in self.episodes.values() if row.series_id == series_id)

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
    ) -> EpisodeRow | None:
        existing = self.episodes.get(episode_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        # SENTINEL: we need to distinguish "no change to current_revision_id" from "set to None".
        # Handlers always pass current_revision_id only when they intend to update it; for generic
        # title/logline updates they pass None. Preserve existing value in that case unless caller
        # explicitly wants to clear it (not used). We treat current_revision_id not-None as intended.
        resolved_revision_id = existing.current_revision_id
        # Inspect if caller passed current_revision_id as non-None via check of whether any update expects it.
        # For this in-memory store we treat the parameter as set only when it's different from existing and caller meant it.
        # Simpler: if the episode has no current_revision_id yet and caller passes a value, use it; else keep.
        # We detect intent by checking if current_revision_id is not None and different from existing, OR episode currently has None.
        # However we cannot differentiate "don't update" vs "set to None". We workaround: handlers that update revision always pass optimistic_version bump as well.
        # So we treat current_revision_id argument only when it's not None and (existing.current_revision_id != current_revision_id).
        # If existing has a value and caller passes None, we keep existing.
        if current_revision_id is not None and current_revision_id != existing.current_revision_id:
            resolved_revision_id = current_revision_id
        updated = EpisodeRow(
            episode_id=existing.episode_id,
            series_id=existing.series_id,
            project_id=existing.project_id,
            title=title if title is not None else existing.title,
            episode_number=existing.episode_number,
            logline=logline if logline is not None else existing.logline,
            state=state if state is not None else existing.state,
            current_revision_id=resolved_revision_id,
            active_run_id=active_run_id if active_run_id is not None else existing.active_run_id,
            awaiting_checkpoint=awaiting_checkpoint if awaiting_checkpoint is not None else existing.awaiting_checkpoint,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self.episodes[episode_id] = updated
        return updated

    # -- revisions ----------------------------------------------------------
    async def insert_revision(self, row: RevisionRow) -> bool:
        if row.revision_id in self.revisions:
            return False
        self.revisions[row.revision_id] = row
        return True

    async def get_revision(self, revision_id: str) -> RevisionRow | None:
        return self.revisions.get(revision_id)

    async def list_revisions(self, episode_id: str | None = None) -> tuple[RevisionRow, ...]:
        if episode_id is None:
            return tuple(self.revisions.values())
        return tuple(row for row in self.revisions.values() if row.episode_id == episode_id)

    async def update_revision(
        self,
        revision_id: str,
        *,
        status: str | None = None,
        lock_state: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
    ) -> RevisionRow | None:
        existing = self.revisions.get(revision_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = RevisionRow(
            revision_id=existing.revision_id,
            series_id=existing.series_id,
            episode_id=existing.episode_id,
            parent_revision_id=existing.parent_revision_id,
            creator=existing.creator,
            actor=existing.actor,
            created_at=existing.created_at,
            content_hash=existing.content_hash,
            status=status if status is not None else existing.status,
            lock_state=lock_state if lock_state is not None else existing.lock_state,
            invalidation_intent=existing.invalidation_intent,
            summary=existing.summary,
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=existing.metadata_json,
        )
        self.revisions[revision_id] = updated
        return updated

    # -- artifacts ----------------------------------------------------------
    async def insert_artifact(self, row: ArtifactRow) -> bool:
        if row.artifact_id in self.artifacts:
            return False
        self.artifacts[row.artifact_id] = row
        return True

    async def get_artifact(self, artifact_id: str) -> ArtifactRow | None:
        return self.artifacts.get(artifact_id)

    async def list_artifacts(
        self, episode_id: str | None = None, artifact_type: str | None = None
    ) -> tuple[ArtifactRow, ...]:
        rows = self.artifacts.values()
        if episode_id is not None:
            rows = [row for row in rows if row.episode_id == episode_id]  # type: ignore[assignment]
        if artifact_type is not None:
            rows = [row for row in rows if row.artifact_type == artifact_type]  # type: ignore[assignment]
        return tuple(rows)

    # -- characters ---------------------------------------------------------
    async def insert_character(self, row: CharacterRow) -> bool:
        if row.character_id in self.characters:
            return False
        self.characters[row.character_id] = row
        return True

    async def get_character(self, character_id: str) -> CharacterRow | None:
        return self.characters.get(character_id)

    async def list_characters(self, series_id: str | None = None) -> tuple[CharacterRow, ...]:
        if series_id is None:
            return tuple(self.characters.values())
        return tuple(row for row in self.characters.values() if row.series_id == series_id)

    async def update_character(self, character_id: str, *, values: dict[str, Any]) -> CharacterRow | None:
        existing = self.characters.get(character_id)
        if existing is None:
            return None
        # optimistic_version guard already checked by service
        updated = CharacterRow(
            character_id=existing.character_id,
            series_id=existing.series_id,
            name=existing.name,
            display_name=values.get("display_name", existing.display_name),
            role=existing.role,
            archetype=existing.archetype,
            description=values.get("description", existing.description),
            traits_json=values.get("traits_json", existing.traits_json),
            backstory=existing.backstory,
            portrait_artifact_id=existing.portrait_artifact_id,
            created_at=existing.created_at,
            updated_at=values.get("updated_at", datetime.now(UTC)),
            optimistic_version=values.get("optimistic_version", existing.optimistic_version + 1),
            metadata_json=values.get("metadata_json", existing.metadata_json),
        )
        self.characters[character_id] = updated
        return updated

    # -- world --------------------------------------------------------------
    async def upsert_location(self, row: WorldLocationRow) -> WorldLocationRow:
        self.locations[row.location_id] = row
        return row

    async def list_locations(self, series_id: str) -> tuple[WorldLocationRow, ...]:
        return tuple(row for row in self.locations.values() if row.series_id == series_id)

    async def upsert_prop(self, row: WorldPropRow) -> WorldPropRow:
        self.props[row.prop_id] = row
        return row

    async def list_props(self, series_id: str) -> tuple[WorldPropRow, ...]:
        return tuple(row for row in self.props.values() if row.series_id == series_id)

    # -- storyboard ---------------------------------------------------------
    async def insert_storyboard(self, row: StoryboardRow) -> bool:
        if row.storyboard_id in self.storyboards:
            return False
        self.storyboards[row.storyboard_id] = row
        return True

    async def get_storyboard(self, storyboard_id: str) -> StoryboardRow | None:
        return self.storyboards.get(storyboard_id)

    async def list_storyboards(self, episode_id: str | None = None) -> tuple[StoryboardRow, ...]:
        if episode_id is None:
            return tuple(self.storyboards.values())
        return tuple(row for row in self.storyboards.values() if row.episode_id == episode_id)

    async def update_storyboard(
        self, storyboard_id: str, *, panels_json: str | None, optimistic_version: int | None, expected_version: int | None, metadata_json: str | None
    ) -> StoryboardRow | None:
        existing = self.storyboards.get(storyboard_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = StoryboardRow(
            storyboard_id=existing.storyboard_id,
            episode_id=existing.episode_id,
            series_id=existing.series_id,
            title=existing.title,
            panels_json=panels_json if panels_json is not None else existing.panels_json,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self.storyboards[storyboard_id] = updated
        return updated


class InMemoryTransactionScope:
    def __init__(self, store: InMemoryStudioStore) -> None:
        self._store = store
        self._pending: list[tuple[EventEnvelope, str | None]] = []

    async def __aenter__(self) -> InMemoryTransactionScope:
        self._pending.clear()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None
    ) -> bool:
        if exc_type is not None:
            self._pending.clear()
        return False

    def store(self) -> InMemoryStudioStore:
        return self._store

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        self._pending.append((envelope, deduplication_key))
        return True

    async def commit(self) -> None:
        for envelope, _ in self._pending:
            self._store.events.append(envelope)
        self._pending.clear()


def memory_scope_factory(store: InMemoryStudioStore) -> Callable[[], InMemoryTransactionScope]:
    return lambda: InMemoryTransactionScope(store)
