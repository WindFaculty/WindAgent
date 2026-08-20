"""
Code Video contracts — compatibility shim.

All canonical types have been moved to:
    windagent_core.contracts.code_video

This module re-exports them for backward compatibility with any remaining
callers inside the workflows package. New code must import from core directly.
"""

from windagent_core.contracts.code_video.models import (
    ActionType,
    VisualMode,
    Resolution,
    OutputPolicy,
    Action,
    ExpectedState,
    Annotation,
    Scene,
    CodeVideoPlan,
    FORBIDDEN_COORDINATE_KEYS,
    FORBIDDEN_AUDIO_KEYS,
)

__all__ = [
    "ActionType",
    "VisualMode",
    "Resolution",
    "OutputPolicy",
    "Action",
    "ExpectedState",
    "Annotation",
    "Scene",
    "CodeVideoPlan",
    "FORBIDDEN_COORDINATE_KEYS",
    "FORBIDDEN_AUDIO_KEYS",
]
