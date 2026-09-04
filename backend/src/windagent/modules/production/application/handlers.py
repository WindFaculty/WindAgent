"""Application handlers connecting commands/queries/jobs to services."""

from __future__ import annotations

from typing import Any

from .commands import (
    CreateAssetRevision,
    CreateAudioTrack,
    CreateCodeVideoProject,
    CreateEdl,
    CreateMixPlan,
    CreateProductionAsset,
    CreateProductionProject,
    CreateProductionRevision,
    CreateRenderJob,
    DeriveProductionRevision,
    LockProductionRevision,
    TransitionCodeVideoProject,
    TransitionProductionAsset,
    TransitionRenderJob,
    UpdateEdl,
    UpdateProductionProject,
)
from .queries import (
    GetAssetRevision,
    GetAudioTrack,
    GetCodeVideoProject,
    GetEdl,
    GetMixPlan,
    GetProductionAsset,
    GetProductionProject,
    GetProductionRevision,
    GetRenderJob,
    ListAssetRevisions,
    ListAudioTracks,
    ListCodeVideoProjects,
    ListEdls,
    ListMixPlans,
    ListProductionAssets,
    ListProductionProjects,
    ListProductionRevisions,
    ListRenderJobs,
)
from .runtime import ProductionServices, container_for


class _Handler:
    def __init__(self, services: ProductionServices | None = None) -> None:
        self._services = services


# -- projects --------------------------------------------------------------


class CreateProductionProjectHandler(_Handler):
    async def handle(self, command: CreateProductionProject) -> Any:
        return await container_for(self._services).production.create_project(
            title=command.title, description=command.description, owner_id=command.owner_id, metadata=command.metadata
        )


class UpdateProductionProjectHandler(_Handler):
    async def handle(self, command: UpdateProductionProject) -> Any:
        return await container_for(self._services).production.update_project(
            project_id=command.project_id,
            title=command.title,
            description=command.description,
            status=command.status,
            expected_version=command.expected_version,
            metadata_patch=command.metadata_patch,
        )


class GetProductionProjectHandler(_Handler):
    async def handle(self, query: GetProductionProject) -> Any:
        return await container_for(self._services).production.get_project(query.project_id)


class ListProductionProjectsHandler(_Handler):
    async def handle(self, query: ListProductionProjects) -> Any:
        return await container_for(self._services).production.list_projects()


# -- revisions -------------------------------------------------------------


class CreateProductionRevisionHandler(_Handler):
    async def handle(self, command: CreateProductionRevision) -> Any:
        return await container_for(self._services).production.create_revision(
            project_id=command.project_id,
            content_hash=command.content_hash,
            creator=command.creator,
            actor=command.actor,
            parent_revision_id=command.parent_revision_id,
            summary=command.summary,
            metadata=command.metadata,
        )


class DeriveProductionRevisionHandler(_Handler):
    async def handle(self, command: DeriveProductionRevision) -> Any:
        return await container_for(self._services).production.derive_revision(
            project_id=command.project_id,
            parent_revision_id=command.parent_revision_id,
            new_content_hash=command.new_content_hash,
            actor=command.actor,
            invalidation_intent=command.invalidation_intent,
            summary=command.summary,
            expected_version=command.expected_version,
        )


class LockProductionRevisionHandler(_Handler):
    async def handle(self, command: LockProductionRevision) -> Any:
        return await container_for(self._services).production.lock_revision(
            revision_id=command.revision_id, expected_content_hash=command.expected_content_hash, expected_version=command.expected_version
        )


class GetProductionRevisionHandler(_Handler):
    async def handle(self, query: GetProductionRevision) -> Any:
        return await container_for(self._services).production.get_revision(query.revision_id)


class ListProductionRevisionsHandler(_Handler):
    async def handle(self, query: ListProductionRevisions) -> Any:
        return await container_for(self._services).production.list_revisions(query.project_id)


# -- assets ----------------------------------------------------------------


class CreateProductionAssetHandler(_Handler):
    async def handle(self, command: CreateProductionAsset) -> Any:
        return await container_for(self._services).production.create_asset(
            name=command.name,
            kind=command.kind,
            project_id=command.project_id,
            description=command.description,
            source_type=command.source_type,
            license_state=command.license_state,
            tags=command.tags,
            metadata=command.metadata,
        )


