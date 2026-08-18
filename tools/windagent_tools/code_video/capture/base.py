"""
Base Contracts and CapturePort Protocol for Code Video Production.

Defines the capture port interface, capture status lifecycles, and configuration
for capturing high-fidelity code studio visual takes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from windagent_workflows.code_video.contracts import Resolution, Scene


class CaptureStatus(str, Enum):
    """Lifecycle status of a capture session or take."""
    INITIALIZED = "INITIALIZED"
    RECORDING = "RECORDING"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


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
    """
    Standard protocol for capturing visual code studio takes.
    Adheres strictly to the CapturePort interface specified in Video 02 implementation plan.
    """

    def start(
        self,
        scene: Scene,
        take_id: Optional[str] = None,
        resolution: Optional[Resolution] = None,
        fps: int = 30,
        **kwargs: Any,
    ) -> str:
        """
        Start recording / capturing frames for a given scene.
        Returns the active take_id.
        """
        ...

    def mark(self, timestamp_ms: int, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Mark a keyframe / milestone event at the given timestamp within the take.
        """
        ...

    def stop(self) -> Any:
        """
        Stop capturing and finalize the take receipt.
        Returns TakeReceipt.
        """
        ...

    def inspect(self, take_id: str) -> Any:
        """
        Inspect the captured take and return a media probe report.
        """
        ...


__all__ = [
    "CaptureStatus",
    "TakeConfig",
    "CapturePort",
]
