"""
Browser Capture Adapter for Code Video Production.

Implements CapturePort protocol for recording-safe headless browser frame capture,
integrating with WindAgent's browser runtime and evidence capture facilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from windagent_core.errors.exceptions import NotFoundError, ValidationError
from windagent_core.contracts.code_video import (
    CodeVideoPlan,
    Resolution,
    Scene,
    VisualMode,
)

from windagent_tools.code_video.capture.base import CapturePort, CaptureStatus, TakeConfig
from windagent_tools.code_video.capture.receipts import (
    FrameMetadata,
    FrameReport,
    MediaProbeReport,
    TakeReceipt,
)
from windagent_tools.code_video.capture.studio_capture import StudioCaptureEngine


class BrowserCaptureAdapter(CapturePort):
    """
    Browser-based capture adapter supporting headless web recording and DOM screenshotting.
    Delegates deterministic rendering to StudioCaptureEngine while providing browser session hooks.
    """

    def __init__(
        self,
        engine: Optional[StudioCaptureEngine] = None,
        base_url: str = "http://localhost:3000",
    ) -> None:
        self.engine = engine or StudioCaptureEngine()
        self.base_url = base_url
        self._session_active: bool = False
        self._viewport: Resolution = Resolution(2560, 1440)

    # ------------------------------------------------------------------
    # CapturePort Implementation
    # ------------------------------------------------------------------

    def start(
        self,
        scene: Scene,
        take_id: Optional[str] = None,
        resolution: Optional[Resolution] = None,
        fps: int = 30,
        **kwargs: Any,
    ) -> str:
        self._viewport = resolution or Resolution(2560, 1440)
        self._session_active = True
        return self.engine.start(
            scene=scene,
            take_id=take_id,
            resolution=self._viewport,
            fps=fps,
            **kwargs,
        )

    def mark(self, timestamp_ms: int, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.engine.mark(timestamp_ms=timestamp_ms, metadata=metadata)

    def stop(self) -> TakeReceipt:
        receipt = self.engine.stop()
        self._session_active = False
        return receipt

    def inspect(self, take_id: str) -> MediaProbeReport:
        return self.engine.inspect(take_id)

    # ------------------------------------------------------------------
    # Scene Capture
    # ------------------------------------------------------------------

    def capture_scene(
        self,
        scene: Scene,
        take_id: Optional[str] = None,
        resolution: Resolution = Resolution(2560, 1440),
        fps: int = 30,
        sample_interval_ms: int = 1000,
    ) -> Tuple[TakeReceipt, FrameReport, MediaProbeReport]:
        return self.engine.capture_scene(
            scene=scene,
            take_id=take_id,
            resolution=resolution,
            fps=fps,
            sample_interval_ms=sample_interval_ms,
        )

    def capture_all_scenes(
        self,
        plan: CodeVideoPlan,
        resolution: Resolution = Resolution(2560, 1440),
        fps: int = 30,
    ) -> Dict[str, Tuple[TakeReceipt, FrameReport, MediaProbeReport]]:
        return self.engine.capture_all_scenes(
            plan=plan,
            resolution=resolution,
            fps=fps,
        )


__all__ = ["BrowserCaptureAdapter"]
