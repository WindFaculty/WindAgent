"""
VP3D Phase 1 — Canonical Production IR (engine-neutral).

The IR describes cinematic intent (actors/action/camera/duration/dialogue/
assets) without any provider, generation-mode, browser, Blender or Unreal
concept. Engine adapters (Blender, Unreal, ...) compile the IR onto their own
execution path; `.blend` is always a derived artifact.

Public surface:

- models: ProductionIrDocument, ShotExecutionIntent, SceneDescription,
  CharacterInstance/PropInstance/EnvironmentInstance, CameraTrack/
  AnimationTrack/FacialTrack/DialogueTrack, LightRig, SimulationTrack,
  RenderProfile, RenderIntent, EngineJobReceipt, DerivedArtifact;
- enums: IrAssetFormat, DerivedArtifactKind, EngineJobStatus, IrComponentKind,
  IrInvalidationScope, LipSyncSource, SimulationKind, RenderQuality,
  IrValidationIssueCode;
- validation: ProductionIrValidator (fail-closed);
- invalidation: invalidate_scope / affected_outputs (track-scoped);
- migrator: ProductionIrMigrator (bounded legacy compatibility reader).

Note: `DialogueTrack` here is the IR value object (per-shot dialogue binding).
It deliberately lives ONLY in the `production_ir` namespace because the domain
package root already exports the Phase 21 audio `DialogueTrack` entity.
"""

from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    EngineJobStatus,
    IrAssetFormat,
    IrComponentKind,
    IrInvalidationScope,
    IrValidationIssueCode,
    LipSyncSource,
    RenderQuality,
    SimulationKind,
)
from windagent_core.domain.video_production.production_ir.invalidation import (
    IR_COMPONENT_INVALIDATION,
    affected_outputs,
    invalidate_scope,
)
from windagent_core.domain.video_production.production_ir.models import (
    PRODUCTION_IR_VERSION,
    SUPPORTED_IR_MAJOR_VERSION,
    DEFAULT_RENDER_PROFILE_ID,
    AnimationTrack,
    AssetReference,
    CameraTrack,
    CharacterInstance,
    DerivedArtifact,
    DialogueTrack,
    EngineJobReceipt,
    EnvironmentInstance,
    FacialTrack,
    LightRig,
    ProductionIrDocument,
    PropInstance,
    RenderIntent,
    RenderProfile,
    SceneDescription,
    ShotExecutionIntent,
    SimulationTrack,
    utc_now,
)
from windagent_core.domain.video_production.production_ir.validation import (
    IrValidationIssue,
    ProductionIrValidator,
    ensure_valid_document,
)
from windagent_core.domain.video_production.production_ir.migrator import (
    ProductionIrMigrator,
)

__all__ = [
    # version
    "PRODUCTION_IR_VERSION",
    "SUPPORTED_IR_MAJOR_VERSION",
    "DEFAULT_RENDER_PROFILE_ID",
    # models
    "utc_now",
    "AssetReference",
    "CharacterInstance",
    "PropInstance",
    "EnvironmentInstance",
    "CameraTrack",
    "AnimationTrack",
    "FacialTrack",
    "DialogueTrack",
    "LightRig",
    "SimulationTrack",
    "RenderProfile",
    "RenderIntent",
    "SceneDescription",
    "ShotExecutionIntent",
    "ProductionIrDocument",
    "EngineJobReceipt",
    "DerivedArtifact",
    # enums
    "IrAssetFormat",
    "DerivedArtifactKind",
    "EngineJobStatus",
    "IrComponentKind",
    "IrInvalidationScope",
    "LipSyncSource",
    "SimulationKind",
    "RenderQuality",
    "IrValidationIssueCode",
    # validation
    "IrValidationIssue",
    "ProductionIrValidator",
    "ensure_valid_document",
    # invalidation
    "IR_COMPONENT_INVALIDATION",
    "invalidate_scope",
    "affected_outputs",
    # migrator
    "ProductionIrMigrator",
]
