"""In-memory Production store and transaction scope for unit tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from windagent.kernel.events import EventEnvelope

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


class InMemoryProductionStore(ProductionStore):
    def __init__(self) -> None:
        self.projects: dict[str, ProductionProjectRow] = {}
        self.revisions: dict[str, ProductionRevisionRow] = {}
        self.assets: dict[str, ProductionAssetRow] = {}
        self.asset_revisions: dict[str, AssetRevisionRow] = {}
        self.audio_tracks: dict[str, AudioTrackRow] = {}
        self.mix_plans: dict[str, MixPlanRow] = {}
        self.code_video_projects: dict[str, CodeVideoProjectRow] = {}
        self.render_jobs: dict[str, RenderJobRow] = {}
        self.edls: dict[str, EdlRow] = {}
        self.events: list[EventEnvelope] = []

    # -- projects ----------------------------------------------------------
    async def insert_project(self, row: ProductionProjectRow) -> bool:
        if row.project_id in self.projects:
            return False
        self.projects[row.project_id] = row
        return True

    async def get_project(self, project_id: str) -> ProductionProjectRow | None:
        return self.projects.get(project_id)

    async def list_projects(self) -> tuple[ProductionProjectRow, ...]:
        return tuple(self.projects.values())

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
        existing = self.projects.get(project_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = ProductionProjectRow(
            project_id=existing.project_id,
            title=title if title is not None else existing.title,
            description=description if description is not None else existing.description,
            owner_id=existing.owner_id,
            status=status if status is not None else existing.status,
            current_revision_id=current_revision_id if current_revision_id is not None else existing.current_revision_id,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=metadata_json if metadata_json is not None else existing.metadata_json,
        )
        self.projects[project_id] = updated
        return updated

    # -- revisions ---------------------------------------------------------
    async def insert_revision(self, row: ProductionRevisionRow) -> bool:
        if row.revision_id in self.revisions:
            return False
        self.revisions[row.revision_id] = row
        return True

    async def get_revision(self, revision_id: str) -> ProductionRevisionRow | None:
        return self.revisions.get(revision_id)

    async def list_revisions(self, project_id: str | None = None) -> tuple[ProductionRevisionRow, ...]:
        if project_id is None:
            return tuple(self.revisions.values())
        return tuple(row for row in self.revisions.values() if row.project_id == project_id)

    async def update_revision(
        self,
        revision_id: str,
        *,
        status: str | None = None,
        locked: bool | None = None,
        optimistic_version: int | None = None,
        expected_version: int | None = None,
    ) -> ProductionRevisionRow | None:
        existing = self.revisions.get(revision_id)
        if existing is None:
            return None
        if expected_version is not None and existing.optimistic_version != expected_version:
            return None
        updated = ProductionRevisionRow(
            revision_id=existing.revision_id,
            project_id=existing.project_id,
            parent_revision_id=existing.parent_revision_id,
            creator=existing.creator,
            actor=existing.actor,
            created_at=existing.created_at,
            content_hash=existing.content_hash,
            status=status if status is not None else existing.status,
            locked=locked if locked is not None else existing.locked,
            invalidation_intent=existing.invalidation_intent,
            summary=existing.summary,
            optimistic_version=optimistic_version if optimistic_version is not None else existing.optimistic_version + 1,
            metadata_json=existing.metadata_json,
        )
        self.revisions[revision_id] = updated
        return updated

    # -- assets ------------------------------------------------------------
    async def insert_asset(self, row: ProductionAssetRow) -> bool:
        if row.asset_id in self.assets:
            return False
        self.assets[row.asset_id] = row
        return True

    async def get_asset(self, asset_id: str) -> ProductionAssetRow | None:
        return self.assets.get(asset_id)

    async def list_assets(self, project_id: str | None = None) -> tuple[ProductionAssetRow, ...]:
        if project_id is None:
            return tuple(self.assets.values())
        return tuple(row for row in self.assets.values() if row.project_id == project_id)

    async def update_asset(self, asset_id: str, *, values: dict[str, Any]) -> ProductionAssetRow | None:
        existing = self.assets.get(asset_id)
        if existing is None:
            return None
        # expected_version guard via values
        expected = values.get("expected_version")
        if expected is not None and existing.optimistic_version != expected:
            return None
        updated = ProductionAssetRow(
            asset_id=existing.asset_id,
            project_id=values.get("project_id", existing.project_id),
            name=values.get("name", existing.name),
            kind=values.get("kind", existing.kind),
            lifecycle_state=values.get("lifecycle_state", existing.lifecycle_state),
            processing_state=values.get("processing_state", existing.processing_state),
            active_revision_id=values.get("active_revision_id", existing.active_revision_id),
            source_type=values.get("source_type", existing.source_type),
            license_state=values.get("license_state", existing.license_state),
            tags_json=values.get("tags_json", existing.tags_json),
            created_at=existing.created_at,
            updated_at=values.get("updated_at", datetime.now(UTC)),
            optimistic_version=values.get("optimistic_version", existing.optimistic_version + 1),
            metadata_json=values.get("metadata_json", existing.metadata_json),
        )
        self.assets[asset_id] = updated
        return updated

    # -- asset revisions ---------------------------------------------------
    async def insert_asset_revision(self, row: AssetRevisionRow) -> bool:
        if row.revision_id in self.asset_revisions:
            return False
        self.asset_revisions[row.revision_id] = row
        return True

    async def get_asset_revision(self, revision_id: str) -> AssetRevisionRow | None:
        return self.asset_revisions.get(revision_id)

    async def list_asset_revisions(self, asset_id: str | None = None) -> tuple[AssetRevisionRow, ...]:
        if asset_id is None:
            return tuple(self.asset_revisions.values())
        return tuple(row for row in self.asset_revisions.values() if row.asset_id == asset_id)

    # -- audio tracks ------------------------------------------------------
    async def insert_audio_track(self, row: AudioTrackRow) -> bool:
        if row.track_id in self.audio_tracks:
            return False
        self.audio_tracks[row.track_id] = row
        return True

    async def get_audio_track(self, track_id: str) -> AudioTrackRow | None:
        return self.audio_tracks.get(track_id)

    async def list_audio_tracks(self, project_id: str | None = None) -> tuple[AudioTrackRow, ...]:
        if project_id is None:
            return tuple(self.audio_tracks.values())
        return tuple(row for row in self.audio_tracks.values() if row.project_id == project_id)

    async def update_audio_track(self, track_id: str, *, values: dict[str, Any]) -> AudioTrackRow | None:
        existing = self.audio_tracks.get(track_id)
        if existing is None:
            return None
        updated = AudioTrackRow(
            track_id=existing.track_id,
            project_id=values.get("project_id", existing.project_id),
            kind=values.get("kind", existing.kind),
            title=values.get("title", existing.title),
            character_id=values.get("character_id", existing.character_id),
            dialogue_text=values.get("dialogue_text", existing.dialogue_text),
            source_path=values.get("source_path", existing.source_path),
            source_hash=values.get("source_hash", existing.source_hash),
            sample_rate=values.get("sample_rate", existing.sample_rate),
            channels=values.get("channels", existing.channels),
            duration_seconds=values.get("duration_seconds", existing.duration_seconds),
            language=values.get("language", existing.language),
            voice_profile_id=values.get("voice_profile_id", existing.voice_profile_id),
            rights_state=values.get("rights_state", existing.rights_state),
            provenance_json=values.get("provenance_json", existing.provenance_json),
            created_at=existing.created_at,
            metadata_json=values.get("metadata_json", existing.metadata_json),
        )
        self.audio_tracks[track_id] = updated
        return updated

    # -- mix plans ---------------------------------------------------------
    async def insert_mix_plan(self, row: MixPlanRow) -> bool:
        if row.mix_plan_id in self.mix_plans:
            return False
        self.mix_plans[row.mix_plan_id] = row
        return True

    async def get_mix_plan(self, mix_plan_id: str) -> MixPlanRow | None:
        return self.mix_plans.get(mix_plan_id)

    async def list_mix_plans(self, project_id: str | None = None) -> tuple[MixPlanRow, ...]:
        if project_id is None:
            return tuple(self.mix_plans.values())
        return tuple(row for row in self.mix_plans.values() if row.project_id == project_id)

    async def update_mix_plan(self, mix_plan_id: str, *, values: dict[str, Any]) -> MixPlanRow | None:
        existing = self.mix_plans.get(mix_plan_id)
        if existing is None:
            return None
        updated = MixPlanRow(
            mix_plan_id=existing.mix_plan_id,
            project_id=values.get("project_id", existing.project_id),
            title=values.get("title", existing.title),
            loudness_target_lufs=values.get("loudness_target_lufs", existing.loudness_target_lufs),
            peak_ceiling_db=values.get("peak_ceiling_db", existing.peak_ceiling_db),
            policy_version=values.get("policy_version", existing.policy_version),
            tracks_json=values.get("tracks_json", existing.tracks_json),
            created_at=existing.created_at,
            updated_at=values.get("updated_at", datetime.now(UTC)),
            metadata_json=values.get("metadata_json", existing.metadata_json),
        )
        self.mix_plans[mix_plan_id] = updated
        return updated

    # -- code video --------------------------------------------------------
    async def insert_code_video_project(self, row: CodeVideoProjectRow) -> bool:
        if row.project_id in self.code_video_projects:
            return False
        self.code_video_projects[row.project_id] = row
        return True

    async def get_code_video_project(self, project_id: str) -> CodeVideoProjectRow | None:
        return self.code_video_projects.get(project_id)

    async def list_code_video_projects(self) -> tuple[CodeVideoProjectRow, ...]:
        return tuple(self.code_video_projects.values())

    async def update_code_video_project(self, project_id: str, *, values: dict[str, Any]) -> CodeVideoProjectRow | None:
        existing = self.code_video_projects.get(project_id)
        if existing is None:
            return None
        expected = values.get("expected_version")
        if expected is not None and existing.optimistic_version != expected:
            return None
        updated = CodeVideoProjectRow(
            project_id=existing.project_id,
            title=values.get("title", existing.title),
            description=values.get("description", existing.description),
            status=values.get("status", existing.status),
            repo_url=values.get("repo_url", existing.repo_url),
            branch=values.get("branch", existing.branch),
            tutorial_steps_json=values.get("tutorial_steps_json", existing.tutorial_steps_json),
            current_checkpoint=values.get("current_checkpoint", existing.current_checkpoint),
            created_at=existing.created_at,
            updated_at=values.get("updated_at", datetime.now(UTC)),
            optimistic_version=values.get("optimistic_version", existing.optimistic_version + 1),
            metadata_json=values.get("metadata_json", existing.metadata_json),
        )
        self.code_video_projects[project_id] = updated
        return updated

    # -- render jobs -------------------------------------------------------
    async def insert_render_job(self, row: RenderJobRow) -> bool:
        if row.job_id in self.render_jobs:
            return False
        self.render_jobs[row.job_id] = row
        return True

    async def get_render_job(self, job_id: str) -> RenderJobRow | None:
        return self.render_jobs.get(job_id)

    async def list_render_jobs(self, project_id: str | None = None) -> tuple[RenderJobRow, ...]:
        if project_id is None:
            return tuple(self.render_jobs.values())
        return tuple(row for row in self.render_jobs.values() if row.project_id == project_id)

    async def update_render_job(self, job_id: str, *, values: dict[str, Any]) -> RenderJobRow | None:
        existing = self.render_jobs.get(job_id)
        if existing is None:
            return None
        expected = values.get("expected_version")
        if expected is not None and existing.optimistic_version != expected:
            return None
        updated = RenderJobRow(
            job_id=existing.job_id,
            project_id=values.get("project_id", existing.project_id),
            revision_id=values.get("revision_id", existing.revision_id),
            scene_id=values.get("scene_id", existing.scene_id),
            shot_id=values.get("shot_id", existing.shot_id),
            status=values.get("status", existing.status),
            frame_start=values.get("frame_start", existing.frame_start),
            frame_end=values.get("frame_end", existing.frame_end),
            colorspace=values.get("colorspace", existing.colorspace),
            profile_id=values.get("profile_id", existing.profile_id),
            attempt=values.get("attempt", existing.attempt),
            input_hash=values.get("input_hash", existing.input_hash),
            output_hash=values.get("output_hash", existing.output_hash),
            error=values.get("error", existing.error),
            created_at=existing.created_at,
            updated_at=values.get("updated_at", datetime.now(UTC)),
            optimistic_version=values.get("optimistic_version", existing.optimistic_version + 1),
            metadata_json=values.get("metadata_json", existing.metadata_json),
        )
        self.render_jobs[job_id] = updated
        return updated

    # -- edls --------------------------------------------------------------
    async def insert_edl(self, row: EdlRow) -> bool:
        if row.edl_id in self.edls:
            return False
        self.edls[row.edl_id] = row
        return True

    async def get_edl(self, edl_id: str) -> EdlRow | None:
        return self.edls.get(edl_id)

    async def list_edls(self, project_id: str | None = None) -> tuple[EdlRow, ...]:
        if project_id is None:
            return tuple(self.edls.values())
        return tuple(row for row in self.edls.values() if row.project_id == project_id)

    async def update_edl(self, edl_id: str, *, values: dict[str, Any]) -> EdlRow | None:
        existing = self.edls.get(edl_id)
        if existing is None:
            return None
        updated = EdlRow(
            edl_id=existing.edl_id,
            project_id=values.get("project_id", existing.project_id),
            revision_id=values.get("revision_id", existing.revision_id),
            title=values.get("title", existing.title),
            status=values.get("status", existing.status),
            items_json=values.get("items_json", existing.items_json),
            audio_mix_plan_id=values.get("audio_mix_plan_id", existing.audio_mix_plan_id),
            subtitle_track_id=values.get("subtitle_track_id", existing.subtitle_track_id),
            encoding_profile_json=values.get("encoding_profile_json", existing.encoding_profile_json),
            edl_hash=values.get("edl_hash", existing.edl_hash),
            created_at=existing.created_at,
            updated_at=values.get("updated_at", datetime.now(UTC)),
            metadata_json=values.get("metadata_json", existing.metadata_json),
        )
        self.edls[edl_id] = updated
        return updated


class InMemoryTransactionScope:
    def __init__(self, store: InMemoryProductionStore) -> None:
        self._store = store
        self._pending: list[tuple[EventEnvelope, str | None]] = []

    async def __aenter__(self) -> InMemoryTransactionScope:
        self._pending.clear()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: object | None) -> bool:
        if exc_type is not None:
            self._pending.clear()
        return False

    def store(self) -> InMemoryProductionStore:
        return self._store

    async def record_event(self, envelope: EventEnvelope, *, deduplication_key: str | None = None) -> bool:
        self._pending.append((envelope, deduplication_key))
        return True

    async def commit(self) -> None:
        for envelope, _ in self._pending:
            self._store.events.append(envelope)
        self._pending.clear()


def memory_scope_factory(store: InMemoryProductionStore) -> Callable[[], InMemoryTransactionScope]:
    return lambda: InMemoryTransactionScope(store)
