"""
Stable, opaque identifiers for the WindAgent Video Production domain (Phase 3).

Every identifier is an opaque stable string that is NEVER derived from a display
name, title, or user input. Deleted or renamed entities never reuse an old ID.
All IDs are backed by the canonical ``OpaqueId`` value object and carry a
namespace prefix (e.g. ``vp_`` for project, ``rev_`` for revision).
"""

from __future__ import annotations

from windagent_core.domain.types import OpaqueId


class VideoProjectId(OpaqueId):
    """Identifier for a VideoProject aggregate."""


class ProductionRevisionId(OpaqueId):
    """Identifier for an immutable ProductionRevision."""


class CreativeBriefId(OpaqueId):
    """Identifier for a CreativeBrief aggregate."""


class StoryConceptId(OpaqueId):
    """Identifier for a StoryConcept aggregate."""


class ScreenplayId(OpaqueId):
    """Identifier for a Screenplay aggregate."""


class SceneId(OpaqueId):
    """Identifier for a Scene entity."""


class CharacterId(OpaqueId):
    """Identifier for a CharacterBible entity."""


class LocationId(OpaqueId):
    """Identifier for a LocationBible entity."""


class PropId(OpaqueId):
    """Identifier for a PropBible entity."""


class StyleBibleId(OpaqueId):
    """Identifier for a StyleBible aggregate."""


class DialogueLineId(OpaqueId):
    """Identifier for a DialogueLine entity."""


class CinematicPlanId(OpaqueId):
    """Identifier for a CinematicPlan aggregate."""


class ShotId(OpaqueId):
    """Identifier for a Shot entity."""


class ShotDependencyId(OpaqueId):
    """Identifier for a ShotDependency edge."""


class ContinuityStateId(OpaqueId):
    """Identifier for a ContinuityState aggregate."""


class ReferenceAssetId(OpaqueId):
    """Identifier for a content-addressed ReferenceAsset."""


class GenerationRequestId(OpaqueId):
    """Identifier for a GenerationRequest (idempotency key holder)."""


class GenerationCandidateId(OpaqueId):
    """Identifier for a GenerationCandidate result."""


class ReviewResultId(OpaqueId):
    """Identifier for a ReviewResult aggregate."""


class ApprovalId(OpaqueId):
    """Identifier for an ApprovalDecision record."""


class FinalDeliverableId(OpaqueId):
    """Identifier for the final published deliverable."""


class DirectorialIssueId(OpaqueId):
    """Identifier for a DirectorialIssue (Phase 8)."""


class ScriptRevisionProposalId(OpaqueId):
    """Identifier for a ScriptRevisionProposal (Phase 8)."""


class ShotGraphIssueId(OpaqueId):
    """Identifier for a ShotGraphIssue (Phase 9)."""


class ShotSpecificationId(OpaqueId):
    """Identifier for a ShotSpecification (Phase 9)."""


class ContinuityLedgerId(OpaqueId):
    """Identifier for a ContinuityLedger aggregate (Phase 10)."""


class ContinuityIssueId(OpaqueId):
    """Identifier for a ContinuityIssue finding (Phase 10)."""


class ContinuityOverrideId(OpaqueId):
    """Identifier for a HumanContinuityOverride audit record (Phase 10)."""


class ReferenceBindingId(OpaqueId):
    """Identifier for a ReferenceBinding edge (Phase 11)."""


class ReferenceBindingPlanId(OpaqueId):
    """Identifier for a ReferenceBindingPlan aggregate (Phase 11)."""


class ReferenceBindingIssueId(OpaqueId):
    """Identifier for a ReferenceBindingIssue finding (Phase 11)."""


class PromptBlockId(OpaqueId):
    """Identifier for a PromptBlock in a compiled prompt (Phase 11)."""


class CompiledPromptId(OpaqueId):
    """Identifier for a CompiledPrompt aggregate (Phase 11)."""


class PromptCompilerIssueId(OpaqueId):
    """Identifier for a PromptCompilerIssue finding (Phase 11)."""


