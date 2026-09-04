"""Application handlers connecting commands/queries/jobs to services."""

from __future__ import annotations

from typing import Any

from .commands import (
    CreateArtifact,
    CreateCharacter,
    CreateEpisode,
    CreateProject,
    CreateRevision,
    CreateSeries,
    CreateStoryboard,
    DeriveRevision,
    LockRevision,
    ReorderStoryboard,
    TransitionEpisode,
    UpdateCharacter,
    UpdateEpisode,
    UpdateProject,
    UpdateSeries,
    UpdateStoryboard,
    UpsertWorldLocation,
    UpsertWorldProp,
)
from .queries import (
    GetArtifact,
    GetCharacter,
    GetEpisode,
    GetProject,
    GetRevision,
    GetSeries,
    GetStoryboard,
    ListArtifacts,
    ListCharacters,
    ListEpisodes,
    ListProjects,
    ListRevisions,
    ListSeries,
    ListStoryboards,
    ListWorldLocations,
    ListWorldProps,
)
from .runtime import StudioServices, container_for


class _Handler:
    def __init__(self, services: StudioServices | None = None) -> None:
        self._services = services


# -- projects --------------------------------------------------------------


class CreateProjectHandler(_Handler):
    async def handle(self, command: CreateProject) -> Any:
        return await container_for(self._services).studio.create_project(
            title=command.title, description=command.description, owner_id=command.owner_id, metadata=command.metadata
        )


class UpdateProjectHandler(_Handler):
    async def handle(self, command: UpdateProject) -> Any:
        return await container_for(self._services).studio.update_project(
            project_id=command.project_id,
            title=command.title,
            description=command.description,
            expected_version=command.expected_version,
            metadata_patch=command.metadata_patch,
        )


class GetProjectHandler(_Handler):
    async def handle(self, query: GetProject) -> Any:
        return await container_for(self._services).studio.get_project(query.project_id)


class ListProjectsHandler(_Handler):
    async def handle(self, query: ListProjects) -> Any:
        return await container_for(self._services).studio.list_projects()


# -- series ----------------------------------------------------------------


class CreateSeriesHandler(_Handler):
    async def handle(self, command: CreateSeries) -> Any:
        return await container_for(self._services).studio.create_series(
            title=command.title, description=command.description, project_id=command.project_id, metadata=command.metadata
        )


class UpdateSeriesHandler(_Handler):
    async def handle(self, command: UpdateSeries) -> Any:
        return await container_for(self._services).studio.update_series(
            series_id=command.series_id,
            title=command.title,
            description=command.description,
            expected_version=command.expected_version,
            metadata_patch=command.metadata_patch,
        )


class GetSeriesHandler(_Handler):
    async def handle(self, query: GetSeries) -> Any:
        return await container_for(self._services).studio.get_series(query.series_id)


class ListSeriesHandler(_Handler):
    async def handle(self, query: ListSeries) -> Any:
        return await container_for(self._services).studio.list_series(query.project_id)


# -- episodes --------------------------------------------------------------


class CreateEpisodeHandler(_Handler):
    async def handle(self, command: CreateEpisode) -> Any:
        return await container_for(self._services).studio.create_episode(
            series_id=command.series_id,
            title=command.title,
            episode_number=command.episode_number,
            logline=command.logline,
            project_id=command.project_id,
            metadata=command.metadata,
        )


class UpdateEpisodeHandler(_Handler):
    async def handle(self, command: UpdateEpisode) -> Any:
        return await container_for(self._services).studio.update_episode(
            episode_id=command.episode_id,
            title=command.title,
            logline=command.logline,
            expected_version=command.expected_version,
            metadata_patch=command.metadata_patch,
        )


class TransitionEpisodeHandler(_Handler):
    async def handle(self, command: TransitionEpisode) -> Any:
        return await container_for(self._services).studio.transition_episode(
            episode_id=command.episode_id, target_state=command.target_state, expected_version=command.expected_version
        )


class GetEpisodeHandler(_Handler):
    async def handle(self, query: GetEpisode) -> Any:
        return await container_for(self._services).studio.get_episode(query.episode_id)


class ListEpisodesHandler(_Handler):
    async def handle(self, query: ListEpisodes) -> Any:
        return await container_for(self._services).studio.list_episodes(query.series_id)


# -- revisions -------------------------------------------------------------


class CreateRevisionHandler(_Handler):
    async def handle(self, command: CreateRevision) -> Any:
        return await container_for(self._services).studio.create_revision(
            series_id=command.series_id,
            episode_id=command.episode_id,
            content_hash=command.content_hash,
            creator=command.creator,
            actor=command.actor,
            parent_revision_id=command.parent_revision_id,
            summary=command.summary,
            metadata=command.metadata,
        )


class DeriveRevisionHandler(_Handler):
    async def handle(self, command: DeriveRevision) -> Any:
        return await container_for(self._services).studio.derive_revision(
            episode_id=command.episode_id,
            series_id=command.series_id,
            parent_revision_id=command.parent_revision_id,
            new_content_hash=command.new_content_hash,
            actor=command.actor,
            invalidation_intent=command.invalidation_intent,
            summary=command.summary,
            expected_version=command.expected_version,
        )


class LockRevisionHandler(_Handler):
    async def handle(self, command: LockRevision) -> Any:
        return await container_for(self._services).studio.lock_revision(
            revision_id=command.revision_id,
            expected_content_hash=command.expected_content_hash,
            expected_version=command.expected_version,
        )


class GetRevisionHandler(_Handler):
    async def handle(self, query: GetRevision) -> Any:
        return await container_for(self._services).studio.get_revision(query.revision_id)


