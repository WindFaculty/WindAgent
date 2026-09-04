"""Contracts and domain ports for production media rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class RenderJobState(StrEnum):
    """Lifecycle states of a production render execution."""
    QUEUED = "QUEUED"
    RENDERING = "RENDERING"
    RENDERED = "RENDERED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RENDER_FAILED = "RENDER_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class RenderValidationError(RuntimeError):
    """Raised when EDL inputs or compiled render parameters are invalid."""


class RenderExecutionError(RuntimeError):
    """Raised when the rendering engine fails during execution."""


class MediaValidationError(RuntimeError):
    """Raised when the rendered output artifact fails quality or technical validation."""


@dataclass(frozen=True)
class RenderClip:
    """A single input media segment compiled from an EDL item."""
    clip_id: str
    source_path: Path
    in_point_s: float
    out_point_s: float
    duration_s: float
    track: str = "V1"
    scale_width: int = 1920
    scale_height: int = 1080
    fps: int = 60


@dataclass(frozen=True)
class RenderEncodingSpec:
    """Target output encoding parameters."""
    container: str = "mp4"
    video_codec: str = "h264"
    audio_codec: str = "aac"
    width: int = 1920
    height: int = 1080
    fps: int = 60
    pixel_format: str = "yuv420p"
    use_nvenc: bool = True
    crf: int = 20


@dataclass(frozen=True)
class RenderPlan:
    """Deterministic compilation of an EDL into a render specification."""
    job_id: str
    output_path: Path
    clips: tuple[RenderClip, ...]
    encoding: RenderEncodingSpec
    total_duration_s: float
    filter_graph_description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaValidationResult:
    """Technical audit results of a rendered media artifact."""
    is_valid: bool
    artifact_path: str
    container: str
    codec: str
    width: int
    height: int
    fps: float
    duration_s: float
    file_size_bytes: int
    video_streams: int
    audio_streams: int
    decode_errors: int
    checksum: str
    probe_raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "artifact_path": self.artifact_path,
            "container": self.container,
            "codec": self.codec,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration_s": self.duration_s,
            "file_size_bytes": self.file_size_bytes,
            "video_streams": self.video_streams,
            "audio_streams": self.audio_streams,
            "decode_errors": self.decode_errors,
            "checksum": self.checksum,
        }


@runtime_checkable
class MediaRendererPort(Protocol):
    """Port for media rendering engines (FFmpeg, GStreamer, etc.)."""

    async def render(self, plan: RenderPlan) -> MediaValidationResult:
        """Execute the render plan and return validated media results."""
        ...