class PromptSecurityFindingId(OpaqueId):
    """Identifier for a PromptSecurityFinding (Phase 11)."""


class CharacterVoiceProfileId(OpaqueId):
    """Identifier for a CharacterVoiceProfile (Phase 21)."""


class DialogueTrackId(OpaqueId):
    """Identifier for a DialogueTrack (Phase 21)."""


class WordTimestampId(OpaqueId):
    """Identifier for a WordTimestamp (Phase 21)."""


class SoundEffectCueId(OpaqueId):
    """Identifier for a SoundEffectCue (Phase 21)."""


class MusicCueId(OpaqueId):
    """Identifier for a MusicCue (Phase 21)."""


class AudioMixPlanId(OpaqueId):
    """Identifier for an AudioMixPlan aggregate (Phase 21)."""


class TtsRequestId(OpaqueId):
    """Identifier for a TTS synthesis request (Phase 21)."""


class TtsAudioAssetId(OpaqueId):
    """Identifier for a TTS output audio asset (Phase 21)."""


class EditDecisionListId(OpaqueId):
    """Identifier for an EditDecisionList aggregate (Phase 22)."""


class TransitionPlanId(OpaqueId):
    """Identifier for a TransitionPlan entity (Phase 22)."""


class SubtitleTrackId(OpaqueId):
    """Identifier for a SubtitleTrack aggregate (Phase 22)."""


class SubtitleCueId(OpaqueId):
    """Identifier for a SubtitleCue entity (Phase 22)."""


class EncodingProfileId(OpaqueId):
    """Identifier for an EncodingProfile value object (Phase 22)."""


class PostProductionJobId(OpaqueId):
    """Identifier for a PostProductionJob aggregate (Phase 22)."""


class FrameSequenceId(OpaqueId):
    """Identifier for a rendered frame sequence input (VP3D Phase 24)."""


# ---------------------------------------------------------------------------
# Production IR (VP3D Phase 1 — engine-neutral intermediate representation)
# ---------------------------------------------------------------------------
class ProductionIrId(OpaqueId):
    """Identifier for a ProductionIrDocument aggregate (VP3D Phase 1)."""


class SceneDescriptionId(OpaqueId):
    """Identifier for a SceneDescription in the Production IR."""


class CharacterInstanceId(OpaqueId):
    """Identifier for a CharacterInstance in the Production IR."""


class PropInstanceId(OpaqueId):
    """Identifier for a PropInstance in the Production IR."""


class EnvironmentInstanceId(OpaqueId):
    """Identifier for an EnvironmentInstance in the Production IR."""


class CameraTrackId(OpaqueId):
    """Identifier for a CameraTrack in the Production IR."""


class AnimationTrackId(OpaqueId):
    """Identifier for an AnimationTrack in the Production IR."""


class LightRigId(OpaqueId):
    """Identifier for a LightRig in the Production IR."""


class SimulationTrackId(OpaqueId):
    """Identifier for a SimulationTrack in the Production IR."""


class RenderProfileId(OpaqueId):
    """Identifier for a RenderProfile in the Production IR."""


class RenderIntentId(OpaqueId):
    """Identifier for a RenderIntent in the Production IR."""


class ShotExecutionIntentId(OpaqueId):
    """Identifier for a ShotExecutionIntent in the Production IR."""


class EngineJobId(OpaqueId):
    """Identifier for an engine job submitted through ProductionEnginePort."""


class DerivedArtifactId(OpaqueId):
    """Identifier for a derived artifact published by an engine adapter."""


class AssetCandidateId(OpaqueId):
    """Identifier for a DISCOVERED asset candidate (VP3D Phase 5)."""


class AssetResolutionId(OpaqueId):
    """Identifier for one Universal Asset Gateway resolution (VP3D Phase 5)."""


class NormalizationRunId(OpaqueId):
    """Identifier for one asset normalization run (VP3D Phase 7)."""


