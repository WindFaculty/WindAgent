"""SQL adapter for the Production store."""

from __future__ import annotations

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
    AssetRevisionRow,
    AudioTrackRow,
    CodeVideoProjectRow,
    EdlRow,
    MixPlanRow,
    ProductionAssetRow,
    ProductionProjectRow,
    ProductionRevisionRow,
    RenderJobRow,
)
from ..application.ports import ProductionStore
from .tables import (
    production_asset_revisions_table,
    production_assets_table,
    production_audio_tracks_table,
    production_code_video_projects_table,
    production_edls_table,
    production_mix_plans_table,
    production_projects_table,
    production_render_jobs_table,
    production_revisions_table,
)

STORE_REPOSITORY_NAME = "production_store"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def make_store(session: AsyncSession) -> SqlProductionStore:
    return SqlProductionStore(session)


class SqlProductionStore(ProductionStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- projects ----------------------------------------------------------
    async def insert_project(self, row: ProductionProjectRow) -> bool:
        exists = await self._session.execute(select(production_projects_table.c.project_id).where(production_projects_table.c.project_id == row.project_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_projects_table).values(
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                owner_id=row.owner_id,
                status=row.status,
                current_revision_id=row.current_revision_id,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_project(self, project_id: str) -> ProductionProjectRow | None:
        result = await self._session.execute(select(production_projects_table).where(production_projects_table.c.project_id == project_id))
        row = result.first()
        return _project_from_row(row) if row else None

    async def list_projects(self) -> tuple[ProductionProjectRow, ...]:
        result = await self._session.execute(select(production_projects_table).order_by(production_projects_table.c.created_at.asc()))
        return tuple(_project_from_row(row) for row in result.all())

    async def update_project(
        self,
        project_id: str,
        *,
        title: str | None,
        description: str | None,
        status: str | None,
        current_revision_id: str | None,
        optimistic_version: int | None,
        expected_version: int | None,
        metadata_json: str | None,
    ) -> ProductionProjectRow | None:
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
        if status is not None:
            values["status"] = status
        if current_revision_id is not None:
            values["current_revision_id"] = current_revision_id
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        if expected_version is not None:
            outcome = await self._session.execute(
                update(production_projects_table).where(production_projects_table.c.project_id == project_id, production_projects_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(production_projects_table).where(production_projects_table.c.project_id == project_id).values(**values))
        return await self.get_project(project_id)

    # -- revisions ---------------------------------------------------------
    async def insert_revision(self, row: ProductionRevisionRow) -> bool:
        exists = await self._session.execute(select(production_revisions_table.c.revision_id).where(production_revisions_table.c.revision_id == row.revision_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_revisions_table).values(
                revision_id=row.revision_id,
                project_id=row.project_id,
                parent_revision_id=row.parent_revision_id,
                creator=row.creator,
                actor=row.actor,
                created_at=_as_utc(row.created_at),
                content_hash=row.content_hash,
                status=row.status,
                locked=row.locked,
                invalidation_intent=row.invalidation_intent,
                summary=row.summary,
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_revision(self, revision_id: str) -> ProductionRevisionRow | None:
        result = await self._session.execute(select(production_revisions_table).where(production_revisions_table.c.revision_id == revision_id))
        row = result.first()
        return _revision_from_row(row) if row else None

    async def list_revisions(self, project_id: str | None = None) -> tuple[ProductionRevisionRow, ...]:
        stmt = select(production_revisions_table)
        if project_id is not None:
            stmt = stmt.where(production_revisions_table.c.project_id == project_id)
        stmt = stmt.order_by(production_revisions_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_revision_from_row(row) for row in result.all())

    async def update_revision(
        self,
        revision_id: str,
        *,
        status: str | None = None,
        locked: bool | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
    ) -> ProductionRevisionRow | None:
        existing = await self.get_revision(revision_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        values: dict[str, Any] = {}
        if status is not None:
            values["status"] = status
        if locked is not None:
            values["locked"] = locked
        if optimistic_version is not None:
            values["optimistic_version"] = optimistic_version
        if expected_version is not None:
            outcome = await self._session.execute(
                update(production_revisions_table).where(production_revisions_table.c.revision_id == revision_id, production_revisions_table.c.optimistic_version == expected_version).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
        else:
            await self._session.execute(update(production_revisions_table).where(production_revisions_table.c.revision_id == revision_id).values(**values))
        return await self.get_revision(revision_id)

    # -- assets ------------------------------------------------------------
    async def insert_asset(self, row: ProductionAssetRow) -> bool:
        exists = await self._session.execute(select(production_assets_table.c.asset_id).where(production_assets_table.c.asset_id == row.asset_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_assets_table).values(
                asset_id=row.asset_id,
                project_id=row.project_id,
                name=row.name,
                kind=row.kind,
                lifecycle_state=row.lifecycle_state,
                processing_state=row.processing_state,
                active_revision_id=row.active_revision_id,
                source_type=row.source_type,
                license_state=row.license_state,
                tags_json=row.tags_json,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_asset(self, asset_id: str) -> ProductionAssetRow | None:
        result = await self._session.execute(select(production_assets_table).where(production_assets_table.c.asset_id == asset_id))
        row = result.first()
        return _asset_from_row(row) if row else None

    async def list_assets(self, project_id: str | None = None) -> tuple[ProductionAssetRow, ...]:
        stmt = select(production_assets_table)
        if project_id is not None:
            stmt = stmt.where(production_assets_table.c.project_id == project_id)
        stmt = stmt.order_by(production_assets_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_asset_from_row(row) for row in result.all())

    async def update_asset(self, asset_id: str, *, values: dict[str, Any]) -> ProductionAssetRow | None:
        # handle optimistic version guard if expected_version present
        expected = values.pop("expected_version", None)
        if expected is not None:
            existing = await self.get_asset(asset_id)
            if existing is None or existing.optimistic_version != expected:
                return None
            outcome = await self._session.execute(
                update(production_assets_table).where(production_assets_table.c.asset_id == asset_id, production_assets_table.c.optimistic_version == expected).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
            return await self.get_asset(asset_id)
        await self._session.execute(update(production_assets_table).where(production_assets_table.c.asset_id == asset_id).values(**values))
        return await self.get_asset(asset_id)

    # -- asset revisions ---------------------------------------------------
    async def insert_asset_revision(self, row: AssetRevisionRow) -> bool:
        exists = await self._session.execute(select(production_asset_revisions_table.c.revision_id).where(production_asset_revisions_table.c.revision_id == row.revision_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_asset_revisions_table).values(
                revision_id=row.revision_id,
                asset_id=row.asset_id,
                supersedes_revision_id=row.supersedes_revision_id,
                content_hash=row.content_hash,
                media_type=row.media_type,
                mime_type=row.mime_type,
                size_bytes=row.size_bytes,
                normalized_format=row.normalized_format,
                preview_json=row.preview_json,
                validation_json=row.validation_json,
                provenance_json=row.provenance_json,
                created_at=_as_utc(row.created_at),
            )
        )
        return True

    async def get_asset_revision(self, revision_id: str) -> AssetRevisionRow | None:
        result = await self._session.execute(select(production_asset_revisions_table).where(production_asset_revisions_table.c.revision_id == revision_id))
        row = result.first()
        return _asset_revision_from_row(row) if row else None

    async def list_asset_revisions(self, asset_id: str | None = None) -> tuple[AssetRevisionRow, ...]:
        stmt = select(production_asset_revisions_table)
        if asset_id is not None:
            stmt = stmt.where(production_asset_revisions_table.c.asset_id == asset_id)
        stmt = stmt.order_by(production_asset_revisions_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_asset_revision_from_row(row) for row in result.all())

    # -- audio tracks ------------------------------------------------------
    async def insert_audio_track(self, row: AudioTrackRow) -> bool:
        exists = await self._session.execute(select(production_audio_tracks_table.c.track_id).where(production_audio_tracks_table.c.track_id == row.track_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_audio_tracks_table).values(
                track_id=row.track_id,
                project_id=row.project_id,
                kind=row.kind,
                title=row.title,
                character_id=row.character_id,
                dialogue_text=row.dialogue_text,
                source_path=row.source_path,
                source_hash=row.source_hash,
                sample_rate=row.sample_rate,
                channels=row.channels,
                duration_seconds=row.duration_seconds,
                language=row.language,
                voice_profile_id=row.voice_profile_id,
                rights_state=row.rights_state,
                provenance_json=row.provenance_json,
                created_at=_as_utc(row.created_at),
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_audio_track(self, track_id: str) -> AudioTrackRow | None:
        result = await self._session.execute(select(production_audio_tracks_table).where(production_audio_tracks_table.c.track_id == track_id))
        row = result.first()
        return _audio_track_from_row(row) if row else None

    async def list_audio_tracks(self, project_id: str | None = None) -> tuple[AudioTrackRow, ...]:
        stmt = select(production_audio_tracks_table)
        if project_id is not None:
            stmt = stmt.where(production_audio_tracks_table.c.project_id == project_id)
        stmt = stmt.order_by(production_audio_tracks_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_audio_track_from_row(row) for row in result.all())

    async def update_audio_track(self, track_id: str, *, values: dict[str, Any]) -> AudioTrackRow | None:
        await self._session.execute(update(production_audio_tracks_table).where(production_audio_tracks_table.c.track_id == track_id).values(**values))
        return await self.get_audio_track(track_id)

    # -- mix plans ---------------------------------------------------------
    async def insert_mix_plan(self, row: MixPlanRow) -> bool:
        exists = await self._session.execute(select(production_mix_plans_table.c.mix_plan_id).where(production_mix_plans_table.c.mix_plan_id == row.mix_plan_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_mix_plans_table).values(
                mix_plan_id=row.mix_plan_id,
                project_id=row.project_id,
                title=row.title,
                loudness_target_lufs=row.loudness_target_lufs,
                peak_ceiling_db=row.peak_ceiling_db,
                policy_version=row.policy_version,
                tracks_json=row.tracks_json,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_mix_plan(self, mix_plan_id: str) -> MixPlanRow | None:
        result = await self._session.execute(select(production_mix_plans_table).where(production_mix_plans_table.c.mix_plan_id == mix_plan_id))
        row = result.first()
        return _mix_plan_from_row(row) if row else None

    async def list_mix_plans(self, project_id: str | None = None) -> tuple[MixPlanRow, ...]:
        stmt = select(production_mix_plans_table)
        if project_id is not None:
            stmt = stmt.where(production_mix_plans_table.c.project_id == project_id)
        stmt = stmt.order_by(production_mix_plans_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_mix_plan_from_row(row) for row in result.all())

    async def update_mix_plan(self, mix_plan_id: str, *, values: dict[str, Any]) -> MixPlanRow | None:
        await self._session.execute(update(production_mix_plans_table).where(production_mix_plans_table.c.mix_plan_id == mix_plan_id).values(**values))
        return await self.get_mix_plan(mix_plan_id)

    # -- code video --------------------------------------------------------
    async def insert_code_video_project(self, row: CodeVideoProjectRow) -> bool:
        exists = await self._session.execute(select(production_code_video_projects_table.c.project_id).where(production_code_video_projects_table.c.project_id == row.project_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_code_video_projects_table).values(
                project_id=row.project_id,
                title=row.title,
                description=row.description,
                status=row.status,
                repo_url=row.repo_url,
                branch=row.branch,
                tutorial_steps_json=row.tutorial_steps_json,
                current_checkpoint=row.current_checkpoint,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_code_video_project(self, project_id: str) -> CodeVideoProjectRow | None:
        result = await self._session.execute(select(production_code_video_projects_table).where(production_code_video_projects_table.c.project_id == project_id))
        row = result.first()
        return _code_video_from_row(row) if row else None

    async def list_code_video_projects(self) -> tuple[CodeVideoProjectRow, ...]:
        result = await self._session.execute(select(production_code_video_projects_table).order_by(production_code_video_projects_table.c.created_at.asc()))
        return tuple(_code_video_from_row(row) for row in result.all())

    async def update_code_video_project(self, project_id: str, *, values: dict[str, Any]) -> CodeVideoProjectRow | None:
        expected = values.pop("expected_version", None)
        if expected is not None:
            existing = await self.get_code_video_project(project_id)
            if existing is None or existing.optimistic_version != expected:
                return None
            outcome = await self._session.execute(
                update(production_code_video_projects_table).where(production_code_video_projects_table.c.project_id == project_id, production_code_video_projects_table.c.optimistic_version == expected).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
            return await self.get_code_video_project(project_id)
        await self._session.execute(update(production_code_video_projects_table).where(production_code_video_projects_table.c.project_id == project_id).values(**values))
        return await self.get_code_video_project(project_id)

    # -- render jobs -------------------------------------------------------
    async def insert_render_job(self, row: RenderJobRow) -> bool:
        exists = await self._session.execute(select(production_render_jobs_table.c.job_id).where(production_render_jobs_table.c.job_id == row.job_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_render_jobs_table).values(
                job_id=row.job_id,
                project_id=row.project_id,
                revision_id=row.revision_id,
                scene_id=row.scene_id,
                shot_id=row.shot_id,
                status=row.status,
                frame_start=row.frame_start,
                frame_end=row.frame_end,
                colorspace=row.colorspace,
                profile_id=row.profile_id,
                attempt=row.attempt,
                input_hash=row.input_hash,
                output_hash=row.output_hash,
                error=row.error,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                optimistic_version=row.optimistic_version,
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_render_job(self, job_id: str) -> RenderJobRow | None:
        result = await self._session.execute(select(production_render_jobs_table).where(production_render_jobs_table.c.job_id == job_id))
        row = result.first()
        return _render_job_from_row(row) if row else None

    async def list_render_jobs(self, project_id: str | None = None) -> tuple[RenderJobRow, ...]:
        stmt = select(production_render_jobs_table)
        if project_id is not None:
            stmt = stmt.where(production_render_jobs_table.c.project_id == project_id)
        stmt = stmt.order_by(production_render_jobs_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_render_job_from_row(row) for row in result.all())

    async def update_render_job(self, job_id: str, *, values: dict[str, Any]) -> RenderJobRow | None:
        expected = values.pop("expected_version", None)
        if expected is not None:
            existing = await self.get_render_job(job_id)
            if existing is None or existing.optimistic_version != expected:
                return None
            outcome = await self._session.execute(
                update(production_render_jobs_table).where(production_render_jobs_table.c.job_id == job_id, production_render_jobs_table.c.optimistic_version == expected).values(**values)
            )
            if cast(CursorResult[Any], outcome).rowcount == 0:
                return None
            return await self.get_render_job(job_id)
        await self._session.execute(update(production_render_jobs_table).where(production_render_jobs_table.c.job_id == job_id).values(**values))
        return await self.get_render_job(job_id)

    # -- edls --------------------------------------------------------------
    async def insert_edl(self, row: EdlRow) -> bool:
        exists = await self._session.execute(select(production_edls_table.c.edl_id).where(production_edls_table.c.edl_id == row.edl_id))
        if exists.first() is not None:
            return False
        await self._session.execute(
            insert(production_edls_table).values(
                edl_id=row.edl_id,
                project_id=row.project_id,
                revision_id=row.revision_id,
                title=row.title,
                status=row.status,
                items_json=row.items_json,
                audio_mix_plan_id=row.audio_mix_plan_id,
                subtitle_track_id=row.subtitle_track_id,
                encoding_profile_json=row.encoding_profile_json,
                edl_hash=row.edl_hash,
                created_at=_as_utc(row.created_at),
                updated_at=_as_utc(row.updated_at),
                metadata_json=row.metadata_json,
            )
        )
        return True

    async def get_edl(self, edl_id: str) -> EdlRow | None:
        result = await self._session.execute(select(production_edls_table).where(production_edls_table.c.edl_id == edl_id))
        row = result.first()
        return _edl_from_row(row) if row else None

    async def list_edls(self, project_id: str | None = None) -> tuple[EdlRow, ...]:
        stmt = select(production_edls_table)
        if project_id is not None:
            stmt = stmt.where(production_edls_table.c.project_id == project_id)
        stmt = stmt.order_by(production_edls_table.c.created_at.asc())
        result = await self._session.execute(stmt)
        return tuple(_edl_from_row(row) for row in result.all())

    async def update_edl(self, edl_id: str, *, values: dict[str, Any]) -> EdlRow | None:
        await self._session.execute(update(production_edls_table).where(production_edls_table.c.edl_id == edl_id).values(**values))
        return await self.get_edl(edl_id)


class SqlTransactionScope:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):  # pragma: no cover
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

    def store(self) -> ProductionStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return cast(ProductionStore, self._uow.repository(STORE_REPOSITORY_NAME))

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


def _project_from_row(row: Any) -> ProductionProjectRow:
    return ProductionProjectRow(
        project_id=str(row.project_id),
        title=str(row.title),
        description=str(row.description),
        owner_id=str(row.owner_id),
        status=str(row.status),
        current_revision_id=str(row.current_revision_id) if row.current_revision_id is not None else None,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _revision_from_row(row: Any) -> ProductionRevisionRow:
    return ProductionRevisionRow(
        revision_id=str(row.revision_id),
        project_id=str(row.project_id),
        parent_revision_id=str(row.parent_revision_id) if row.parent_revision_id is not None else None,
        creator=str(row.creator),
        actor=str(row.actor),
        created_at=_as_utc(row.created_at),
        content_hash=str(row.content_hash),
        status=str(row.status),
        locked=bool(row.locked),
        invalidation_intent=str(row.invalidation_intent) if row.invalidation_intent is not None else None,
        summary=str(row.summary),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _asset_from_row(row: Any) -> ProductionAssetRow:
    return ProductionAssetRow(
        asset_id=str(row.asset_id),
        project_id=str(row.project_id) if row.project_id is not None else None,
        name=str(row.name),
        kind=str(row.kind),
        lifecycle_state=str(row.lifecycle_state),
        processing_state=str(row.processing_state),
        active_revision_id=str(row.active_revision_id) if row.active_revision_id is not None else None,
        source_type=str(row.source_type),
        license_state=str(row.license_state),
        tags_json=str(row.tags_json),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _asset_revision_from_row(row: Any) -> AssetRevisionRow:
    return AssetRevisionRow(
        revision_id=str(row.revision_id),
        asset_id=str(row.asset_id),
        supersedes_revision_id=str(row.supersedes_revision_id) if row.supersedes_revision_id is not None else None,
        content_hash=str(row.content_hash),
        media_type=str(row.media_type),
        mime_type=str(row.mime_type),
        size_bytes=int(row.size_bytes),
        normalized_format=str(row.normalized_format) if row.normalized_format is not None else None,
        preview_json=str(row.preview_json),
        validation_json=str(row.validation_json),
        provenance_json=str(row.provenance_json),
        created_at=_as_utc(row.created_at),
    )


def _audio_track_from_row(row: Any) -> AudioTrackRow:
    return AudioTrackRow(
        track_id=str(row.track_id),
        project_id=str(row.project_id),
        kind=str(row.kind),
        title=str(row.title),
        character_id=str(row.character_id) if row.character_id is not None else None,
        dialogue_text=str(row.dialogue_text),
        source_path=str(row.source_path),
        source_hash=str(row.source_hash),
        sample_rate=int(row.sample_rate),
        channels=int(row.channels),
        duration_seconds=float(row.duration_seconds),
        language=str(row.language),
        voice_profile_id=str(row.voice_profile_id) if row.voice_profile_id is not None else None,
        rights_state=str(row.rights_state),
        provenance_json=str(row.provenance_json),
        created_at=_as_utc(row.created_at),
        metadata_json=str(row.metadata_json),
    )


def _mix_plan_from_row(row: Any) -> MixPlanRow:
    return MixPlanRow(
        mix_plan_id=str(row.mix_plan_id),
        project_id=str(row.project_id),
        title=str(row.title),
        loudness_target_lufs=float(row.loudness_target_lufs),
        peak_ceiling_db=float(row.peak_ceiling_db),
        policy_version=str(row.policy_version),
        tracks_json=str(row.tracks_json),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        metadata_json=str(row.metadata_json),
    )


def _code_video_from_row(row: Any) -> CodeVideoProjectRow:
    return CodeVideoProjectRow(
        project_id=str(row.project_id),
        title=str(row.title),
        description=str(row.description),
        status=str(row.status),
        repo_url=str(row.repo_url),
        branch=str(row.branch),
        tutorial_steps_json=str(row.tutorial_steps_json),
        current_checkpoint=str(row.current_checkpoint) if row.current_checkpoint is not None else None,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _render_job_from_row(row: Any) -> RenderJobRow:
    return RenderJobRow(
        job_id=str(row.job_id),
        project_id=str(row.project_id),
        revision_id=str(row.revision_id) if row.revision_id is not None else None,
        scene_id=str(row.scene_id),
        shot_id=str(row.shot_id),
        status=str(row.status),
        frame_start=int(row.frame_start),
        frame_end=int(row.frame_end),
        colorspace=str(row.colorspace),
        profile_id=str(row.profile_id),
        attempt=int(row.attempt),
        input_hash=str(row.input_hash),
        output_hash=str(row.output_hash),
        error=str(row.error),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        optimistic_version=int(row.optimistic_version),
        metadata_json=str(row.metadata_json),
    )


def _edl_from_row(row: Any) -> EdlRow:
    return EdlRow(
        edl_id=str(row.edl_id),
        project_id=str(row.project_id),
        revision_id=str(row.revision_id),
        title=str(row.title),
        status=str(row.status),
        items_json=str(row.items_json),
        audio_mix_plan_id=str(row.audio_mix_plan_id),
        subtitle_track_id=str(row.subtitle_track_id) if row.subtitle_track_id is not None else None,
        encoding_profile_json=str(row.encoding_profile_json),
        edl_hash=str(row.edl_hash),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        metadata_json=str(row.metadata_json),
    )
