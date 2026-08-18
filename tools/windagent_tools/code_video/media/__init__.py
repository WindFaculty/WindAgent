"""
Media Processing and Verification Tools for Code Video Production.

Provides TakeAssembler, TakesManifest, VisualMasterAssembler, CueSheet, TransitionPolicy, TakeVerifier, and TakeVerificationResult.
"""

from __future__ import annotations

from windagent_tools.code_video.media.assembler import (
    FORBIDDEN_FLASHY_TRANSITIONS,
    CueSheet,
    CueSheetEntry,
    MasterAssemblyResult,
    TakeAssembler,
    TakesManifest,
    TransitionPolicy,
    TransitionRule,
    TransitionType,
    VideoAssemblyConfig,
    VisualMasterAssembler,
    format_timecode_ms,
)
from windagent_tools.code_video.media.verifier import (
    TakeVerificationResult,
    TakeVerifier,
)
from windagent_tools.code_video.media.video_generator import (
    RealMasterVideoSynthesizer,
    Video02FrameRenderer,
)

__all__ = [
    "TransitionType",
    "TransitionRule",
    "TransitionPolicy",
    "FORBIDDEN_FLASHY_TRANSITIONS",
    "format_timecode_ms",
    "CueSheetEntry",
    "CueSheet",
    "TakesManifest",
    "VideoAssemblyConfig",
    "MasterAssemblyResult",
    "TakeAssembler",
    "VisualMasterAssembler",
    "TakeVerificationResult",
    "TakeVerifier",
    "Video02FrameRenderer",
    "RealMasterVideoSynthesizer",
]