# ---------------------------------------------------------------------------
# Stage D Character System (VP3D Phase 8 — Character Master Asset)
# ---------------------------------------------------------------------------
class CharacterMasterId(OpaqueId):
    """Stable identifier for a CharacterMaster aggregate (VP3D Phase 8)."""


class CharacterMasterRevisionId(OpaqueId):
    """Identifier for one immutable CharacterMasterRevision (VP3D Phase 8)."""


class CharacterGeometryProfileId(OpaqueId):
    """Identifier for a canonical mesh CharacterGeometryProfile (VP3D Phase 8)."""


class CharacterMaterialProfileId(OpaqueId):
    """Identifier for a materials/textures CharacterMaterialProfile (VP3D Phase 8)."""


class CharacterProportionProfileId(OpaqueId):
    """Identifier for a CharacterProportionProfile (VP3D Phase 8)."""


class FacialRigProfileId(OpaqueId):
    """Identifier for a FacialRigProfile (VP3D Phase 8)."""


class AnimationProfileId(OpaqueId):
    """Identifier for an approved AnimationProfile (VP3D Phase 8)."""


class StyleFingerprintId(OpaqueId):
    """Identifier for a StyleFingerprint (VP3D Phase 8)."""


# ---------------------------------------------------------------------------
# Stage D Rigging & Retargeting (VP3D Phase 9 — Rigging & Retargeting)
# ---------------------------------------------------------------------------
class SkeletonProfileId(OpaqueId):
    """Identifier for a detected/normalized SkeletonProfile (VP3D Phase 9)."""


class RigProfileId(OpaqueId):
    """Identifier for a validated RigProfile (VP3D Phase 9)."""


class RigValidationReceiptId(OpaqueId):
    """Identifier for a RigValidationReceipt (VP3D Phase 9)."""


class RetargetProfileId(OpaqueId):
    """Identifier for a versioned RetargetProfile mapping (VP3D Phase 9)."""


class AnimationCompatibilityProfileId(OpaqueId):
    """Identifier for a per-clip AnimationCompatibilityProfile (VP3D Phase 9)."""


# ---------------------------------------------------------------------------
# Stage E Concurrent Audio (VP3D Phase 10 — Concurrent Audio Production)
# ---------------------------------------------------------------------------
class TtsProviderId(OpaqueId):
    """Identifier for a registered TTS provider/engine (VP3D Phase 10)."""


class AudioSynthesisRunId(OpaqueId):
    """Identifier for one TTS synthesis run (per line, idempotent, Phase 10)."""


class AudioValidationReceiptId(OpaqueId):
    """Identifier for a TTS output validation receipt (VP3D Phase 10)."""


class ForcedAlignRunId(OpaqueId):
    """Identifier for one forced-alignment run (VP3D Phase 10)."""


class AlignmentReceiptId(OpaqueId):
    """Identifier for an alignment receipt with word/phoneme timestamps (Phase 10)."""


class LineTimingResolutionId(OpaqueId):
    """Identifier for a resolution of an overlong line (VP3D Phase 10)."""


class AudioNodeExecutionId(OpaqueId):
    """Identifier for one audio DAG node execution record (VP3D Phase 10)."""


class AudioConcurrencyStateId(OpaqueId):
    """Identifier for a persisted audio DAG concurrency state (VP3D Phase 10)."""


# ---------------------------------------------------------------------------
# Stage F Set Dressing (VP3D Phase 12 — Environment & Set Dressing)
# ---------------------------------------------------------------------------
class SetDressingSceneId(OpaqueId):
    """Identifier for a compiled set-dressing scene plan (VP3D Phase 12)."""


class SpatialFindingId(OpaqueId):
    """Identifier for one spatial/constraint finding (VP3D Phase 12)."""


# ---------------------------------------------------------------------------
# Stage G Cinematography (VP3D Phase 13 — Blender Camera Compiler)
# ---------------------------------------------------------------------------
class CameraIntentId(OpaqueId):
    """Identifier for one shot's CameraIntent (VP3D Phase 13)."""


