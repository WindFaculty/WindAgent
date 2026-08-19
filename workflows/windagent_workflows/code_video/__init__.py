"""
WindAgent Code Video Workflow Package.

Provides intermediate representation contracts, deterministic timeline models,
and workflow step definitions for automated code tutorial video production.
"""

from __future__ import annotations

from typing import Any

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
from windagent_workflows.code_video.compiler import CodeVideoScriptCompiler
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
from windagent_workflows.code_video.replay import (
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
def __getattr__(name: str) -> Any:
    if name == "AssembleMasterStepExecutor":
        from windagent_workflows.code_video.assembly import AssembleMasterStepExecutor
        return AssembleMasterStepExecutor
    if name in ("ProgramCertificationDriver", "ProgramCertificationStepExecutor"):
        from windagent_workflows.code_video import program_certification

        return getattr(program_certification, name)
    if name in ("FinalQCDriver", "FinalQCStepExecutor"):
        from windagent_workflows.code_video import qc

        return getattr(qc, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Compiler
    "CodeVideoScriptCompiler",
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
    # Deterministic Replay
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
    # Master Assembly
    "AssembleMasterStepExecutor",
    # Final QC
    "FinalQCStepExecutor",
    "FinalQCDriver",
    # Program Certification (Phase 12)
    "ProgramCertificationStepExecutor",
    "ProgramCertificationDriver",
]
