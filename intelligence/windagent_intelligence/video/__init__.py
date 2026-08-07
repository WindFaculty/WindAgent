"""
WindAgent Video Pre-production Kernel (Phase 6).

Canonical, provider-neutral reimplementation of the pre-production
capabilities that were characterized in Phase 5
(VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED). Nine vertical slices:

1. ideation.brief_expander      — creative brief / idea expansion
2. ideation.outliner            — story outline
3. screenplay.writer            — multi-scene screenplay
4. screenplay.narration         — dialogue and narration
5. entity_extraction.extractor  — character/location/prop extraction
6. style_design.designer        — style bible
7. continuation.service         — plot continuation and revision proposal
8. asset_prompts.builder        — asset prompt specification
9. assembly.assembler           — assemble VideoProductionPackage v1

Design rules (plan 02 §14-18, §16):
- Zero runtime import from third_party/videoclaw/upstream.
- Provider-neutral: every model-backed capability goes through the
  `PreproductionModelPort` protocol; prompts are versioned and hashed
  (`PromptSpec`); model ID / temperature / token limits are config.
- Provider responses are parsed and validated BEFORE entering the domain;
  broken/empty responses raise typed kernel errors (fixes DEF-001, DEF-002,
  DEF-005 from artifacts/video_production/phase_05/defect_inventory.json).
- Identity is bound via stable canonical IDs, never merged on display name
  (fixes DEF-003). Version listing is deterministic (fixes DEF-004).
- Capabilities never write project/session DB, never lock a screenplay,
  never approve assets, and never call video generation.
"""

from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    ModelCompletionResult,
    PreproductionModelPort,
)
from windagent_intelligence.video.prompts import PromptSpec
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.errors import (
    VideoKernelError,
    ResponseParseError,
    EmptyResponseError,
    MissingModelConfigError,
    ValidationFailureError,
    CancellationError,
)

# Capability services
from windagent_intelligence.video.ideation.brief_expander import CreativeBriefExpander
from windagent_intelligence.video.ideation.outliner import StoryOutliner
from windagent_intelligence.video.screenplay.writer import ScreenplayWriter
from windagent_intelligence.video.screenplay.narration import DialogueNarrator
from windagent_intelligence.video.entity_extraction.extractor import EntityExtractor
from windagent_intelligence.video.style_design.designer import StyleDesigner
from windagent_intelligence.video.continuation.service import ContinuationService
from windagent_intelligence.video.asset_prompts.builder import AssetPromptSpecBuilder
from windagent_intelligence.video.assembly.assembler import (
    PackageAssembler,
    PackageAssemblyReceipt,
)

# Director layer (Phase 8)
from windagent_intelligence.video.director import (
    DIRECTOR_PLANNING_PROMPT_V1,
    BeatPlan,
    DirectorPlanReceipt,
    DirectorPlanValidator,
    DurationBudgetPolicy,
    PlannerOutput,
    SceneObjectivePlan,
    ScriptRevisionProposalFactory,
    ShotPlan,
    ValidationResult,
    VideoDirectorService,
)

# Shot graph / camera planning layer (Phase 9)
from windagent_intelligence.video.shot_planner import (
    CameraPlanner,
    ShotGraphBuilder,
    ShotGraphPlannerService,
    ShotGraphReceipt,
    ShotScheduler,
)

# Continuity ledger layer (Phase 10)
from windagent_intelligence.video.continuity import (
    ContinuityLedgerReceipt,
    ContinuityLedgerService,
)

# Reference binding layer (Phase 11)
from windagent_intelligence.video.reference_selector import (
    ReferenceBindingPlanReceipt,
    ReferenceBindingPlanner,
)

# Prompt compiler layer retired in VP3D Stage A — the runtime compiles IR
# (ProductionIrDocument / ShotExecutionIntent) directly; see legacy_v1/SUNSET.md.

# Audio pipeline layer (Phase 21)
from windagent_intelligence.video.audio import (
    ALIGNMENT_VERSION,
    AUDIO_PIPELINE_VERSION,
    AlignmentReceipt,
    AlignmentService,
    AudioIssue,
    AudioPipelineConfig,
    AudioPipelineReceipt,
    AudioPipelineService,
    DIALOGUE_PREP_VERSION,
    DialoguePreparationReceipt,
    DialoguePreparer,
    MIX_VERSION,
    MixPlanner,
    PRONUNCIATION_LEXICON_VERSION,
    TTS_PIPELINE_VERSION,
    TtsProviderPort,
    TtsSynthesisReceipt,
    TtsSynthesisRequest,
    TtsSynthesisResult,
    TtsSynthesizer,
    VOICE_CAST_VERSION,
    VoiceCastReceipt,
    VoiceCastingService,
)