class CameraRigPlanId(OpaqueId):
    """Identifier for a compiled CameraRigPlan (VP3D Phase 13)."""


class CameraFindingId(OpaqueId):
    """Identifier for one camera validation/occlusion finding (VP3D Phase 13)."""


class CameraOverrideId(OpaqueId):
    """Identifier for a manual camera override pinning a track revision (Phase 13)."""


class CameraPathManifestId(OpaqueId):
    """Identifier for a camera path / playblast manifest (VP3D Phase 13)."""


# ---------------------------------------------------------------------------
# Stage G Cinematography (VP3D Phase 14 — Lighting System)
# ---------------------------------------------------------------------------
class LightingIntentId(OpaqueId):
    """Identifier for one shot's LightingIntent (VP3D Phase 14)."""


class LightRigPlanId(OpaqueId):
    """Identifier for a compiled LightRigPlan (VP3D Phase 14)."""


class LightingFindingId(OpaqueId):
    """Identifier for one lighting validation finding (VP3D Phase 14)."""


class LightOverrideId(OpaqueId):
    """Identifier for a bounded lighting override (VP3D Phase 14)."""


class LightingContactSheetId(OpaqueId):
    """Identifier for a lighting contact sheet / histogram manifest (Phase 14)."""


# ---------------------------------------------------------------------------
# Stage H Animation (VP3D Phase 15 — Animation Layer V1: Library + Mocap)
# ---------------------------------------------------------------------------
class AnimationIntentId(OpaqueId):
    """Identifier for one AnimationIntent (VP3D Phase 15)."""


class AnimationClipId(OpaqueId):
    """Identifier for one versioned clip in the animation library (VP3D Phase 15)."""


class AnimationFindingId(OpaqueId):
    """Identifier for an animation validation finding (VP3D Phase 15)."""


class RetargetReceiptId(OpaqueId):
    """Identifier for a clip retarget receipt (VP3D Phase 15)."""


class EpisodePinId(OpaqueId):
    """Identifier for an episode clip-revision pin (VP3D Phase 15)."""


class BlendTransitionId(OpaqueId):
    """Identifier for a blend transition between tracks (VP3D Phase 15)."""


# ---------------------------------------------------------------------------
# Stage H Procedural Animation (VP3D Phase 16)
# ---------------------------------------------------------------------------
class ProceduralRecipeId(OpaqueId):
    """Identifier for a procedural layer recipe (VP3D Phase 16)."""


class ProceduralLayerId(OpaqueId):
    """Identifier for one procedural layer spec (VP3D Phase 16)."""


class ProceduralFindingId(OpaqueId):
    """Identifier for a procedural validation finding (VP3D Phase 16)."""


class BakedActionId(OpaqueId):
    """Identifier for a baked derived action (VP3D Phase 16)."""


# ---------------------------------------------------------------------------
# Stage H AI Motion Adapter (VP3D Phase 17)
# ---------------------------------------------------------------------------
class MotionCapabilityId(OpaqueId):
    """Identifier for an AI motion provider capability contract (Phase 17)."""


class MotionRequestId(OpaqueId):
    """Identifier for one AI motion generation request (VP3D Phase 17)."""


class RawMotionArtifactId(OpaqueId):
    """Identifier for a quarantined raw AI motion artifact (VP3D Phase 17)."""


class MotionCandidateId(OpaqueId):
    """Identifier for one AI motion candidate (VP3D Phase 17)."""


class MotionFindingId(OpaqueId):
    """Identifier for an AI motion validation finding (VP3D Phase 17)."""


class SkeletonRemapReceiptId(OpaqueId):
    """Identifier for a skeleton remap receipt (VP3D Phase 17)."""


# ---------------------------------------------------------------------------
# Stage I Facial Animation (VP3D Phase 18 — Lip-sync / Facial Pipeline)
# ---------------------------------------------------------------------------
class PhonemeTrackId(OpaqueId):
    """Identifier for a normalized phoneme track (VP3D Phase 18)."""


