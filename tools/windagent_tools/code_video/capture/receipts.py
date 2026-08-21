"""
Take Receipts, Frame Reports, and Media Probe Models for Code Video Capture.

Canonical definitions moved to core/windagent_core/contracts/code_video/capture.py.
This module re-exports for backward compatibility.
"""

from windagent_core.contracts.code_video.capture import (
    CaptureStatus,
    TakeReceipt,
    FrameMetadata,
    FrameReport,
    MediaProbeReport,
)

__all__ = [
    "CaptureStatus",
    "TakeReceipt",
    "FrameMetadata",
    "FrameReport",
    "MediaProbeReport",
]
