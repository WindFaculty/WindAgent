"""Immutable Production commands (intentions with payloads)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from windagent.platform.commands import Command

from .models import (
    AssetRevisionView,
    AudioTrackView,
    CodeVideoProjectView,
    EdlView,
    MixPlanView,
    ProductionAssetView,
    ProductionProjectView,
    ProductionRevisionView,
    RenderJobView,
)

# -- projects --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateProductionProject(Command[ProductionProjectView]):
    title: str
    description: str = ""
    owner_id: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateProductionProject(Command[ProductionProjectView]):
    project_id: str
    title: str | None = None
    description: str | None = None
    status: str | None = None
    expected_version: int | None = None
    metadata_patch: dict[str, Any] = field(default_factory=dict)


# -- revisions -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateProductionRevision(Command[ProductionRevisionView]):
    project_id: str
    content_hash: str
    creator: str = "system"
    actor: str | None = None
    parent_revision_id: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeriveProductionRevision(Command[ProductionRevisionView]):
    project_id: str
    parent_revision_id: str
    new_content_hash: str
    actor: str = "system"
    invalidation_intent: str | None = None
    summary: str = ""
    expected_version: int | None = None


@dataclass(frozen=True, slots=True)
class LockProductionRevision(Command[ProductionRevisionView]):
    revision_id: str
    expected_content_hash: str | None = None
    expected_version: int | None = None


# -- assets ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateProductionAsset(Command[ProductionAssetView]):
    name: str
    kind: str = "OTHER"
    project_id: str | None = None
    description: str = ""
    source_type: str = "UPLOADED"
    license_state: str = "UNKNOWN"
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionProductionAsset(Command[ProductionAssetView]):
    asset_id: str
    target_state: str
    expected_version: int | None = None
    new_review_record: bool = False


@dataclass(frozen=True, slots=True)
class CreateAssetRevision(Command[AssetRevisionView]):
    asset_id: str
    content_hash: str
    media_type: str = "IMAGE"
    mime_type: str = "image/png"
    size_bytes: int = 0
    supersedes_revision_id: str | None = None
    normalized_format: str | None = None
    preview_artifacts: dict[str, Any] = field(default_factory=dict)
    validation_report: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


# -- audio -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateAudioTrack(Command[AudioTrackView]):
    project_id: str
    title: str
    kind: str = "DIALOGUE"
    character_id: str | None = None
    dialogue_text: str = ""
    source_path: str = ""
    source_hash: str = ""
    sample_rate: int = 48000
    channels: int = 1
    duration_seconds: float = 0.0
    language: str = "en"
    voice_profile_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CreateMixPlan(Command[MixPlanView]):
    project_id: str
    title: str = "main"
    loudness_target_lufs: float = -16.0
    peak_ceiling_db: float = -1.0
    policy_version: str = "loudness-v1"
    tracks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


# -- code video ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateCodeVideoProject(Command[CodeVideoProjectView]):
    title: str
    description: str = ""
    repo_url: str = ""
    branch: str = "main"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionCodeVideoProject(Command[CodeVideoProjectView]):
    project_id: str
    target_status: str
    expected_version: int | None = None


# -- rendering -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateRenderJob(Command[RenderJobView]):
    project_id: str
    scene_id: str = ""
    shot_id: str = ""
    revision_id: str | None = None
    frame_start: int = 1
    frame_end: int = 24
    colorspace: str = "sRGB"
    profile_id: str = "main_1080p_h264"
    input_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransitionRenderJob(Command[RenderJobView]):
    job_id: str
    target_status: str
    expected_version: int | None = None
    output_hash: str | None = None
    error: str | None = None


# -- postproduction --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateEdl(Command[EdlView]):
    project_id: str
    revision_id: str
    title: str = "main"
    items: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    audio_mix_plan_id: str = ""
    subtitle_track_id: str | None = None
    encoding_profile: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateEdl(Command[EdlView]):
    edl_id: str
    title: str | None = None
    status: str | None = None
    expected_version: int | None = None
    metadata_patch: dict[str, Any] = field(default_factory=dict)