class VisemeMapId(OpaqueId):
    """Identifier for a versioned viseme map (VP3D Phase 18)."""


class EmotionCurveId(OpaqueId):
    """Identifier for one emotion curve (VP3D Phase 18)."""


class BlinkTrackId(OpaqueId):
    """Identifier for a blink track (VP3D Phase 18)."""


class GazeTrackId(OpaqueId):
    """Identifier for a gaze/eye-target track (VP3D Phase 18)."""


class FacialTrackId(OpaqueId):
    """Identifier for a facial track — Production IR intent and the compiled
    FacialAnimationTrack (VP3D Phase 18) share this canonical id type."""


class FacialFindingId(OpaqueId):
    """Identifier for one facial validation finding (VP3D Phase 18)."""


class FacialValidationReceiptId(OpaqueId):
    """Identifier for a facial validation receipt (VP3D Phase 18)."""


class BakedFacialActionId(OpaqueId):
    """Identifier for a baked derived facial action (VP3D Phase 18)."""


class FacialRepairReceiptId(OpaqueId):
    """Identifier for a facial repair receipt (VP3D Phase 18)."""


# ---------------------------------------------------------------------------
# Stage F Scene Construction (VP3D Phase 11 — Scene Compiler)
# ---------------------------------------------------------------------------
class BlenderScenePlanId(OpaqueId):
    """Identifier for a compiled BlenderScenePlan (VP3D Phase 11)."""


class BlendInspectionReceiptId(OpaqueId):
    """Identifier for a save/reopen/publish inspection receipt (VP3D Phase 11)."""


class IrMappingManifestId(OpaqueId):
    """Identifier for an IR-entity -> data-block mapping manifest (Phase 11)."""


class ScenePlanIssueId(OpaqueId):
    """Identifier for a scene-plan validation / inspection issue (Phase 11)."""


# ---------------------------------------------------------------------------
# Stage M End-to-End (VP3D Phase 25 — Golden Scene)
# ---------------------------------------------------------------------------
class GoldenSceneRunId(OpaqueId):
    """Identifier for one golden scene E2E production run (VP3D Phase 25)."""


class GoldenSceneNodeId(OpaqueId):
    """Identifier for one pipeline node execution receipt (VP3D Phase 25)."""


class GoldenSceneArtifactId(OpaqueId):
    """Identifier for an artifact produced by a golden scene node (Phase 25)."""


# ---------------------------------------------------------------------------
# Stage M End-to-End (VP3D Phase 26 — Multi-Scene Episode)
# ---------------------------------------------------------------------------
class EpisodeRunId(OpaqueId):
    """Identifier for one multi-scene episode production run (VP3D Phase 26)."""


class EpisodeSceneId(OpaqueId):
    """Identifier for one episode scene (VP3D Phase 26)."""


class EpisodeShotId(OpaqueId):
    """Identifier for one episode shot (VP3D Phase 26)."""


class EpisodeArtifactId(OpaqueId):
    """Identifier for an artifact produced/reused by an episode run (Phase 26)."""


class EpisodeChunkId(OpaqueId):
    """Identifier for one render frame chunk (VP3D Phase 26)."""


class EpisodeBranchId(OpaqueId):
    """Identifier for one parallel branch of the episode schedule (Phase 26)."""


