"""
WindAgent Code Video Workflow Package.

Provides intermediate representation contracts, deterministic timeline models,
and workflow step definitions for automated code tutorial video production.
"""

from __future__ import annotations

from windagent_workflows.code_video.contracts import (
    FORBIDDEN_AUDIO_KEYS,
    FORBIDDEN_COORDINATE_KEYS,
    Action,
    ActionType,
    Annotation,
    CodeVideoPlan,
    ExpectedState,
    OutputPolicy,
    Resolution,
    Scene,
    VisualMode,
)
from windagent_workflows.code_video.definition import (
    CODE_VIDEO_STEPS,
    STEP_APPROVAL_GATES,
    STEP_EXPECTED_EVENTS,
    STEP_EXTERNAL_COST,
    STEP_MAX_ATTEMPTS,
    STEP_OUTPUT_ARTIFACTS,
    STEP_RETRY_CLASS,
    STEP_VERSIONS,
    all_step_contracts,
    build_code_video_step_nodes,
    step_contract,
)
from windagent_core.contracts.code_video.replay import (
    TypingSpeedMode,
    SPEED_MODE_CPS_MAP,
    ReplayStepRecord,
    ReplayTrace,
    CheckpointDefinition,
)


__all__ = [
    # Contracts
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
    # Workflow Definition
    "CODE_VIDEO_STEPS",
    "STEP_APPROVAL_GATES",
    "STEP_VERSIONS",
    "STEP_RETRY_CLASS",
    "STEP_EXTERNAL_COST",
    "STEP_OUTPUT_ARTIFACTS",
    "STEP_EXPECTED_EVENTS",
    "STEP_MAX_ATTEMPTS",
    "build_code_video_step_nodes",
    "step_contract",
    "all_step_contracts",
    # Replay data types (canonical in core)
    "TypingSpeedMode",
    "SPEED_MODE_CPS_MAP",
    "ReplayStepRecord",
    "ReplayTrace",
    "CheckpointDefinition",
]
