"""Application view models and durable row types for Production."""

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
class ProductionProjectRow:
    project_id: str
    title: str
    description: str
    owner_id: str
    status: str
    current_revision_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class ProductionRevisionRow:
    revision_id: str
    project_id: str
    parent_revision_id: str | None
    creator: str
    actor: str
    created_at: datetime | None
    content_hash: str
    status: str
    locked: bool
    invalidation_intent: str | None
    summary: str
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class ProductionAssetRow:
    asset_id: str
    project_id: str | None
    name: str
    kind: str
    lifecycle_state: str
    processing_state: str
    active_revision_id: str | None
    source_type: str
    license_state: str
    tags_json: str
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class AssetRevisionRow:
    revision_id: str
    asset_id: str
    supersedes_revision_id: str | None
    content_hash: str
    media_type: str
    mime_type: str
    size_bytes: int
    normalized_format: str | None
    preview_json: str
    validation_json: str
    provenance_json: str
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class AudioTrackRow:
    track_id: str
    project_id: str
    kind: str
    title: str
    character_id: str | None
    dialogue_text: str
    source_path: str
    source_hash: str
    sample_rate: int
    channels: int
    duration_seconds: float
    language: str
    voice_profile_id: str | None
    rights_state: str
    provenance_json: str
    created_at: datetime | None
    metadata_json: str


@dataclass(frozen=True, slots=True)
class MixPlanRow:
    mix_plan_id: str
    project_id: str
    title: str
    loudness_target_lufs: float
    peak_ceiling_db: float
    policy_version: str
    tracks_json: str
    created_at: datetime | None
    updated_at: datetime | None
    metadata_json: str


@dataclass(frozen=True, slots=True)
class CodeVideoProjectRow:
    project_id: str
    title: str
    description: str
    status: str
    repo_url: str
    branch: str
    tutorial_steps_json: str
    current_checkpoint: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class RenderJobRow:
    job_id: str
    project_id: str
    revision_id: str | None
    scene_id: str
    shot_id: str
    status: str
    frame_start: int
    frame_end: int
    colorspace: str
    profile_id: str
    attempt: int
    input_hash: str
    output_hash: str
    error: str
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata_json: str


@dataclass(frozen=True, slots=True)
class EdlRow:
    edl_id: str
    project_id: str
    revision_id: str
    title: str
    status: str
    items_json: str
    audio_mix_plan_id: str
    subtitle_track_id: str | None
    encoding_profile_json: str
    edl_hash: str
    created_at: datetime | None
    updated_at: datetime | None
    metadata_json: str


# --------------------------------------------------------------------------- #
# Views (application return types)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ProductionProjectView:
    project_id: str
    title: str
    description: str
    owner_id: str
    status: str
    current_revision_id: str | None
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
            "status": self.status,
            "current_revision_id": self.current_revision_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ProductionRevisionView:
    revision_id: str
    project_id: str
    parent_revision_id: str | None
    creator: str
    actor: str
    created_at: datetime | None
    content_hash: str
    status: str
    locked: bool
    invalidation_intent: str | None
    summary: str
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "project_id": self.project_id,
            "parent_revision_id": self.parent_revision_id,
            "creator": self.creator,
            "actor": self.actor,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "content_hash": self.content_hash,
            "status": self.status,
            "locked": self.locked,
            "invalidation_intent": self.invalidation_intent,
            "summary": self.summary,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ProductionAssetView:
    asset_id: str
    project_id: str | None
    name: str
    kind: str
    lifecycle_state: str
    processing_state: str
    active_revision_id: str | None
    source_type: str
    license_state: str
    tags: tuple[str, ...]
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "project_id": self.project_id,
            "name": self.name,
            "kind": self.kind,
            "lifecycle_state": self.lifecycle_state,
            "processing_state": self.processing_state,
            "active_revision_id": self.active_revision_id,
            "source_type": self.source_type,
            "license_state": self.license_state,
            "tags": list(self.tags),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class AssetRevisionView:
    revision_id: str
    asset_id: str
    supersedes_revision_id: str | None
    content_hash: str
    media_type: str
    mime_type: str
    size_bytes: int
    normalized_format: str | None
    preview_artifacts: dict[str, Any]
    validation_report: dict[str, Any]
    provenance: dict[str, Any]
    created_at: datetime | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "asset_id": self.asset_id,
            "supersedes_revision_id": self.supersedes_revision_id,
            "content_hash": self.content_hash,
            "media_type": self.media_type,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "normalized_format": self.normalized_format,
            "preview_artifacts": self.preview_artifacts,
            "validation_report": self.validation_report,
            "provenance": self.provenance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass(frozen=True, slots=True)
class AudioTrackView:
    track_id: str
    project_id: str
    kind: str
    title: str
    character_id: str | None
    dialogue_text: str
    source_path: str
    source_hash: str
    sample_rate: int
    channels: int
    duration_seconds: float
    language: str
    voice_profile_id: str | None
    rights_state: str
    provenance: dict[str, Any]
    created_at: datetime | None
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "title": self.title,
            "character_id": self.character_id,
            "dialogue_text": self.dialogue_text,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "duration_seconds": self.duration_seconds,
            "language": self.language,
            "voice_profile_id": self.voice_profile_id,
            "rights_state": self.rights_state,
            "provenance": self.provenance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class MixPlanView:
    mix_plan_id: str
    project_id: str
    title: str
    loudness_target_lufs: float
    peak_ceiling_db: float
    policy_version: str
    tracks: tuple[dict[str, Any], ...]
    created_at: datetime | None
    updated_at: datetime | None
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "mix_plan_id": self.mix_plan_id,
            "project_id": self.project_id,
            "title": self.title,
            "loudness_target_lufs": self.loudness_target_lufs,
            "peak_ceiling_db": self.peak_ceiling_db,
            "policy_version": self.policy_version,
            "tracks": list(self.tracks),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class CodeVideoProjectView:
    project_id: str
    title: str
    description: str
    status: str
    repo_url: str
    branch: str
    tutorial_steps: tuple[str, ...]
    current_checkpoint: str | None
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "repo_url": self.repo_url,
            "branch": self.branch,
            "tutorial_steps": list(self.tutorial_steps),
            "current_checkpoint": self.current_checkpoint,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class RenderJobView:
    job_id: str
    project_id: str
    revision_id: str | None
    scene_id: str
    shot_id: str
    status: str
    frame_start: int
    frame_end: int
    colorspace: str
    profile_id: str
    attempt: int
    input_hash: str
    output_hash: str
    error: str
    created_at: datetime | None
    updated_at: datetime | None
    optimistic_version: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "scene_id": self.scene_id,
            "shot_id": self.shot_id,
            "status": self.status,
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "colorspace": self.colorspace,
            "profile_id": self.profile_id,
            "attempt": self.attempt,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "optimistic_version": self.optimistic_version,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class EdlView:
    edl_id: str
    project_id: str
    revision_id: str
    title: str
    status: str
    items: tuple[dict[str, Any], ...]
    audio_mix_plan_id: str
    subtitle_track_id: str | None
    encoding_profile: dict[str, Any]
    edl_hash: str
    created_at: datetime | None
    updated_at: datetime | None
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "edl_id": self.edl_id,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "title": self.title,
            "status": self.status,
            "items": list(self.items),
            "audio_mix_plan_id": self.audio_mix_plan_id,
            "subtitle_track_id": self.subtitle_track_id,
            "encoding_profile": self.encoding_profile,
            "edl_hash": self.edl_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }
