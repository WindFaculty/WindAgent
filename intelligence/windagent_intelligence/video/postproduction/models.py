"""
Internal DTOs and specifications for post-production intelligence services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from windagent_core.domain.video_production.enums import (
    PostProductionIssueCode,
)
from windagent_core.domain.video_production.postproduction import (
    EncodingProfile,
)


@dataclass(frozen=True)
class InputMediaMetadata:
    """Metadata extracted by probing an input video/audio media file."""

    file_path: Path
    content_hash: str
    duration_seconds: float
    width: int
    height: int
    frame_rate: float
    video_codec: str
    pixel_format: str
    has_audio: bool
    audio_codec: str = ""
    audio_sample_rate: int = 0
    audio_channels: int = 0
    rotation_degrees: int = 0


@dataclass(frozen=True)
class NormalizationSpec:
    """Normalization requirement computed for an input clip."""

    file_path: Path
    target_profile: EncodingProfile
    needs_scaling: bool
    needs_padding: bool
    needs_fps_conversion: bool
    needs_audio_resampling: bool
    filter_graph: str = ""


@dataclass(frozen=True)
class FfmpegRenderPlan:
    """Deterministic render plan containing generated filter graphs and argv."""

    edl_hash: str
    profile: EncodingProfile
    output_path: Path
    proxy_path: Path
    thumbnail_path: Path
    argv_assemble: tuple[str, ...]
    argv_proxy: tuple[str, ...]
    argv_thumbnail: tuple[str, ...]
    filter_graph_str: str


@dataclass(frozen=True)
class VerificationResult:
    """Detailed verification outcome for a post-production render."""

    is_valid: bool
    file_path: Path
    content_hash: str
    duration_seconds: float
    format_name: str
    video_stream_valid: bool
    audio_stream_valid: bool
    sample_frames_decoded: int
    loudness_lufs: float
    peak_db: float
    issues: tuple[PostProductionIssueCode, ...] = field(default_factory=tuple)
    proxy_path: Path | None = None
    proxy_hash: str = ""
    thumbnail_path: Path | None = None
    thumbnail_hash: str = ""


@dataclass(frozen=True)
class ReproducibilityReport:
    """Audit report comparing render runs for deterministic reproducibility."""

    is_reproducible: bool
    input_hashes_matched: bool
    edl_hash_matched: bool
    command_manifest_matched: bool
    output_sha256: str
    previous_sha256: str = ""
    mismatch_reasons: tuple[str, ...] = field(default_factory=tuple)
