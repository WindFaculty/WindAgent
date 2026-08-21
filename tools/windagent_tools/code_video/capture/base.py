"""
Base Contracts and CapturePort Protocol for Code Video Production.

CaptureStatus moved to core/windagent_core/contracts/code_video/capture.py.
This module re-exports for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from windagent_core.contracts.code_video import Resolution, Scene
from windagent_core.contracts.code_video.capture import CaptureStatus


@dataclass(frozen=True)
class TakeConfig:
    """Configuration parameters for capturing a visual scene take."""
    scene_id: str
    take_id: str
    resolution: Resolution = field(default_factory=lambda: Resolution(2560, 1440))
    fps: int = 30
    audio_enabled: bool = False
    format: str = "mp4"
    output_dir: Optional[str] = None
    custom_options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "take_id": self.take_id,
            "resolution": self.resolution.to_dict(),
            "fps": self.fps,
            "audio_enabled": self.audio_enabled,
            "format": self.format,
            "output_dir": self.output_dir,
            "custom_options": dict(self.custom_options),
        }


@runtime_checkable
class CapturePort(Protocol):
    """Standard protocol for capturing visual code studio takes."""

    def start(
        self,
        scene: Scene,
        take_id: Optional[str] = None,
        resolution: Optional[Resolution] = None,
        fps: int = 30,
        **kwargs: Any,
    ) -> str:
        ...

    def mark(self, timestamp_ms: int, metadata: Optional[Dict[str, Any]] = None) -> None:
        ...

    def stop(self) -> Any:
        ...

    def inspect(self, take_id: str) -> Any:
        ...


__all__ = [
    "CaptureStatus",
    "TakeConfig",
    "CapturePort",
]
