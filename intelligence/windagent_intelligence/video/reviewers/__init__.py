"""
Candidate review & quality gates (plan 05 Phase 20,
gate VP20_GENERATION_REVIEW_VERIFIED).

Multi-tier reviewer hierarchy (plan §24):

    deterministic validation (ffprobe/file/media/safety facts)
        ↓
    single-candidate VLM scoring (validated, never a false PASS)
        ↓
    cross-shot / reference comparison (via the Phase 10 continuity ledger)
        ↓
    verdict policy (blocking defect always wins; low confidence -> human)
        ↓
    candidate selection (rank unblocked only; audited human override)

The layer is provider-neutral: VLM goes through the `ReviewModelPort`
protocol (adapter injected at composition); deterministic + cross-shot +
verdict + selection are fully offline and deterministic.
"""

from windagent_intelligence.video.reviewers.models import (
    BlockingDefect,
    BlockingReasonCode,
    CandidateReview,
    CandidateVerdict,
    DimensionResult,
    HumanSelectionOverride,
    RetryProposal,
    ReviewDimension,
    ReviewerType,
    SelectionRecord,
)
from windagent_intelligence.video.reviewers.dimensions import (
    BLOCKING_DIMENSIONS,
    REVIEW_DIMENSIONS,
    REVIEW_POLICY_VERSION,
    DimensionConfig,
    config_for,
)
from windagent_intelligence.video.reviewers.deterministic import (
    DETERMINISTIC_METRIC_VERSION,
    DeterministicReviewResult,
    DeterministicReviewer,
    MediaProbeFacts,
)
from windagent_intelligence.video.reviewers.vlm import (
    VLM_DIMENSIONS,
    VLM_METRIC_VERSION,
    VLM_PROMPT_VERSION,
    VLM_SCHEMA_VERSION,
    ReviewModelPort,
    VlmReviewOutcome,
    VlmReviewRequest,
    VlmReviewResult,
    VlmReviewer,
)
from windagent_intelligence.video.reviewers.cross_shot import (
    CROSS_SHOT_METRIC_VERSION,
    CrossShotReviewResult,
    CrossShotReviewer,
)
from windagent_intelligence.video.reviewers.verdict import (
    VERDICT_POLICY_VERSION,
    VerdictPolicy,
)
from windagent_intelligence.video.reviewers.selection import (
    SELECTION_ALGORITHM_VERSION,
    CandidateSelector,
)
from windagent_intelligence.video.reviewers.pipeline import (
    CandidateReviewReceipt,
    ReviewPipeline,
)

__all__ = [
    # models
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
    # dimensions catalog
    "REVIEW_POLICY_VERSION",
    "DimensionConfig",
    "REVIEW_DIMENSIONS",
    "BLOCKING_DIMENSIONS",
    "config_for",
    # deterministic tier
    "DETERMINISTIC_METRIC_VERSION",
    "MediaProbeFacts",
    "DeterministicReviewResult",
    "DeterministicReviewer",
    # VLM tier
    "VLM_DIMENSIONS",
    "VLM_METRIC_VERSION",
    "VLM_PROMPT_VERSION",
    "VLM_SCHEMA_VERSION",
    "ReviewModelPort",
    "VlmReviewRequest",
    "VlmReviewResult",
    "VlmReviewOutcome",
    "VlmReviewer",
    # cross-shot tier
    "CROSS_SHOT_METRIC_VERSION",
    "CrossShotReviewResult",
    "CrossShotReviewer",
    # verdict policy
    "VERDICT_POLICY_VERSION",
    "VerdictPolicy",
    # selection
    "SELECTION_ALGORITHM_VERSION",
    "CandidateSelector",
    # pipeline
    "CandidateReviewReceipt",
    "ReviewPipeline",
]