__all__ = [
    "VideoProjectId",
    "ProductionRevisionId",
    "CreativeBriefId",
    "StoryConceptId",
    "ScreenplayId",
    "SceneId",
    "CharacterId",
    "LocationId",
    "PropId",
    "StyleBibleId",
    "DialogueLineId",
    "CinematicPlanId",
    "ShotId",
    "ShotDependencyId",
    "ContinuityStateId",
    "ReferenceAssetId",
    "GenerationRequestId",
    "GenerationCandidateId",
    "ReviewResultId",
    "ApprovalId",
    "FinalDeliverableId",
    "DirectorialIssueId",
    "ScriptRevisionProposalId",
    "ShotGraphIssueId",
    "ShotSpecificationId",
    "ContinuityLedgerId",
    "ContinuityIssueId",
    "ContinuityOverrideId",
    "ReferenceBindingId",
    "ReferenceBindingPlanId",
    "ReferenceBindingIssueId",
    "PromptBlockId",
    "CompiledPromptId",

    "PromptCompilerIssueId",
    "PromptSecurityFindingId",
    "CharacterVoiceProfileId",
    "DialogueTrackId",
    "WordTimestampId",
    "SoundEffectCueId",
    "MusicCueId",
    "AudioMixPlanId",
    "TtsRequestId",
    "TtsAudioAssetId",
    "EditDecisionListId",
    "TransitionPlanId",
    "SubtitleTrackId",
    "SubtitleCueId",
    "EncodingProfileId",
    "PostProductionJobId",
    "FrameSequenceId",
    "ProductionIrId",
    "SceneDescriptionId",
    "CharacterInstanceId",
    "PropInstanceId",
    "EnvironmentInstanceId",
    "CameraTrackId",
    "AnimationTrackId",
    "FacialTrackId",
    "LightRigId",
    "SimulationTrackId",
    "RenderProfileId",
    "RenderIntentId",
    "ShotExecutionIntentId",
    "EngineJobId",
    "DerivedArtifactId",
    "AssetCandidateId",
    "AssetResolutionId",
    "NormalizationRunId",
    "CharacterMasterId",
    "CharacterMasterRevisionId",
    "CharacterGeometryProfileId",
    "CharacterMaterialProfileId",
    "CharacterProportionProfileId",
    "FacialRigProfileId",
    "AnimationProfileId",
    "StyleFingerprintId",
    "SkeletonProfileId",
    "RigProfileId",
    "RigValidationReceiptId",
    "RetargetProfileId",
    "AnimationCompatibilityProfileId",
    "TtsProviderId",
    "AudioSynthesisRunId",
    "AudioValidationReceiptId",
    "ForcedAlignRunId",
    "AlignmentReceiptId",
    "LineTimingResolutionId",
    "AudioNodeExecutionId",
    "AudioConcurrencyStateId",
    "SetDressingSceneId",
    "SpatialFindingId",
    "BlenderScenePlanId",
    "BlendInspectionReceiptId",
    "IrMappingManifestId",
    "ScenePlanIssueId",
    "GoldenSceneRunId",
    "GoldenSceneNodeId",
    "GoldenSceneArtifactId",
    "EpisodeRunId",
    "EpisodeSceneId",
    "EpisodeShotId",
    "EpisodeArtifactId",
    "EpisodeChunkId",
    "EpisodeBranchId",
    "CameraIntentId",
    "CameraRigPlanId",
    "CameraFindingId",
    "CameraOverrideId",
    "CameraPathManifestId",
    "LightingIntentId",
    "LightRigPlanId",
    "LightingFindingId",
    "LightOverrideId",
    "LightingContactSheetId",
    # Stage H Animation (VP3D Phase 15)
    "AnimationIntentId",
    "AnimationClipId",
    "AnimationFindingId",
    "RetargetReceiptId",
    "EpisodePinId",
    "BlendTransitionId",
    # Stage H Procedural Animation (VP3D Phase 16)
    "ProceduralRecipeId",
    "ProceduralLayerId",
    "ProceduralFindingId",
    "BakedActionId",
    # Stage H AI Motion Adapter (VP3D Phase 17)
    "MotionCapabilityId",
    "MotionRequestId",
    "RawMotionArtifactId",
    "MotionCandidateId",
    "MotionFindingId",
    "SkeletonRemapReceiptId",
    # Stage I Facial Animation (VP3D Phase 18)
    "PhonemeTrackId",
    "VisemeMapId",
    "EmotionCurveId",
    "BlinkTrackId",
    "GazeTrackId",
    "FacialTrackId",
    "FacialFindingId",
    "FacialValidationReceiptId",
    "BakedFacialActionId",
    "FacialRepairReceiptId",
]
