"""
Engine-neutral video technical inspection contract & policy.

Provides `VideoInspectorPort`, `VideoInspection`, `VideoInspectionPolicy`, and related errors
to perform technical validation of video streams independent of any specific engine or provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


class VideoInspectionError(RuntimeError):
    """Base error for video technical inspection."""


class VideoProbeUnavailableError(VideoInspectionError):
    """The video probe (ffprobe/decoder) is not available."""


@dataclass(frozen=True)
class VideoInspection:
    """Result of decoding a candidate's video stream."""

    has_video_stream: bool
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    frame_rate: Optional[float] = None
    container: str = ""
    codec: str = ""
    probe_error: str = ""


@runtime_checkable
class VideoInspectorPort(Protocol):
    """Decodes candidate bytes and reports stream facts (offline-testable).

    Real implementations (e.g. `windagent_tools.video_probe.FfprobeVideoInspector`) run a bounded process;
    tests inject a deterministic fake.
    """

    def inspect(self, data: bytes) -> VideoInspection:
        """Inspect candidate bytes; never raises for malformed input —
        malformed input yields a VideoInspection with has_video_stream=False.
        """
        ...


@dataclass(frozen=True)
class VideoInspectionPolicy:
    """Fail-closed technical acceptance policy."""

    require_video_stream: bool = True
    min_duration_seconds: float = 0.5
    max_duration_seconds: float = 600.0
    min_width: int = 64
    min_height: int = 64
    max_frame_rate: float = 240.0
    min_frame_rate: float = 0.1

    def violations(self, inspection: VideoInspection) -> tuple[str, ...]:
        """Return the list of policy violations (empty when accepted)."""
        problems: list[str] = []
        if self.require_video_stream and not inspection.has_video_stream:
            problems.append("no video stream detected")
        if inspection.duration_seconds is not None:
            if inspection.duration_seconds < self.min_duration_seconds:
                problems.append(
                    f"duration {inspection.duration_seconds:.3f}s below "
                    f"min {self.min_duration_seconds}s"
                )
            if inspection.duration_seconds > self.max_duration_seconds:
                problems.append(
                    f"duration {inspection.duration_seconds:.3f}s above "
                    f"max {self.max_duration_seconds}s"
                )
        if inspection.width is not None and inspection.height is not None:
            if inspection.width < self.min_width or inspection.height < self.min_height:
                problems.append(
                    f"resolution {inspection.width}x{inspection.height} below "
                    f"min {self.min_width}x{self.min_height}"
                )
        if inspection.frame_rate is not None:
            if inspection.frame_rate < self.min_frame_rate:
                problems.append(
                    f"frame rate {inspection.frame_rate:.3f} below "
                    f"min {self.min_frame_rate}"
                )
            if inspection.frame_rate > self.max_frame_rate:
                problems.append(
                    f"frame rate {inspection.frame_rate:.3f} above "
                    f"max {self.max_frame_rate}"
                )
        return tuple(problems)


__all__ = [
    "VideoInspection",
    "VideoInspectionError",
    "VideoInspectionPolicy",
    "VideoInspectorPort",
    "VideoProbeUnavailableError",
]
