"""
Core contracts for Code Video Capture Receipt types.

Pure data contracts — no implementation, no tool dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError


class CaptureStatus(str, Enum):
    """Lifecycle status of a capture session or take."""
    INITIALIZED = "INITIALIZED"
    RECORDING = "RECORDING"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TakeReceipt:
    """
    Cryptographically verifiable receipt for a single recorded visual take.
    Matches plan §Phase 7 schema requirements.
    """
    take_id: str
    scene_id: str
    start_ms: int
    duration_ms: int
    resolution: str = "2560x1440"
    fps: int = 30
    frame_count: int = 0
    output_hash: str = ""
    status: str = "VERIFIED"
    audio_enabled: bool = False
    output_file: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.take_id:
            raise ValidationError("TakeReceipt take_id cannot be empty")
        if not self.scene_id:
            raise ValidationError("TakeReceipt scene_id cannot be empty")
        if self.start_ms < 0:
            raise ValidationError(f"TakeReceipt start_ms must be non-negative, got {self.start_ms}")
        if self.duration_ms <= 0:
            raise ValidationError(f"TakeReceipt duration_ms must be positive, got {self.duration_ms}")
        if self.fps <= 0:
            raise ValidationError(f"TakeReceipt fps must be positive, got {self.fps}")
        if self.audio_enabled:
            raise ValidationError("TakeReceipt audio_enabled must be False for Video 02 (Audio is EXCLUDED)")

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms

    @property
    def expected_frame_count(self) -> int:
        return (self.duration_ms * self.fps) // 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "take_id": self.take_id,
            "scene_id": self.scene_id,
            "start_ms": self.start_ms,
            "duration_ms": self.duration_ms,
            "resolution": self.resolution,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "output_hash": self.output_hash,
            "status": self.status,
            "audio_enabled": self.audio_enabled,
            "output_file": self.output_file,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TakeReceipt:
        return cls(
            take_id=str(data.get("take_id", "")),
            scene_id=str(data.get("scene_id", "")),
            start_ms=int(data.get("start_ms", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            resolution=str(data.get("resolution", "2560x1440")),
            fps=int(data.get("fps", 30)),
            frame_count=int(data.get("frame_count", 0)),
            output_hash=str(data.get("output_hash", "")),
            status=str(data.get("status", "VERIFIED")),
            audio_enabled=bool(data.get("audio_enabled", False)),
            output_file=data.get("output_file"),
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> TakeReceipt:
        import json
        try:
            data = json.loads(json_str)
        except Exception as e:
            raise ValidationError(f"Failed to parse JSON for TakeReceipt: {e}")
        return cls.from_dict(data)


@dataclass(frozen=True)
class FrameMetadata:
    """Diagnostic information for a sampled frame or keyframe."""
    frame_index: int
    timestamp_ms: int
    scene_id: str
    visual_mode: str
    frame_hash: str
    is_keyframe: bool = False
    active_file: Optional[str] = None
    cursor_position: Optional[List[int]] = None
    event_label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp_ms": self.timestamp_ms,
            "scene_id": self.scene_id,
            "visual_mode": self.visual_mode,
            "frame_hash": self.frame_hash,
            "is_keyframe": self.is_keyframe,
            "active_file": self.active_file,
            "cursor_position": list(self.cursor_position) if self.cursor_position else None,
            "event_label": self.event_label,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FrameMetadata:
        return cls(
            frame_index=int(data.get("frame_index", 0)),
            timestamp_ms=int(data.get("timestamp_ms", 0)),
            scene_id=str(data.get("scene_id", "")),
            visual_mode=str(data.get("visual_mode", "")),
            frame_hash=str(data.get("frame_hash", "")),
            is_keyframe=bool(data.get("is_keyframe", False)),
            active_file=data.get("active_file"),
            cursor_position=list(data["cursor_position"]) if data.get("cursor_position") else None,
            event_label=data.get("event_label"),
        )


@dataclass(frozen=True)
class FrameReport:
    """Summary and sampling report of all frames in a take."""
    take_id: str
    scene_id: str
    total_frames: int
    duration_ms: int
    fps: int
    keyframe_count: int
    keyframe_hashes: List[str] = field(default_factory=list)
    frame_samples: List[FrameMetadata] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "take_id": self.take_id,
            "scene_id": self.scene_id,
            "total_frames": self.total_frames,
            "duration_ms": self.duration_ms,
            "fps": self.fps,
            "keyframe_count": self.keyframe_count,
            "keyframe_hashes": list(self.keyframe_hashes),
            "frame_samples": [s.to_dict() for s in self.frame_samples],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FrameReport:
        return cls(
            take_id=str(data.get("take_id", "")),
            scene_id=str(data.get("scene_id", "")),
            total_frames=int(data.get("total_frames", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            fps=int(data.get("fps", 30)),
            keyframe_count=int(data.get("keyframe_count", 0)),
            keyframe_hashes=list(data.get("keyframe_hashes", [])),
            frame_samples=[FrameMetadata.from_dict(s) for s in data.get("frame_samples", [])],
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> FrameReport:
        import json
        try:
            data = json.loads(json_str)
        except Exception as e:
            raise ValidationError(f"Failed to parse JSON for FrameReport: {e}")
        return cls.from_dict(data)


@dataclass(frozen=True)
class MediaProbeReport:
    """Technical media stream inspection report matching ffprobe style output."""
    take_id: str
    scene_id: str
    container: str = "mp4"
    codec: str = "h264"
    width: int = 2560
    height: int = 1440
    frame_rate: float = 30.0
    frame_count: int = 0
    duration_seconds: float = 0.0
    audio_streams_count: int = 0
    has_video_stream: bool = True
    has_audio_stream: bool = False
    pixel_format: str = "yuv420p"
    color_space: str = "bt709"
    probe_status: str = "VALID"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "take_id": self.take_id,
            "scene_id": self.scene_id,
            "container": self.container,
            "codec": self.codec,
            "width": self.width,
            "height": self.height,
            "frame_rate": self.frame_rate,
            "frame_count": self.frame_count,
            "duration_seconds": self.duration_seconds,
            "audio_streams_count": self.audio_streams_count,
            "has_video_stream": self.has_video_stream,
            "has_audio_stream": self.has_audio_stream,
            "pixel_format": self.pixel_format,
            "color_space": self.color_space,
            "probe_status": self.probe_status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MediaProbeReport:
        return cls(
            take_id=str(data.get("take_id", "")),
            scene_id=str(data.get("scene_id", "")),
            container=str(data.get("container", "mp4")),
            codec=str(data.get("codec", "h264")),
            width=int(data.get("width", 2560)),
            height=int(data.get("height", 1440)),
            frame_rate=float(data.get("frame_rate", 30.0)),
            frame_count=int(data.get("frame_count", 0)),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            audio_streams_count=int(data.get("audio_streams_count", 0)),
            has_video_stream=bool(data.get("has_video_stream", True)),
            has_audio_stream=bool(data.get("has_audio_stream", False)),
            pixel_format=str(data.get("pixel_format", "yuv420p")),
            color_space=str(data.get("color_space", "bt709")),
            probe_status=str(data.get("probe_status", "VALID")),
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> MediaProbeReport:
        import json
        try:
            data = json.loads(json_str)
        except Exception as e:
            raise ValidationError(f"Failed to parse JSON for MediaProbeReport: {e}")
        return cls.from_dict(data)