# Candidate review / quality gates layer (Phase 20)
from windagent_intelligence.video.reviewers import (
    BLOCKING_DIMENSIONS,
    BlockingDefect,
    BlockingReasonCode,
    CandidateReview,
    CandidateSelector,
    CandidateVerdict,
    CROSS_SHOT_METRIC_VERSION,
    CrossShotReviewResult,
    CrossShotReviewer,
    DETERMINISTIC_METRIC_VERSION,
    DeterministicReviewResult,
    DeterministicReviewer,
    DimensionConfig,
    DimensionResult,
    HumanSelectionOverride,
    MediaProbeFacts,
    REVIEW_DIMENSIONS,
    REVIEW_POLICY_VERSION,
    RetryProposal,
    ReviewDimension,
    ReviewModelPort,
    ReviewerType,
    SELECTION_ALGORITHM_VERSION,
    SelectionRecord,
    CandidateReviewReceipt,
    ReviewPipeline,
    VLM_METRIC_VERSION,
    VERDICT_POLICY_VERSION,
    VerdictPolicy,
    VlmReviewOutcome,
    VlmReviewRequest,
    VlmReviewResult,
    VlmReviewer,
    config_for,
)

__all__ = [
    # ports
    "ModelCompletionRequest",
    "ModelCompletionResult",
    "PreproductionModelPort",
    # prompts & ids
    "PromptSpec",
    "StableIdFactory",
    # errors
    "VideoKernelError",
    "ResponseParseError",
    "EmptyResponseError",
    "MissingModelConfigError",
    "ValidationFailureError",
    "CancellationError",
    # capability services
    "CreativeBriefExpander",
    "StoryOutliner",
    "ScreenplayWriter",
    "DialogueNarrator",
    "EntityExtractor",
    "StyleDesigner",
    "ContinuationService",
    "AssetPromptSpecBuilder",
    "PackageAssembler",
    "PackageAssemblyReceipt",
    # director layer
    "VideoDirectorService",
    "DirectorPlanValidator",
    "ScriptRevisionProposalFactory",
    "DurationBudgetPolicy",
    "DirectorPlanReceipt",
    "PlannerOutput",
    "SceneObjectivePlan",
    "ShotPlan",
    "BeatPlan",
    "ValidationResult",
    "DIRECTOR_PLANNING_PROMPT_V1",
    # shot graph / camera planning layer
    "ShotGraphPlannerService",
    "ShotGraphReceipt",
    "ShotGraphBuilder",
    "CameraPlanner",
    "ShotScheduler",
    # continuity ledger layer
    "ContinuityLedgerService",
    "ContinuityLedgerReceipt",
    # reference binding layer
    "ReferenceBindingPlanner",
    "ReferenceBindingPlanReceipt",
    # audio pipeline layer (Phase 21)
    "ALIGNMENT_VERSION",
    "AlignmentService",
    "AlignmentReceipt",
    "AUDIO_PIPELINE_VERSION",
    "AudioPipelineService",
    "AudioPipelineConfig",
    "AudioPipelineReceipt",
    "AudioIssue",
    "DIALOGUE_PREP_VERSION",
    "DialoguePreparer",
    "DialoguePreparationReceipt",
    "PRONUNCIATION_LEXICON_VERSION",
    "MIX_VERSION",
    "MixPlanner",
    "TTS_PIPELINE_VERSION",
    "TtsSynthesizer",
    "TtsSynthesisRequest",
    "TtsSynthesisResult",
    "TtsProviderPort",
    "TtsSynthesisReceipt",
    "VOICE_CAST_VERSION",
    "VoiceCastingService",
    "VoiceCastReceipt",
    # candidate review / quality gates layer (Phase 20)
    "ReviewDimension",
    "ReviewerType",
    "CandidateVerdict",
    "BlockingReasonCode",
    "DimensionResult",
    "BlockingDefect",
    "CandidateReview",
    "HumanSelectionOverride",
    "RetryProposal",
    "SelectionRecord",
    "REVIEW_POLICY_VERSION",
    "DimensionConfig",
    "REVIEW_DIMENSIONS",
    "BLOCKING_DIMENSIONS",
    "config_for",
    "MediaProbeFacts",
    "DeterministicReviewResult",
    "DeterministicReviewer",
    "DETERMINISTIC_METRIC_VERSION",
    "ReviewModelPort",
    "VlmReviewRequest",
    "VlmReviewResult",
    "VlmReviewOutcome",
    "VlmReviewer",
    "VLM_METRIC_VERSION",
    "CrossShotReviewResult",
    "CrossShotReviewer",
    "CROSS_SHOT_METRIC_VERSION",
    "VerdictPolicy",
    "VERDICT_POLICY_VERSION",
    "CandidateSelector",
    "SELECTION_ALGORITHM_VERSION",
    "CandidateReviewReceipt",
    "ReviewPipeline",
]
