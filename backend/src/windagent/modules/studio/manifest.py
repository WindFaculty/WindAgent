"""Module manifest for Studio (Phase 15).

Discovered automatically by ``PackageModuleDiscovery`` — no bootstrap file
needs to import this module by name except for testing.
"""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_studio_router
from .application.commands import (
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
from .application.handlers import (
    CreateArtifactHandler,
    CreateCharacterHandler,
    CreateEpisodeHandler,
    CreateProjectHandler,
    CreateRevisionHandler,
    CreateSeriesHandler,
    CreateStoryboardHandler,
    DeriveRevisionHandler,
    GetArtifactHandler,
    GetCharacterHandler,
    GetEpisodeHandler,
    GetProjectHandler,
    GetRevisionHandler,
    GetSeriesHandler,
    GetStoryboardHandler,
    ListArtifactsHandler,
    ListCharactersHandler,
    ListEpisodesHandler,
    ListProjectsHandler,
    ListRevisionsHandler,
    ListSeriesHandler,
    ListStoryboardsHandler,
    ListWorldLocationsHandler,
    ListWorldPropsHandler,
    LockRevisionHandler,
    ReorderStoryboardHandler,
    StoryGenerateJobHandler,
    TransitionEpisodeHandler,
    UpdateCharacterHandler,
    UpdateEpisodeHandler,
    UpdateProjectHandler,
    UpdateSeriesHandler,
    UpdateStoryboardHandler,
    UpsertWorldLocationHandler,
    UpsertWorldPropHandler,
)
from .application.queries import (
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
from .application.runtime import StudioServices

STUDIO_JOB_TYPES = ("studio.story.generate",)


def build_studio_manifest(services: StudioServices | None = None) -> ModuleManifest:
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(CreateProject, CreateProjectHandler(services)),
            CommandRegistration(UpdateProject, UpdateProjectHandler(services)),
            CommandRegistration(CreateSeries, CreateSeriesHandler(services)),
            CommandRegistration(UpdateSeries, UpdateSeriesHandler(services)),
            CommandRegistration(CreateEpisode, CreateEpisodeHandler(services)),
            CommandRegistration(UpdateEpisode, UpdateEpisodeHandler(services)),
            CommandRegistration(TransitionEpisode, TransitionEpisodeHandler(services)),
            CommandRegistration(CreateRevision, CreateRevisionHandler(services)),
            CommandRegistration(DeriveRevision, DeriveRevisionHandler(services)),
            CommandRegistration(LockRevision, LockRevisionHandler(services)),
            CommandRegistration(CreateArtifact, CreateArtifactHandler(services)),
            CommandRegistration(CreateCharacter, CreateCharacterHandler(services)),
            CommandRegistration(UpdateCharacter, UpdateCharacterHandler(services)),
            CommandRegistration(UpsertWorldLocation, UpsertWorldLocationHandler(services)),
            CommandRegistration(UpsertWorldProp, UpsertWorldPropHandler(services)),
            CommandRegistration(CreateStoryboard, CreateStoryboardHandler(services)),
            CommandRegistration(UpdateStoryboard, UpdateStoryboardHandler(services)),
            CommandRegistration(ReorderStoryboard, ReorderStoryboardHandler(services)),
        ),
        queries=(
            QueryRegistration(GetProject, GetProjectHandler(services)),
            QueryRegistration(ListProjects, ListProjectsHandler(services)),
            QueryRegistration(GetSeries, GetSeriesHandler(services)),
            QueryRegistration(ListSeries, ListSeriesHandler(services)),
            QueryRegistration(GetEpisode, GetEpisodeHandler(services)),
            QueryRegistration(ListEpisodes, ListEpisodesHandler(services)),
            QueryRegistration(GetRevision, GetRevisionHandler(services)),
            QueryRegistration(ListRevisions, ListRevisionsHandler(services)),
            QueryRegistration(GetArtifact, GetArtifactHandler(services)),
            QueryRegistration(ListArtifacts, ListArtifactsHandler(services)),
            QueryRegistration(GetCharacter, GetCharacterHandler(services)),
            QueryRegistration(ListCharacters, ListCharactersHandler(services)),
            QueryRegistration(ListWorldLocations, ListWorldLocationsHandler(services)),
            QueryRegistration(ListWorldProps, ListWorldPropsHandler(services)),
            QueryRegistration(GetStoryboard, GetStoryboardHandler(services)),
            QueryRegistration(ListStoryboards, ListStoryboardsHandler(services)),
        ),
        jobs=(JobRegistration("studio.story.generate", StoryGenerateJobHandler(services)),),
        routers=(create_studio_router(),),
        capabilities=("studio", "story", "projects", "series", "episodes", "characters", "world", "storyboard"),
    )


manifest = build_studio_manifest()
