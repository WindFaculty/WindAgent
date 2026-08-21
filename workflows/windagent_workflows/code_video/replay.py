"""
Code Video Replay compatibility shim.

Data types are canonical in core/windagent_core/contracts/code_video/replay.py.
Implementation classes are available via __getattr__ in the package __init__.
"""

from windagent_core.contracts.code_video.replay import (
    TypingSpeedMode,
    SPEED_MODE_CPS_MAP,
    ReplayStepRecord,
    ReplayTrace,
    CheckpointDefinition,
)

__all__ = [
    "TypingSpeedMode",
    "SPEED_MODE_CPS_MAP",
    "ReplayStepRecord",
    "ReplayTrace",
    "CheckpointDefinition",
]
