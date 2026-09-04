"""SQL adapter for the Studio store."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from windagent.kernel.events import EventEnvelope
from windagent.platform.events.outbox import TransactionalOutbox
from windagent.platform.persistence.database import Database
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

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
from .tables import (
    artifacts_table,
    characters_table,
    episodes_table,
    projects_table,
    revisions_table,
    series_table,
    storyboards_table,
    world_locations_table,
    world_props_table,
)

STORE_REPOSITORY_NAME = "studio_store"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def make_store(session: AsyncSession) -> SqlStudioStore:
    return SqlStudioStore(session)


class SqlStudioStore(StudioStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- projects ----------------------------------------------------------
    async def insert_project(self, row: ProjectRow) -> bool:
        exists = await self._session.execute(select(projects_table.c.project_id).where(projects_table.c.project_id == row.project_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(projects_table).values(
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                owner_id=row.owner_id,
                series_ids_json=row.series_ids_json,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_project(self, project_id: str) -> ProjectRow | None:
        result = await self._session.execute(select(projects_table).where(projects_table.c.project_id == project_id))
        row = result.first()
        return _project_from_row(row) if row else None

    async def list_projects(self) -> tuple[ProjectRow, ...]:
        result = await self._session.execute(select(projects_table).order_by(projects_table.c.created_at.asc()))
        return tuple(_project_from_row(row) for row in result.all())

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
        existing = await self.get_project(project_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if title is not None:
            values["title"] = title
        if description is not None:
            values["description"] = description
        if series_ids_json is not None:
            values["series_ids_json"] = series_ids_json
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if expected_version is not None:
            outcome = await self._session.execute(
                update(projects_table).where(projects_table.c.project_id == project_id, projects_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(projects_table).where(projects_table.c.project_id == project_id).values(**values))
        return await self.get_project(project_id)

    # -- series ------------------------------------------------------------
    async def insert_series(self, row: SeriesRow) -> bool:
        exists = await self._session.execute(select(series_table.c.series_id).where(series_table.c.series_id == row.series_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(series_table).values(
                series_id=row.series_id,
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                episode_ids_json=row.episode_ids_json,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_series(self, series_id: str) -> SeriesRow | None:
        result = await self._session.execute(select(series_table).where(series_table.c.series_id == series_id))
        row = result.first()
        return _series_from_row(row) if row else None

    async def list_series(self, project_id: str | None = None) -> tuple[SeriesRow, ...]:
        stmt = select(series_table)
        if project_id is not None:
            stmt = stmt.where(series_table.c.project_id == project_id)
        stmt = stmt.order_by(series_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_series_from_row(row) for row in result.all())

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
        existing = await self.get_series(series_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if title is not None:
            values["title"] = title
        if description is not None:
            values["description"] = description
        if episode_ids_json is not None:
            values["episode_ids_json"] = episode_ids_json
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if expected_version is not None:
            outcome = await self._session.execute(
                update(series_table).where(series_table.c.series_id == series_id, series_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(series_table).where(series_table.c.series_id == series_id).values(**values))
        return await self.get_series(series_id)

    # -- episodes -----------------------------------------------------------
    async def insert_episode(self, row: EpisodeRow) -> bool:
        exists = await self._session.execute(select(episodes_table.c.episode_id).where(episodes_table.c.episode_id == row.episode_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(episodes_table).values(
                episode_id=row.episode_id,
                series_id=row.series_id,
                project_id=row.project_id,
                title=row.title,
                episode_number=row.episode_number,
                logline=row.logline,
                state=row.state,
                current_revision_id=row.current_revision_id,
                active_run_id=row.active_run_id,
                awaiting_checkpoint=row.awaiting_checkpoint,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_episode(self, episode_id: str) -> EpisodeRow | None:
        result = await self._session.execute(select(episodes_table).where(episodes_table.c.episode_id == episode_id))
        row = result.first()
        return _episode_from_row(row) if row else None

    async def list_episodes(self, series_id: str | None = None) -> tuple[EpisodeRow, ...]:
        stmt = select(episodes_table)
        if series_id is not None:
            stmt = stmt.where(episodes_table.c.series_id == series_id)
        stmt = stmt.order_by(episodes_table.c.episode_number.asc())
        result = await self._session.execute(stmt)
        return tuple(_episode_from_row(row) for row in result.all())

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
        existing = await self.get_episode(episode_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if title is not None:
            values["title"] = title
        if logline is not None:
            values["logline"] = logline
        if state is not None:
            values["state"] = state
        if current_revision_id is not None:
            values["current_revision_id"] = current_revision_id
        if active_run_id is not None:
            values["active_run_id"] = active_run_id
        if awaiting_checkpoint is not None:
            values["awaiting_checkpoint"] = awaiting_checkpoint
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if expected_version is not None:
            outcome = await self._session.execute(
                update(episodes_table).where(episodes_table.c.episode_id == episode_id, episodes_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(episodes_table).where(episodes_table.c.episode_id == episode_id).values(**values))
        return await self.get_episode(episode_id)

    # -- revisions ----------------------------------------------------------
    async def insert_revision(self, row: RevisionRow) -> bool:
        exists = await self._session.execute(select(revisions_table.c.revision_id).where(revisions_table.c.revision_id == row.revision_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(revisions_table).values(
                revision_id=row.revision_id,
                series_id=row.series_id,
                episode_id=row.episode_id,
                parent_revision_id=row.parent_revision_id,
                creator=row.creator,
                actor=row.actor,
                created_at=_as_utc(row.created_at),
                content_hash=row.content_hash,
                status=row.status,
                lock_state=row.lock_state,
                invalidation_intent=row.invalidation_intent,
                summary=row.summary,
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_revision(self, revision_id: str) -> RevisionRow | None:
        result = await self._session.execute(select(revisions_table).where(revisions_table.c.revision_id == revision_id))
        row = result.first()
        return _revision_from_row(row) if row else None

    async def list_revisions(self, episode_id: str | None = None) -> tuple[RevisionRow, ...]:
        stmt = select(revisions_table)
        if episode_id is not None:
            stmt = stmt.where(revisions_table.c.episode_id == episode_id)
        stmt = stmt.order_by(revisions_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_revision_from_row(row) for row in result.all())

    async def update_revision(
        self,
        revision_id: str,
        *,
        status: str | None = None,
        lock_state: str | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
    ) -> RevisionRow | None:
        existing = await self.get_revision(revision_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {}
        if status is not None:
            values["status"] = status
        if lock_state is not None:
            values["lock_state"] = lock_state
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if expected_version is not None:
            outcome = await self._session.execute(
                update(revisions_table).where(revisions_table.c.revision_id == revision_id, revisions_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(revisions_table).where(revisions_table.c.revision_id == revision_id).values(**values))
        return await self.get_revision(revision_id)

    # -- artifacts ----------------------------------------------------------
    async def insert_artifact(self, row: ArtifactRow) -> bool:
        exists = await self._session.execute(select(artifacts_table.c.artifact_id).where(artifacts_table.c.artifact_id == row.artifact_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(artifacts_table).values(
                artifact_id=row.artifact_id,
                artifact_type=row.artifact_type,
                schema_version=row.schema_version,
                series_id=row.series_id,
                episode_id=row.episode_id,
                revision_id=row.revision_id,
                content_hash=row.content_hash,
                input_refs_json=row.input_refs_json,
                created_at=_as_utc(row.created_at),
                created_by=row.created_by,
                content_json=row.content_json,
                extra_json=row.extra_json,
            )
        )
        return True

    async def get_artifact(self, artifact_id: str) -> ArtifactRow | None:
        result = await self._session.execute(select(artifacts_table).where(artifacts_table.c.artifact_id == artifact_id))
        row = result.first()
        return _artifact_from_row(row) if row else None

    async def list_artifacts(
        self, episode_id: str | None = None, artifact_type: str | None = None
    ) -> tuple[ArtifactRow, ...]:
        stmt = select(artifacts_table)
        if episode_id is not None:
            stmt = stmt.where(artifacts_table.c.episode_id == episode_id)
        if artifact_type is not None:
            stmt = stmt.where(artifacts_table.c.artifact_type == artifact_type)
        stmt = stmt.order_by(artifacts_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_artifact_from_row(row) for row in result.all())

    # -- characters ---------------------------------------------------------
    async def insert_character(self, row: CharacterRow) -> bool:
        exists = await self._session.execute(select(characters_table.c.character_id).where(characters_table.c.character_id == row.character_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(characters_table).values(
                character_id=row.character_id,
                series_id=row.series_id,
                name=row.name,
                display_name=row.display_name,
                role=row.role,
                archetype=row.archetype,
                description=row.description,
                traits_json=row.traits_json,
                backstory=row.backstory,
                portrait_artifact_id=row.portrait_artifact_id,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_character(self, character_id: str) -> CharacterRow | None:
        result = await self._session.execute(select(characters_table).where(characters_table.c.character_id == character_id))
        row = result.first()
        return _character_from_row(row) if row else None

    async def list_characters(self, series_id: str | None = None) -> tuple[CharacterRow, ...]:
        stmt = select(characters_table)
        if series_id is not None:
            stmt = stmt.where(characters_table.c.series_id == series_id)
        stmt = stmt.order_by(characters_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_character_from_row(row) for row in result.all())

    async def update_character(self, character_id: str, *, values: dict[str, Any]) -> CharacterRow | None:
        await self._session.execute(update(characters_table).where(characters_table.c.character_id == character_id).values(**values))
        return await self.get_character(character_id)

    # -- world --------------------------------------------------------------
    async def upsert_location(self, row: WorldLocationRow) -> WorldLocationRow:
        existing = await self._session.execute(select(world_locations_table.c.location_id).where(world_locations_table.c.location_id == row.location_id))
        if existing.first() is None:
            await self._session.execute(
                insert(world_locations_table).values(
                    location_id=row.location_id,
                    series_id=row.series_id,
                    name=row.name,
                    description=row.description,
                    geography=row.geography,
                    metadata_json=row.metadata_json,
                    created_at=_as_utc(row.created_at),
                    updated_at=_as_utc(row.updated_at),
                )
            )
        else:
            await self._session.execute(
                update(world_locations_table).where(world_locations_table.c.location_id == row.location_id).values(
                    name=row.name, description=row.description, geography=row.geography, metadata_json=row.metadata_json, updated_at=_as_utc(row.updated_at)
                )
            )
        result = await self._session.execute(select(world_locations_table).where(world_locations_table.c.location_id == row.location_id))
        row_obj = result.first()
        assert row_obj is not None
        return WorldLocationRow(
            location_id=str(row_obj.location_id),
            series_id=str(row_obj.series_id),
            name=str(row_obj.name),
            description=str(row_obj.description),
            geography=str(row_obj.geography),
            metadata_json=str(row_obj.metadata_json),
            created_at=_as_utc(row_obj.created_at),
            updated_at=_as_utc(row_obj.updated_at),
        )

    async def list_locations(self, series_id: str) -> tuple[WorldLocationRow, ...]:
        result = await self._session.execute(select(world_locations_table).where(world_locations_table.c.series_id == series_id))
        return tuple(
            WorldLocationRow(
                location_id=str(row.location_id),
                series_id=str(row.series_id),
                name=str(row.name),
                description=str(row.description),
                geography=str(row.geography),
                metadata_json=str(row.metadata_json),
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
            )
            for row in result.all()
        )

    async def upsert_prop(self, row: WorldPropRow) -> WorldPropRow:
        existing = await self._session.execute(select(world_props_table.c.prop_id).where(world_props_table.c.prop_id == row.prop_id))
        if existing.first() is None:
            await self._session.execute(
                insert(world_props_table).values(
                    prop_id=row.prop_id,
                    series_id=row.series_id,
                    name=row.name,
                    description=row.description,
                    significance=row.significance,
                    metadata_json=row.metadata_json,
                    created_at=_as_utc(row.created_at),
                    updated_at=_as_utc(row.updated_at),
                )
            )
        else:
            await self._session.execute(
                update(world_props_table).where(world_props_table.c.prop_id == row.prop_id).values(
                    name=row.name, description=row.description, significance=row.significance, metadata_json=row.metadata_json, updated_at=_as_utc(row.updated_at)
                )
            )
        result = await self._session.execute(select(world_props_table).where(world_props_table.c.prop_id == row.prop_id))
        row_obj = result.first()
        assert row_obj is not None
        return WorldPropRow(
            prop_id=str(row_obj.prop_id),
            series_id=str(row_obj.series_id),
            name=str(row_obj.name),
            description=str(row_obj.description),
            significance=str(row_obj.significance),
            metadata_json=str(row_obj.metadata_json),
            created_at=_as_utc(row_obj.created_at),
            updated_at=_as_utc(row_obj.updated_at),
        )

    async def list_props(self, series_id: str) -> tuple[WorldPropRow, ...]:
        result = await self._session.execute(select(world_props_table).where(world_props_table.c.series_id == series_id))
        return tuple(
            WorldPropRow(
                prop_id=str(row.prop_id),
                series_id=str(row.series_id),
                name=str(row.name),
                description=str(row.description),
                significance=str(row.significance),
                metadata_json=str(row.metadata_json),
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
            )
            for row in result.all()
        )

    # -- storyboard ---------------------------------------------------------
    async def insert_storyboard(self, row: StoryboardRow) -> bool:
        exists = await self._session.execute(select(storyboards_table.c.storyboard_id).where(storyboards_table.c.storyboard_id == row.storyboard_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(storyboards_table).values(
                storyboard_id=row.storyboard_id,
                episode_id=row.episode_id,
                series_id=row.series_id,
                title=row.title,
                panels_json=row.panels_json,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_storyboard(self, storyboard_id: str) -> StoryboardRow | None:
        result = await self._session.execute(select(storyboards_table).where(storyboards_table.c.storyboard_id == storyboard_id))
        row = result.first()
        return _storyboard_from_row(row) if row else None

    async def list_storyboards(self, episode_id: str | None = None) -> tuple[StoryboardRow, ...]:
        stmt = select(storyboards_table)
        if episode_id is not None:
            stmt = stmt.where(storyboards_table.c.episode_id == episode_id)
        stmt = stmt.order_by(storyboards_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_storyboard_from_row(row) for row in result.all())

    async def update_storyboard(
        self, storyboard_id: str, *, panels_json: str | None, optimistic_version: int | None, expected_version: int | None, metadata_json: str | None
    ) -> StoryboardRow | None:
        existing = await self.get_storyboard(storyboard_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if panels_json is not None:
            values["panels_json"] = panels_json
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if expected_version is not None:
            outcome = await self._session.execute(
                update(storyboards_table).where(storyboards_table.c.storyboard_id == storyboard_id, storyboards_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(storyboards_table).where(storyboards_table.c.storyboard_id == storyboard_id).values(**values))
        return await self.get_storyboard(storyboard_id)


class SqlTransactionScope:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):  # pragma: no cover - composition guard
            raise TypeError("transaction scope requires a SQL unit of work")
        uow.register_repository(STORE_REPOSITORY_NAME, make_store)
        self._uow = uow
        await uow.__aenter__()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None) -> bool:
        if self._uow is not None:
            await self._uow.__aexit__(exc_type, exc_value, None)
            self._uow = None
        return False

    def store(self) -> StudioStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return cast(StudioStore, self._uow.repository(STORE_REPOSITORY_NAME))

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        outbox = TransactionalOutbox(self._uow)
        return await outbox.record_next(envelope, deduplication_key=deduplication_key)

    async def commit(self) -> None:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        await self._uow.commit()


def sql_scope_factory(database: Database) -> Callable[[], SqlTransactionScope]:
    return lambda: SqlTransactionScope(database)


# --------------------------------------------------------------------------- #
# Row mappers
# --------------------------------------------------------------------------- #


def _project_from_row(row: Any) -> ProjectRow:
    return ProjectRow(
        project_id=str(row.project_id),
        title=str(row.title),
        description=str(row.description),
        owner_id=str(row.owner_id),
        series_ids_json=str(row.series_ids_json),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _series_from_row(row: Any) -> SeriesRow:
    return SeriesRow(
        series_id=str(row.series_id),
        project_id=str(row.project_id) if row.project_id is not None else None,
        title=str(row.title),
        description=str(row.description),
        episode_ids_json=str(row.episode_ids_json),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _episode_from_row(row: Any) -> EpisodeRow:
    return EpisodeRow(
        episode_id=str(row.episode_id),
        series_id=str(row.series_id),
        project_id=str(row.project_id) if row.project_id is not None else None,
        title=str(row.title),
        episode_number=int(row.episode_number),
        logline=str(row.logline),
        state=str(row.state),
        current_revision_id=str(row.current_revision_id) if row.current_revision_id is not None else None,
        active_run_id=str(row.active_run_id) if row.active_run_id is not None else None,
        awaiting_checkpoint=str(row.awaiting_checkpoint) if row.awaiting_checkpoint is not None else None,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _revision_from_row(row: Any) -> RevisionRow:
    return RevisionRow(
        revision_id=str(row.revision_id),
        series_id=str(row.series_id),
        episode_id=str(row.episode_id),
        parent_revision_id=str(row.parent_revision_id) if row.parent_revision_id is not None else None,
        creator=str(row.creator),
        actor=str(row.actor),
        created_at=_as_utc(row.created_at),
        content_hash=str(row.content_hash),
        status=str(row.status),
        lock_state=str(row.lock_state),
        invalidation_intent=str(row.invalidation_intent) if row.invalidation_intent is not None else None,
        summary=str(row.summary),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _artifact_from_row(row: Any) -> ArtifactRow:
    return ArtifactRow(
        artifact_id=str(row.artifact_id),
        artifact_type=str(row.artifact_type),
        schema_version=str(row.schema_version),
        series_id=str(row.series_id),
        episode_id=str(row.episode_id),
        revision_id=str(row.revision_id) if row.revision_id is not None else None,
        content_hash=str(row.content_hash),
        input_refs_json=str(row.input_refs_json),
        created_at=_as_utc(row.created_at),
        created_by=str(row.created_by),
        content_json=str(row.content_json),
        extra_json=str(row.extra_json),
    )


def _character_from_row(row: Any) -> CharacterRow:
    return CharacterRow(
        character_id=str(row.character_id),
        series_id=str(row.series_id),
        name=str(row.name),
        display_name=str(row.display_name),
        role=str(row.role),
        archetype=str(row.archetype),
        description=str(row.description),
        traits_json=str(row.traits_json),
        backstory=str(row.backstory),
        portrait_artifact_id=str(row.portrait_artifact_id) if row.portrait_artifact_id is not None else None,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _storyboard_from_row(row: Any) -> StoryboardRow:
    return StoryboardRow(
        storyboard_id=str(row.storyboard_id),
        episode_id=str(row.episode_id),
        series_id=str(row.series_id),
        title=str(row.title),
        panels_json=str(row.panels_json),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )
