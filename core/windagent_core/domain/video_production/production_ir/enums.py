"""
VP3D Phase 1 — Production IR enums.

All enums here describe ENGINE-NEUTRAL cinematic / production concepts. None of
them name a provider, a legacy generative-video mode, a browser
runtime, Blender, Unreal, or any engine SDK. The engine adapter maps these
intents onto its own execution path.
"""

from __future__ import annotations

from enum import Enum


class IrAssetFormat(str, Enum):
    """Interchange formats referenced by the Production IR.

    `.blend` is ALWAYS a derived artifact (never a source of truth). glTF is
    the preferred asset interchange; FBX covers skeletal/animation compat;
    USD is the long-term Blender <-> Unreal interchange.
    """

    GLTF = "GLTF"
    FBX = "FBX"
    USD = "USD"
    BLEND = "BLEND"
    PNG = "PNG"
    EXR = "EXR"
    WAV = "WAV"
    MP4 = "MP4"
    JSON = "JSON"
    UNKNOWN = "UNKNOWN"


class DerivedArtifactKind(str, Enum):
    """Kinds of artifacts an engine adapter publishes from the IR.

    Every derived artifact records the IR content hash it was built from so a
    track change invalidates exactly the dependent outputs.
    """

    SCENE_BLEND = "SCENE_BLEND"
    FRAME_SEQUENCE = "FRAME_SEQUENCE"
    RENDERED_CLIP = "RENDERED_CLIP"
    MIXED_AUDIO = "MIXED_AUDIO"
    FACIAL_RENDER = "FACIAL_RENDER"
    FINAL_CUT = "FINAL_CUT"
    THUMBNAIL = "THUMBNAIL"


class EngineJobStatus(str, Enum):
    """Lifecycle of a job submitted through ProductionEnginePort."""

    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class IrComponentKind(str, Enum):
    """Typed component of a ProductionIrDocument for track-scoped invalidation.

    A change to one component must invalidate exactly the dependent scenes /
    shots / outputs (plan §4 backlog item 7): e.g. dialogue change invalidates
    audio/facial/final cut; camera change invalidates scene compile + render.
    """

    DIALOGUE = "DIALOGUE"
    CAMERA = "CAMERA"
    ANIMATION = "ANIMATION"
    FACIAL = "FACIAL"
    LIGHTING = "LIGHTING"
    SIMULATION = "SIMULATION"
    SCENE_STRUCTURE = "SCENE_STRUCTURE"
    ASSET_REFERENCE = "ASSET_REFERENCE"
    RENDER_PROFILE = "RENDER_PROFILE"
    DURATION = "DURATION"


class IrInvalidationScope(str, Enum):
    """Downstream invalidation scope of an IR component change (plan §4.7).

    - AUDIO_AND_FACIAL_AND_CUT: dialogue/facial change -> audio mix, facial
      render and the final cut (never the baked scene/geometry).
    - SCENE_COMPILE_AND_RENDER: scene structure / camera / lighting / asset /
      duration change -> recompile the scene and re-render dependent shots.
    - RENDER_ONLY: render-profile change -> re-render, no scene recompile.
    - DEPENDENT_RENDER: animation/simulation change -> re-render dependent
      shots (and their continuity dependents).
    - NONE: no downstream output is invalidated.
    """

    NONE = "NONE"
    AUDIO_AND_FACIAL_AND_CUT = "AUDIO_AND_FACIAL_AND_CUT"
    SCENE_COMPILE_AND_RENDER = "SCENE_COMPILE_AND_RENDER"
    RENDER_ONLY = "RENDER_ONLY"
    DEPENDENT_RENDER = "DEPENDENT_RENDER"


class LipSyncSource(str, Enum):
    """Source used to drive facial lip-sync in the IR (engine-neutral)."""

    AUDIO_ASSET = "AUDIO_ASSET"
    WORD_TIMESTAMPS = "WORD_TIMESTAMPS"
    NONE = "NONE"


class SimulationKind(str, Enum):
    """Engine-neutral simulation track kinds."""

    CLOTH = "CLOTH"
    HAIR = "HAIR"
    FLUID = "FLUID"
    PARTICLES = "PARTICLES"
    SOFT_BODY = "SOFT_BODY"
    RIGID_BODY = "RIGID_BODY"


class RenderQuality(str, Enum):
    """Engine-neutral render quality ladder; the adapter maps to its engine."""

    DRAFT = "DRAFT"
    PREVIEW = "PREVIEW"
    HIGH = "HIGH"
    FINAL = "FINAL"


class IrValidationIssueCode(str, Enum):
    """Typed findings from ProductionIrValidator (fail-closed rules)."""

    DUPLICATE_SCENE_ID = "DUPLICATE_SCENE_ID"
    DUPLICATE_SHOT_ID = "DUPLICATE_SHOT_ID"
    DUPLICATE_INSTANCE_ID = "DUPLICATE_INSTANCE_ID"
    DUPLICATE_TRACK_ID = "DUPLICATE_TRACK_ID"
    DUPLICATE_PROFILE_ID = "DUPLICATE_PROFILE_ID"
    BROKEN_REFERENCE = "BROKEN_REFERENCE"
    BLEND_MUST_BE_DERIVED = "BLEND_MUST_BE_DERIVED"
    MISSING_CAMERA = "MISSING_CAMERA"
    DURATION_MISMATCH = "DURATION_MISMATCH"
    UNKNOWN_COMPONENT_KIND = "UNKNOWN_COMPONENT_KIND"


__all__ = [
    "IrAssetFormat",
    "DerivedArtifactKind",
    "EngineJobStatus",
    "IrComponentKind",
    "IrInvalidationScope",
    "LipSyncSource",
    "SimulationKind",
    "RenderQuality",
    "IrValidationIssueCode",
]
