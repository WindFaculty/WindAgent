"""Application view models and durable row types for Studio.

Rows are transport-neutral storage shapes; views are the application surface
returned through the command/query buses.  Both stay plain dataclasses so the
domain never owns SQL concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Durable rows (1:1 with tables)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ProjectRow:
    project_id: str
    title: str
    description: str
    owner_id: str
    series_ids_json: str
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class SeriesRow:
    series_id: str
    project_id: str | None
    title: str
    description: str
    episode_ids_json: str
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class EpisodeRow:
    episode_id: str
    series_id: str
    project_id: str | None
    title: str
    episode_number: int
    logline: str
    state: str
    current_revision_id: str | None
    active_run_id: str | None
    awaiting_checkpoint: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class RevisionRow:
    revision_id: str
    series_id: str
    episode_id: str
    parent_revision_id: str | None
    creator: str
    actor: str
    created_at: datetime | None
    content_hash: str
    status: str
    lock_state: str
    invalidation_intent: str | None
    summary: str
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class ArtifactRow:
    artifact_id: str
    artifact_type: str
    schema_version: str
    series_id: str
    episode_id: str
    revision_id: str | None
    content_hash: str
    input_refs_json: str
    created_at: datetime | None
    created_by: str
    content_json: str
    extra_json: str


@dataclass(frozen=True, slots=True)
class CharacterRow:
    character_id: str
    series_id: str
    name: str
    display_name: str
    role: str
    archetype: str
    description: str
    traits_json: str
    backstory: str
    portrait_artifact_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class WorldLocationRow:
    location_id: str
    series_id: str
    name: str
    description: str
    geography: str
    metadata_json: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorldPropRow:
    prop_id: str
    series_id: str
    name: str
    description: str
    significance: str
    metadata_json: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class StoryboardRow:
    storyboard_id: str
    episode_id: str
    series_id: str
    title: str
    panels_json: str
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


# --------------------------------------------------------------------------- #
# Views (application return types)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ProjectView:
    project_id: str
    title: str
    description: str
    owner_id: str
    series_ids: tuple[str, ...]
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "owner_id": self.owner_id,
            "series_ids": list(self.series_ids),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class SeriesView:
    series_id: str
    project_id: str | None
    title: str
    description: str
    episode_ids: tuple[str, ...]
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "episode_ids": list(self.episode_ids),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class EpisodeView:
    episode_id: str
    series_id: str
    project_id: str | None
    title: str
    episode_number: int
    logline: str
    state: str
    current_revision_id: str | None
    active_run_id: str | None
    awaiting_checkpoint: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]
    revision_summary: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "series_id": self.series_id,
            "project_id": self.project_id,
            "title": self.title,
            "episode_number": self.episode_number,
            "logline": self.logline,
            "state": self.state,
            "current_revision_id": self.current_revision_id,
            "active_run_id": self.active_run_id,
            "awaiting_checkpoint": self.awaiting_checkpoint,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class RevisionView:
    revision_id: str
    series_id: str
    episode_id: str
    parent_revision_id: str | None
    creator: str
    actor: str
    created_at: datetime | None
    content_hash: str
    status: str
    lock_state: str
    invalidation_intent: str | None
    summary: str
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "series_id": self.series_id,
            "episode_id": self.episode_id,
            "parent_revision_id": self.parent_revision_id,
            "creator": self.creator,
            "actor": self.actor,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "content_hash": self.content_hash,
            "status": self.status,
            "lock_state": self.lock_state,
            "invalidation_intent": self.invalidation_intent,
            "summary": self.summary,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ArtifactView:
    artifact_id: str
    artifact_type: str
    schema_version: str
    series_id: str
    episode_id: str
    revision_id: str | None
    content_hash: str
    input_artifact_refs: tuple[str, ...]
    created_at: datetime | None
    created_by: str
    content: Any
    extra: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "series_id": self.series_id,
            "episode_id": self.episode_id,
            "revision_id": self.revision_id,
            "content_hash": self.content_hash,
            "input_artifact_refs": list(self.input_artifact_refs),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "content": self.content,
            "extra": self.extra,
        }


@dataclass(frozen=True, slots=True)
class CharacterView:
    character_id: str
    series_id: str
    name: str
    display_name: str
    role: str
    archetype: str
    description: str
    traits: tuple[str, ...]
    backstory: str
    portrait_artifact_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "series_id": self.series_id,
            "name": self.name,
            "display_name": self.display_name,
            "role": self.role,
            "archetype": self.archetype,
            "description": self.description,
            "traits": list(self.traits),
            "backstory": self.backstory,
            "portrait_artifact_id": self.portrait_artifact_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class StoryboardView:
    storyboard_id: str
    episode_id: str
    series_id: str
    title: str
    panels: tuple[dict[str, Any], ...]
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "storyboard_id": self.storyboard_id,
            "episode_id": self.episode_id,
            "series_id": self.series_id,
            "title": self.title,
            "panels": list(self.panels),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }
