"""
Code Video Replay compatibility shim.

Canonical implementation moved to windagent_tools.code_video.replay.
This module re-exports for backward compatibility.
"""
from windagent_tools.code_video.replay import (
    CHECKPOINT_CODE_MAP,
    CheckpointCodeResolver,
    DeterministicReplayEngine,
    ReplayStepRecord,
    ReplayTrace,
    SPEED_MODE_CPS_MAP,
    TerminalReplayExecutor,
    TypingSimulator,
    TypingSpeedMode,
    VERIFIED_TERMINAL_RECEIPTS,
)

__all__ = [
    "TypingSpeedMode",
    "SPEED_MODE_CPS_MAP",
    "TypingSimulator",
    "VERIFIED_TERMINAL_RECEIPTS",
    "TerminalReplayExecutor",
    "CHECKPOINT_CODE_MAP",
    "CheckpointCodeResolver",
    "ReplayStepRecord",
    "ReplayTrace",
    "DeterministicReplayEngine",
]