class TransitionProductionAssetHandler(_Handler):
    async def handle(self, command: TransitionProductionAsset) -> Any:
        return await container_for(self._services).production.transition_asset(
            asset_id=command.asset_id, target_state=command.target_state, expected_version=command.expected_version, new_review_record=command.new_review_record
        )


class GetProductionAssetHandler(_Handler):
    async def handle(self, query: GetProductionAsset) -> Any:
        return await container_for(self._services).production.get_asset(query.asset_id)


class ListProductionAssetsHandler(_Handler):
    async def handle(self, query: ListProductionAssets) -> Any:
        return await container_for(self._services).production.list_assets(query.project_id)


class CreateAssetRevisionHandler(_Handler):
    async def handle(self, command: CreateAssetRevision) -> Any:
        return await container_for(self._services).production.create_asset_revision(
            asset_id=command.asset_id,
            content_hash=command.content_hash,
            media_type=command.media_type,
            mime_type=command.mime_type,
            size_bytes=command.size_bytes,
            supersedes_revision_id=command.supersedes_revision_id,
            normalized_format=command.normalized_format,
            preview_artifacts=command.preview_artifacts,
            validation_report=command.validation_report,
            provenance=command.provenance,
        )


class GetAssetRevisionHandler(_Handler):
    async def handle(self, query: GetAssetRevision) -> Any:
        return await container_for(self._services).production.get_asset_revision(query.revision_id)


class ListAssetRevisionsHandler(_Handler):
    async def handle(self, query: ListAssetRevisions) -> Any:
        return await container_for(self._services).production.list_asset_revisions(query.asset_id)


# -- audio -----------------------------------------------------------------


class CreateAudioTrackHandler(_Handler):
    async def handle(self, command: CreateAudioTrack) -> Any:
        return await container_for(self._services).production.create_audio_track(
            project_id=command.project_id,
            title=command.title,
            kind=command.kind,
            character_id=command.character_id,
            dialogue_text=command.dialogue_text,
            source_path=command.source_path,
            source_hash=command.source_hash,
            sample_rate=command.sample_rate,
            channels=command.channels,
            duration_seconds=command.duration_seconds,
            language=command.language,
            voice_profile_id=command.voice_profile_id,
            provenance=command.provenance,
            metadata=command.metadata,
        )


class GetAudioTrackHandler(_Handler):
    async def handle(self, query: GetAudioTrack) -> Any:
        return await container_for(self._services).production.get_audio_track(query.track_id)


class ListAudioTracksHandler(_Handler):
    async def handle(self, query: ListAudioTracks) -> Any:
        return await container_for(self._services).production.list_audio_tracks(query.project_id)


class CreateMixPlanHandler(_Handler):
    async def handle(self, command: CreateMixPlan) -> Any:
        return await container_for(self._services).production.create_mix_plan(
            project_id=command.project_id,
            title=command.title,
            loudness_target_lufs=command.loudness_target_lufs,
            peak_ceiling_db=command.peak_ceiling_db,
            policy_version=command.policy_version,
            tracks=command.tracks,
            metadata=command.metadata,
        )


class GetMixPlanHandler(_Handler):
    async def handle(self, query: GetMixPlan) -> Any:
        return await container_for(self._services).production.get_mix_plan(query.mix_plan_id)


class ListMixPlansHandler(_Handler):
    async def handle(self, query: ListMixPlans) -> Any:
        return await container_for(self._services).production.list_mix_plans(query.project_id)


# -- code video ------------------------------------------------------------


class CreateCodeVideoProjectHandler(_Handler):
    async def handle(self, command: CreateCodeVideoProject) -> Any:
        return await container_for(self._services).production.create_code_video_project(
            title=command.title, description=command.description, repo_url=command.repo_url, branch=command.branch, metadata=command.metadata
        )


class TransitionCodeVideoProjectHandler(_Handler):
    async def handle(self, command: TransitionCodeVideoProject) -> Any:
        return await container_for(self._services).production.transition_code_video_project(
            project_id=command.project_id, target_status=command.target_status, expected_version=command.expected_version
        )


class GetCodeVideoProjectHandler(_Handler):
    async def handle(self, query: GetCodeVideoProject) -> Any:
        return await container_for(self._services).production.get_code_video_project(query.project_id)


class ListCodeVideoProjectsHandler(_Handler):
    async def handle(self, query: ListCodeVideoProjects) -> Any:
        return await container_for(self._services).production.list_code_video_projects()


