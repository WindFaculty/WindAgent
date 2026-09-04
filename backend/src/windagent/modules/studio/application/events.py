"""Studio domain events — one envelope per durable state change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.time import utc_now
from windagent.kernel.types import Version

EVENT_PROJECT_CREATED: Final[str] = "studio.project.created"
EVENT_SERIES_CREATED: Final[str] = "studio.series.created"
EVENT_EPISODE_CREATED: Final[str] = "studio.episode.created"
EVENT_EPISODE_TRANSITIONED: Final[str] = "studio.episode.transitioned"
EVENT_REVISION_CREATED: Final[str] = "studio.revision.created"
EVENT_REVISION_LOCKED: Final[str] = "studio.revision.locked"
EVENT_ARTIFACT_CREATED: Final[str] = "studio.artifact.created"

EVENT_VERSION: Final[int] = 1


def _envelope(
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=EntityId(aggregate_id),
        sequence=0,
        event_version=Version(EVENT_VERSION),
        occurred_at=utc_now(),
        payload=payload,
    )


def project_created(project_id: str, title: str) -> EventEnvelope:
    return _envelope(
        EVENT_PROJECT_CREATED,
        "Project",
        project_id,
        {"project_id": project_id, "title": title},
    )


def series_created(series_id: str, title: str, project_id: str | None) -> EventEnvelope:
    return _envelope(
        EVENT_SERIES_CREATED,
        "SeriesProject",
        series_id,
        {"series_id": series_id, "title": title, "project_id": project_id},
    )


def episode_created(episode_id: str, series_id: str, title: str) -> EventEnvelope:
    return _envelope(
        EVENT_EPISODE_CREATED,
        "Episode",
        episode_id,
        {"episode_id": episode_id, "series_id": series_id, "title": title},
    )


def episode_transitioned(episode_id: str, from_state: str, to_state: str) -> EventEnvelope:
    return _envelope(
        EVENT_EPISODE_TRANSITIONED,
        "Episode",
        episode_id,
        {"episode_id": episode_id, "from_state": from_state, "to_state": to_state},
    )


def revision_created(revision_id: str, episode_id: str) -> EventEnvelope:
    return _envelope(
        EVENT_REVISION_CREATED,
        "ProductionRevision",
        revision_id,
        {"revision_id": revision_id, "episode_id": episode_id},
    )


def revision_locked(revision_id: str, episode_id: str) -> EventEnvelope:
    return _envelope(
        EVENT_REVISION_LOCKED,
        "ProductionRevision",
        revision_id,
        {"revision_id": revision_id, "episode_id": episode_id},
    )


def artifact_created(artifact_id: str, episode_id: str, artifact_type: str) -> EventEnvelope:
    return _envelope(
        EVENT_ARTIFACT_CREATED,
        "StoryArtifact",
        artifact_id,
        {"artifact_id": artifact_id, "episode_id": episode_id, "artifact_type": artifact_type},
    )


@dataclass(frozen=True, slots=True)
class StudioEventFactory:
    def project_created(self, project_id: str, title: str) -> EventEnvelope:
        return project_created(project_id, title)

    def series_created(self, series_id: str, title: str, project_id: str | None) -> EventEnvelope:
        return series_created(series_id, title, project_id)

    def episode_created(self, episode_id: str, series_id: str, title: str) -> EventEnvelope:
        return episode_created(episode_id, series_id, title)

    def episode_transitioned(self, episode_id: str, from_state: str, to_state: str) -> EventEnvelope:
        return episode_transitioned(episode_id, from_state, to_state)

    def revision_created(self, revision_id: str, episode_id: str) -> EventEnvelope:
        return revision_created(revision_id, episode_id)

    def revision_locked(self, revision_id: str, episode_id: str) -> EventEnvelope:
        return revision_locked(revision_id, episode_id)

    def artifact_created(self, artifact_id: str, episode_id: str, artifact_type: str) -> EventEnvelope:
        return artifact_created(artifact_id, episode_id, artifact_type)
