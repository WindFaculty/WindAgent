"""
Code Video IR contracts — canonical source of truth in core.

All neutral, implementation-free types for code video production:
Scene, Resolution, Action, CodeVideoPlan, assembly types, capture receipts,
replay data, renderer types, and related data contracts.

Consumers (tools, workflows, workers) import from here, NOT from
windagent_tools.code_video or windagent_workflows.code_video.
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

from windagent_core.contracts.code_video.assembly import (
    TransitionType,
    FORBIDDEN_FLASHY_TRANSITIONS,
    TransitionRule,
    TransitionPolicy,
    format_timecode_ms,
    CueSheetEntry,
    CueSheet,
    VideoAssemblyConfig,
    MasterAssemblyResult,
    TakesManifest,
)

from windagent_core.contracts.code_video.capture import (
    CaptureStatus,
    TakeReceipt,
    FrameMetadata,
    FrameReport,
    MediaProbeReport,
)

from windagent_core.contracts.code_video.replay import (
    TypingSpeedMode,
    SPEED_MODE_CPS_MAP,
    ReplayStepRecord,
    ReplayTrace,
    CheckpointDefinition,
)

from windagent_core.contracts.code_video.renderer import (
    SafeInsets,
    TypographyScale,
    StudioColorPalette,
    CodeVideoVisualTheme,
    AssetClassification,
    AssetCategory,
    GraphicTransitionType,
    AnimationType,
    GraphicsCatalogEntry,
)

__all__ = [
    # Models (existing)
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
    # Assembly types
    "TransitionType",
    "FORBIDDEN_FLASHY_TRANSITIONS",
    "TransitionRule",
    "TransitionPolicy",
    "format_timecode_ms",
    "CueSheetEntry",
    "CueSheet",
    "VideoAssemblyConfig",
    "MasterAssemblyResult",
    "TakesManifest",
    # Capture types
    "CaptureStatus",
    "TakeReceipt",
    "FrameMetadata",
    "FrameReport",
    "MediaProbeReport",
    # Replay types
    "TypingSpeedMode",
    "SPEED_MODE_CPS_MAP",
    "ReplayStepRecord",
    "ReplayTrace",
    "CheckpointDefinition",
    # Renderer types
    "SafeInsets",
    "TypographyScale",
    "StudioColorPalette",
    "CodeVideoVisualTheme",
    "AssetClassification",
    "AssetCategory",
    "GraphicTransitionType",
    "AnimationType",
    "GraphicsCatalogEntry",
]