# -- rendering -------------------------------------------------------------


class CreateRenderJobHandler(_Handler):
    async def handle(self, command: CreateRenderJob) -> Any:
        return await container_for(self._services).production.create_render_job(
            project_id=command.project_id,
            scene_id=command.scene_id,
            shot_id=command.shot_id,
            revision_id=command.revision_id,
            frame_start=command.frame_start,
            frame_end=command.frame_end,
            colorspace=command.colorspace,
            profile_id=command.profile_id,
            input_hash=command.input_hash,
            metadata=command.metadata,
        )


class TransitionRenderJobHandler(_Handler):
    async def handle(self, command: TransitionRenderJob) -> Any:
        return await container_for(self._services).production.transition_render_job(
            job_id=command.job_id, target_status=command.target_status, expected_version=command.expected_version, output_hash=command.output_hash, error=command.error
        )


class GetRenderJobHandler(_Handler):
    async def handle(self, query: GetRenderJob) -> Any:
        return await container_for(self._services).production.get_render_job(query.job_id)


class ListRenderJobsHandler(_Handler):
    async def handle(self, query: ListRenderJobs) -> Any:
        return await container_for(self._services).production.list_render_jobs(query.project_id)


# -- edl -------------------------------------------------------------------


class CreateEdlHandler(_Handler):
    async def handle(self, command: CreateEdl) -> Any:
        return await container_for(self._services).production.create_edl(
            project_id=command.project_id,
            revision_id=command.revision_id,
            title=command.title,
            items=command.items,
            audio_mix_plan_id=command.audio_mix_plan_id,
            subtitle_track_id=command.subtitle_track_id,
            encoding_profile=command.encoding_profile,
            metadata=command.metadata,
        )


class UpdateEdlHandler(_Handler):
    async def handle(self, command: UpdateEdl) -> Any:
        return await container_for(self._services).production.update_edl(
            edl_id=command.edl_id, title=command.title, status=command.status, expected_version=command.expected_version, metadata_patch=command.metadata_patch
        )


class GetEdlHandler(_Handler):
    async def handle(self, query: GetEdl) -> Any:
        return await container_for(self._services).production.get_edl(query.edl_id)


class ListEdlsHandler(_Handler):
    async def handle(self, query: ListEdls) -> Any:
        return await container_for(self._services).production.list_edls(query.project_id)


# -- jobs (production.jobs.*) ----------------------------------------------


class ProductionRenderJobHandler(_Handler):
    """Idempotent handler for ``production.render.execute``."""

    async def handle(self, payload: dict[str, object]) -> dict[str, object]:
        job_id = str(payload.get("job_id", "")) if isinstance(payload, dict) else ""
        edl_data = payload.get("edl_data") if isinstance(payload, dict) else None
        output_path = payload.get("output_path") if isinstance(payload, dict) else None

        if isinstance(edl_data, dict) and output_path:
            from pathlib import Path
            from ..render import RenderJobState, RenderService

            resolver = {}
            if "asset_resolver" in payload and isinstance(payload["asset_resolver"], dict):
                resolver = {k: Path(str(v)) for k, v in payload["asset_resolver"].items()}

            service = RenderService()
            state, validation, err = await service.execute_render_job(
                job_id=job_id,
                edl_data=edl_data,
                output_path=Path(str(output_path)),
                asset_resolver=resolver,
            )

            if state != RenderJobState.READY:
                raise RuntimeError(f"Production render failed for job '{job_id}': {err}")

            return {
                "job_id": job_id,
                "status": state.value,
                "output_file": str(output_path),
                "validation": validation.to_dict() if validation else None,
            }

        return {"job_id": job_id, "status": "COMPLETED"}


class ProductionPostprocessJobHandler(_Handler):
    async def handle(self, payload: dict[str, object]) -> dict[str, object]:
        job_id = str(payload.get("job_id", "")) if isinstance(payload, dict) else ""
        return {"job_id": job_id, "status": "COMPLETED"}


class ProductionAssetNormalizeJobHandler(_Handler):
    async def handle(self, payload: dict[str, object]) -> dict[str, object]:
        job_id = str(payload.get("job_id", "")) if isinstance(payload, dict) else ""
        return {"job_id": job_id, "status": "COMPLETED"}
