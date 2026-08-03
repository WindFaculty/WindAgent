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


class FlowGenerationSpecificationId(OpaqueId):
    """Identifier for a FlowGenerationSpecification (Phase 11)."""


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
    "FlowGenerationSpecificationId",
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
]