class ListRevisionsHandler(_Handler):
    async def handle(self, query: ListRevisions) -> Any:
        return await container_for(self._services).studio.list_revisions(query.episode_id)


# -- artifacts -------------------------------------------------------------


class CreateArtifactHandler(_Handler):
    async def handle(self, command: CreateArtifact) -> Any:
        return await container_for(self._services).studio.create_artifact(
            artifact_type=command.artifact_type,
            series_id=command.series_id,
            episode_id=command.episode_id,
            content=command.content,
            revision_id=command.revision_id,
            input_artifact_refs=command.input_artifact_refs,
            created_by=command.created_by,
            extra=command.extra,
        )


class GetArtifactHandler(_Handler):
    async def handle(self, query: GetArtifact) -> Any:
        return await container_for(self._services).studio.get_artifact(query.artifact_id)


class ListArtifactsHandler(_Handler):
    async def handle(self, query: ListArtifacts) -> Any:
        return await container_for(self._services).studio.list_artifacts(query.episode_id, query.artifact_type)


# -- characters ------------------------------------------------------------


class CreateCharacterHandler(_Handler):
    async def handle(self, command: CreateCharacter) -> Any:
        return await container_for(self._services).studio.create_character(
            series_id=command.series_id,
            name=command.name,
            display_name=command.display_name,
            role=command.role,
            archetype=command.archetype,
            description=command.description,
            traits=command.traits,
            backstory=command.backstory,
            metadata=command.metadata,
        )


class UpdateCharacterHandler(_Handler):
    async def handle(self, command: UpdateCharacter) -> Any:
        return await container_for(self._services).studio.update_character(
            character_id=command.character_id,
            display_name=command.display_name,
            description=command.description,
            traits=command.traits,
            expected_version=command.expected_version,
            metadata_patch=command.metadata_patch,
        )


class GetCharacterHandler(_Handler):
    async def handle(self, query: GetCharacter) -> Any:
        return await container_for(self._services).studio.get_character(query.character_id)


class ListCharactersHandler(_Handler):
    async def handle(self, query: ListCharacters) -> Any:
        return await container_for(self._services).studio.list_characters(query.series_id)


# -- world -----------------------------------------------------------------


class UpsertWorldLocationHandler(_Handler):
    async def handle(self, command: UpsertWorldLocation) -> Any:
        return await container_for(self._services).studio.upsert_location(
            series_id=command.series_id,
            location_id=command.location_id,
            name=command.name,
            description=command.description,
            geography=command.geography,
            metadata=command.metadata,
        )


class UpsertWorldPropHandler(_Handler):
    async def handle(self, command: UpsertWorldProp) -> Any:
        return await container_for(self._services).studio.upsert_prop(
            series_id=command.series_id,
            prop_id=command.prop_id,
            name=command.name,
            description=command.description,
            significance=command.significance,
            metadata=command.metadata,
        )


class ListWorldLocationsHandler(_Handler):
    async def handle(self, query: ListWorldLocations) -> Any:
        return await container_for(self._services).studio.list_locations(query.series_id)


class ListWorldPropsHandler(_Handler):
    async def handle(self, query: ListWorldProps) -> Any:
        return await container_for(self._services).studio.list_props(query.series_id)


# -- storyboard ------------------------------------------------------------


class CreateStoryboardHandler(_Handler):
    async def handle(self, command: CreateStoryboard) -> Any:
        return await container_for(self._services).studio.create_storyboard(
            episode_id=command.episode_id,
            series_id=command.series_id,
            title=command.title,
            panels=command.panels,
            metadata=command.metadata,
        )


class UpdateStoryboardHandler(_Handler):
    async def handle(self, command: UpdateStoryboard) -> Any:
        return await container_for(self._services).studio.update_storyboard(
            storyboard_id=command.storyboard_id,
            panels=command.panels,
            expected_version=command.expected_version,
            metadata_patch=command.metadata_patch,
        )


class ReorderStoryboardHandler(_Handler):
    async def handle(self, command: ReorderStoryboard) -> Any:
        return await container_for(self._services).studio.reorder_storyboard(
            storyboard_id=command.storyboard_id, panel_ids=command.panel_ids, expected_version=command.expected_version
        )


class GetStoryboardHandler(_Handler):
    async def handle(self, query: GetStoryboard) -> Any:
        return await container_for(self._services).studio.get_storyboard(query.storyboard_id)


class ListStoryboardsHandler(_Handler):
    async def handle(self, query: ListStoryboards) -> Any:
        return await container_for(self._services).studio.list_storyboards(query.episode_id)


# -- job adapter -----------------------------------------------------------


class StoryGenerateJobHandler(_Handler):
    """Worker job handler stub for future AI story generation.

    Payload shape: ``{episode_id, series_id, artifact_type, prompt}``.
    The handler deterministically produces a placeholder artifact so the
    pipeline is end-to-end testable without a provider.  Future wiring will
    delegate to ``intelligence/story`` adapters through the automation runtime.
    """

    job_type = "studio.story.generate"

    async def handle(self, payload: dict[str, object]) -> dict[str, object]:
        from windagent.kernel.time import utc_now as _utc

        artifact_type = str(payload.get("artifact_type", "CreativeBrief"))
        episode_id = str(payload.get("episode_id", ""))
        series_id = str(payload.get("series_id", ""))
        content = payload.get("prompt") or payload.get("content") or {"note": "placeholder generation"}
        # Create artifact via service (reuses current services scope)
        view = await container_for(self._services).studio.create_artifact(
            artifact_type=artifact_type,
            series_id=series_id,
            episode_id=episode_id,
            content=content,
            created_by="studio-job",
        )
        return {"artifact_id": view.artifact_id, "status": "SUCCEEDED", "created_at": _utc().isoformat()}
