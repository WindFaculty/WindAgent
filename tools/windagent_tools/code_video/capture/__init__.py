"""
Capture Subsystem Package for Code Video Production.

Provides CapturePort protocol, TakeReceipt models, FrameReports, MediaProbeReports,
StudioCaptureEngine, and BrowserCaptureAdapter.
"""

from __future__ import annotations

from windagent_tools.code_video.capture.base import (
    CapturePort,
    CaptureStatus,
    TakeConfig,
)
from windagent_tools.code_video.capture.browser_capture import BrowserCaptureAdapter
from windagent_tools.code_video.capture.receipts import (
    FrameMetadata,
    FrameReport,
    MediaProbeReport,
    TakeReceipt,
)
from windagent_tools.code_video.capture.studio_capture import StudioCaptureEngine

__all__ = [
    "CaptureStatus",
    "TakeConfig",
    "CapturePort",
    "TakeReceipt",
    "FrameMetadata",
    "FrameReport",
    "MediaProbeReport",
    "StudioCaptureEngine",
    "BrowserCaptureAdapter",
]
