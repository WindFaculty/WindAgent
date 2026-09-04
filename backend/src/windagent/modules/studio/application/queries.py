"""Immutable Studio queries (side-effect-free)."""

from __future__ import annotations

from dataclasses import dataclass

from windagent.platform.queries import Query

from .models import (
    ArtifactView,
    CharacterView,
    EpisodeView,
    ProjectView,
    RevisionView,
    SeriesView,
    StoryboardView,
)


@dataclass(frozen=True, slots=True)
class GetProject(Query[ProjectView]):
    project_id: str


@dataclass(frozen=True, slots=True)
class ListProjects(Query[tuple[ProjectView, ...]]):
    pass


@dataclass(frozen=True, slots=True)
class GetSeries(Query[SeriesView]):
    series_id: str


@dataclass(frozen=True, slots=True)
class ListSeries(Query[tuple[SeriesView, ...]]):
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetEpisode(Query[EpisodeView]):
    episode_id: str


@dataclass(frozen=True, slots=True)
class ListEpisodes(Query[tuple[EpisodeView, ...]]):
    series_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetRevision(Query[RevisionView]):
    revision_id: str


@dataclass(frozen=True, slots=True)
class ListRevisions(Query[tuple[RevisionView, ...]]):
    episode_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetArtifact(Query[ArtifactView]):
    artifact_id: str


@dataclass(frozen=True, slots=True)
class ListArtifacts(Query[tuple[ArtifactView, ...]]):
    episode_id: str | None = None
    artifact_type: str | None = None


@dataclass(frozen=True, slots=True)
class ListCharacters(Query[tuple[CharacterView, ...]]):
    series_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetCharacter(Query[CharacterView]):
    character_id: str


@dataclass(frozen=True, slots=True)
class ListWorldLocations(Query[tuple[dict[str, object], ...]]):
    series_id: str


@dataclass(frozen=True, slots=True)
class ListWorldProps(Query[tuple[dict[str, object], ...]]):
    series_id: str


@dataclass(frozen=True, slots=True)
class GetStoryboard(Query[StoryboardView]):
    storyboard_id: str


@dataclass(frozen=True, slots=True)
class ListStoryboards(Query[tuple[StoryboardView, ...]]):
    episode_id: str | None = None
