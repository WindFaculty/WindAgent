"""Immutable Studio commands (intentions with payloads)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from windagent.platform.commands import Command

from .models import (
    ArtifactView,
    CharacterView,
    EpisodeView,
    ProjectView,
    RevisionView,
    SeriesView,
    StoryboardView,
)

# -- projects --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateProject(Command[ProjectView]):
    title: str
    description: str = ""
    owner_id: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateProject(Command[ProjectView]):
    project_id: str
    title: str | None = None
    description: str | None = None
    expected_version: int | None = None
    metadata_patch: dict[str, Any] = field(default_factory=dict)


# -- series ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateSeries(Command[SeriesView]):
    title: str
    description: str = ""
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateSeries(Command[SeriesView]):
    series_id: str
    title: str | None = None
    description: str | None = None
    expected_version: int | None = None
    metadata_patch: dict[str, Any] = field(default_factory=dict)


# -- episodes --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateEpisode(Command[EpisodeView]):
    series_id: str
    title: str
    episode_number: int = 1
    logline: str = ""
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateEpisode(Command[EpisodeView]):
    episode_id: str
    title: str | None = None
    logline: str | None = None
    expected_version: int | None = None
    metadata_patch: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionEpisode(Command[EpisodeView]):
    episode_id: str
    target_state: str
    expected_version: int | None = None


# -- revisions -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateRevision(Command[RevisionView]):
    series_id: str
    episode_id: str
    content_hash: str
    creator: str = "system"
    actor: str | None = None
    parent_revision_id: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeriveRevision(Command[RevisionView]):
    episode_id: str
    series_id: str
    parent_revision_id: str
    new_content_hash: str
    actor: str = "system"
    invalidation_intent: str | None = None
    summary: str = ""
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class LockRevision(Command[RevisionView]):
    revision_id: str
    expected_content_hash: str | None = None
    expected_version: int | None = None


# -- artifacts -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateArtifact(Command[ArtifactView]):
    artifact_type: str
    series_id: str
    episode_id: str
    content: Any
    revision_id: str | None = None
    input_artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    created_by: str = "system"
    extra: dict[str, Any] = field(default_factory=dict)


# -- characters ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateCharacter(Command[CharacterView]):
    series_id: str
    name: str
    display_name: str = ""
    role: str = "supporting"
    archetype: str = ""
    description: str = ""
    traits: tuple[str, ...] = field(default_factory=tuple)
    backstory: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateCharacter(Command[CharacterView]):
    character_id: str
    display_name: str | None = None
    description: str | None = None
    traits: tuple[str, ...] | None = None
    expected_version: int | None = None
    metadata_patch: dict[str, Any] = field(default_factory=dict)


# -- world -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UpsertWorldLocation(Command[dict[str, Any]]):
    series_id: str
    location_id: str
    name: str
    description: str = ""
    geography: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpsertWorldProp(Command[dict[str, Any]]):
    series_id: str
    prop_id: str
    name: str
    description: str = ""
    significance: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# -- storyboard ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateStoryboard(Command[StoryboardView]):
    episode_id: str
    series_id: str
    title: str
    panels: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateStoryboard(Command[StoryboardView]):
    storyboard_id: str
    panels: tuple[dict[str, Any], ...] | None = None
    expected_version: int | None = None
    metadata_patch: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReorderStoryboard(Command[StoryboardView]):
    storyboard_id: str
    panel_ids: tuple[str, ...]
    expected_version: int | None = None
