"""
Code Video IR contracts — canonical source of truth in core.

All neutral, implementation-free types for code video production:
Scene, Resolution, Action, CodeVideoPlan, and related data contracts.

Consumers (tools, workflows, workers) import from here, NOT from
windagent_workflows.code_video.contracts.
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
