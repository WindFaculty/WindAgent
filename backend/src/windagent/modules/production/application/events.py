"""Production domain events — one envelope per durable state change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.kernel.time import utc_now
from windagent.kernel.types import Version

EVENT_PROJECT_CREATED: Final[str] = "production.project.created"
EVENT_PROJECT_UPDATED: Final[str] = "production.project.updated"
EVENT_REVISION_CREATED: Final[str] = "production.revision.created"
EVENT_REVISION_LOCKED: Final[str] = "production.revision.locked"
EVENT_ASSET_CREATED: Final[str] = "production.asset.created"
EVENT_ASSET_TRANSITIONED: Final[str] = "production.asset.transitioned"
EVENT_ASSET_REVISION_CREATED: Final[str] = "production.asset_revision.created"
EVENT_AUDIO_TRACK_CREATED: Final[str] = "production.audio_track.created"
EVENT_MIX_PLAN_CREATED: Final[str] = "production.mix_plan.created"
EVENT_CODE_VIDEO_CREATED: Final[str] = "production.code_video.created"
EVENT_CODE_VIDEO_TRANSITIONED: Final[str] = "production.code_video.transitioned"
EVENT_RENDER_JOB_CREATED: Final[str] = "production.render_job.created"
EVENT_RENDER_JOB_TRANSITIONED: Final[str] = "production.render_job.transitioned"
EVENT_EDL_CREATED: Final[str] = "production.edl.created"
EVENT_EDL_UPDATED: Final[str] = "production.edl.updated"

EVENT_VERSION: Final[int] = 1


def _envelope(event_type: str, aggregate_type: str, aggregate_id: str, payload: dict[str, Any]) -> EventEnvelope:
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
    return _envelope(EVENT_PROJECT_CREATED, "VideoProject", project_id, {"project_id": project_id, "title": title})


def project_updated(project_id: str) -> EventEnvelope:
    return _envelope(EVENT_PROJECT_UPDATED, "VideoProject", project_id, {"project_id": project_id})


def revision_created(revision_id: str, project_id: str) -> EventEnvelope:
    return _envelope(EVENT_REVISION_CREATED, "ProductionRevision", revision_id, {"revision_id": revision_id, "project_id": project_id})


def revision_locked(revision_id: str, project_id: str) -> EventEnvelope:
    return _envelope(EVENT_REVISION_LOCKED, "ProductionRevision", revision_id, {"revision_id": revision_id, "project_id": project_id})


def asset_created(asset_id: str, project_id: str | None) -> EventEnvelope:
    return _envelope(EVENT_ASSET_CREATED, "ProductionAsset", asset_id, {"asset_id": asset_id, "project_id": project_id})


def asset_transitioned(asset_id: str, from_state: str, to_state: str) -> EventEnvelope:
    return _envelope(
        EVENT_ASSET_TRANSITIONED, "ProductionAsset", asset_id, {"asset_id": asset_id, "from_state": from_state, "to_state": to_state}
    )


def asset_revision_created(revision_id: str, asset_id: str) -> EventEnvelope:
    return _envelope(EVENT_ASSET_REVISION_CREATED, "AssetRevision", revision_id, {"revision_id": revision_id, "asset_id": asset_id})


def audio_track_created(track_id: str, project_id: str) -> EventEnvelope:
    return _envelope(EVENT_AUDIO_TRACK_CREATED, "AudioTrack", track_id, {"track_id": track_id, "project_id": project_id})


def mix_plan_created(mix_plan_id: str, project_id: str) -> EventEnvelope:
    return _envelope(EVENT_MIX_PLAN_CREATED, "AudioMixPlan", mix_plan_id, {"mix_plan_id": mix_plan_id, "project_id": project_id})


def code_video_created(project_id: str, title: str) -> EventEnvelope:
    return _envelope(EVENT_CODE_VIDEO_CREATED, "CodeVideoProject", project_id, {"project_id": project_id, "title": title})


def code_video_transitioned(project_id: str, from_status: str, to_status: str) -> EventEnvelope:
    return _envelope(
        EVENT_CODE_VIDEO_TRANSITIONED, "CodeVideoProject", project_id, {"project_id": project_id, "from_status": from_status, "to_status": to_status}
    )


def render_job_created(job_id: str, project_id: str) -> EventEnvelope:
    return _envelope(EVENT_RENDER_JOB_CREATED, "RenderJob", job_id, {"job_id": job_id, "project_id": project_id})


def render_job_transitioned(job_id: str, from_status: str, to_status: str) -> EventEnvelope:
    return _envelope(
        EVENT_RENDER_JOB_TRANSITIONED, "RenderJob", job_id, {"job_id": job_id, "from_status": from_status, "to_status": to_status}
    )


def edl_created(edl_id: str, project_id: str) -> EventEnvelope:
    return _envelope(EVENT_EDL_CREATED, "EditDecisionList", edl_id, {"edl_id": edl_id, "project_id": project_id})


def edl_updated(edl_id: str, project_id: str) -> EventEnvelope:
    return _envelope(EVENT_EDL_UPDATED, "EditDecisionList", edl_id, {"edl_id": edl_id, "project_id": project_id})


@dataclass(frozen=True, slots=True)
class ProductionEventFactory:
    def project_created(self, project_id: str, title: str) -> EventEnvelope:
        return project_created(project_id, title)

    def project_updated(self, project_id: str) -> EventEnvelope:
        return project_updated(project_id)

    def revision_created(self, revision_id: str, project_id: str) -> EventEnvelope:
        return revision_created(revision_id, project_id)

    def revision_locked(self, revision_id: str, project_id: str) -> EventEnvelope:
        return revision_locked(revision_id, project_id)

    def asset_created(self, asset_id: str, project_id: str | None) -> EventEnvelope:
        return asset_created(asset_id, project_id)

    def asset_transitioned(self, asset_id: str, from_state: str, to_state: str) -> EventEnvelope:
        return asset_transitioned(asset_id, from_state, to_state)

    def asset_revision_created(self, revision_id: str, asset_id: str) -> EventEnvelope:
        return asset_revision_created(revision_id, asset_id)

    def audio_track_created(self, track_id: str, project_id: str) -> EventEnvelope:
        return audio_track_created(track_id, project_id)

    def mix_plan_created(self, mix_plan_id: str, project_id: str) -> EventEnvelope:
        return mix_plan_created(mix_plan_id, project_id)

    def code_video_created(self, project_id: str, title: str) -> EventEnvelope:
        return code_video_created(project_id, title)

    def code_video_transitioned(self, project_id: str, from_status: str, to_status: str) -> EventEnvelope:
        return code_video_transitioned(project_id, from_status, to_status)

    def render_job_created(self, job_id: str, project_id: str) -> EventEnvelope:
        return render_job_created(job_id, project_id)

    def render_job_transitioned(self, job_id: str, from_status: str, to_status: str) -> EventEnvelope:
        return render_job_transitioned(job_id, from_status, to_status)

    def edl_created(self, edl_id: str, project_id: str) -> EventEnvelope:
        return edl_created(edl_id, project_id)

    def edl_updated(self, edl_id: str, project_id: str) -> EventEnvelope:
        return edl_updated(edl_id, project_id)
