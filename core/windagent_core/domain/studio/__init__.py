"""
WindAgent Studio domain (studio.contract/v0.1).

Canonical, provider-neutral aggregates and value objects for the
``SeriesProject -> Episode -> ProductionRevision`` hierarchy: lifecycle rules,
approvals, artifact envelope, revision lineage with stale-write protection, and
VideoProject compatibility conversion. Story content schemas are owned by Plan B.
"""

from windagent_core.domain.studio.lifecycle import (
    ApprovalCheckpoint,
    ApprovalMode,
    CHECKPOINT_ORDER,
    CHECKPOINT_TO_REVIEW_STATE,
    EpisodeState,
    EpisodeStateMachine,
    LOCKED_STATES,
    TERMINAL_FAILURE_STATES,
    TERMINAL_STATES,
    TERMINAL_SUCCESS_STATES,
)
from windagent_core.domain.studio.series import SeriesProject
from windagent_core.domain.studio.episode import Episode
from windagent_core.domain.studio.approval import (
    ApprovalDecisionValue,
    ApprovalPolicy,
    ApprovalPolicyService,
    StudioApprovalDecision,
)
from windagent_core.domain.studio.artifact import (
    ArtifactType,
    IdeaCandidate,
    IdeaCandidateSet,
    StoryArtifactEnvelope,
)
from windagent_core.domain.studio.revision import (
    StudioInvalidationIntent,
    StudioLockState,
    StudioProductionRevision,
    StudioRevisionService,
    StudioRevisionStatus,
    canonical_content_hash,
)
from windagent_core.domain.studio.compat import (
    series_id_from_video,
    to_series_project,
    to_video_project,
    video_id_from_series,
)

# Migration-compatible alias: canonical revision type for new Studio code.
ProductionRevision = StudioProductionRevision
RevisionService = StudioRevisionService

__all__ = [
    "ApprovalCheckpoint",
    "ApprovalMode",
    "CHECKPOINT_ORDER",
    "CHECKPOINT_TO_REVIEW_STATE",
    "EpisodeState",
    "EpisodeStateMachine",
    "LOCKED_STATES",
    "TERMINAL_FAILURE_STATES",
    "TERMINAL_STATES",
    "TERMINAL_SUCCESS_STATES",
    "SeriesProject",
    "Episode",
    "ApprovalDecisionValue",
    "ApprovalPolicy",
    "ApprovalPolicyService",
    "StudioApprovalDecision",
    "ArtifactType",
    "IdeaCandidate",
    "IdeaCandidateSet",
    "StoryArtifactEnvelope",
    "StudioInvalidationIntent",
    "StudioLockState",
    "StudioProductionRevision",
    "StudioRevisionService",
    "StudioRevisionStatus",
    "canonical_content_hash",
    "ProductionRevision",
    "RevisionService",
    "series_id_from_video",
    "to_series_project",
    "to_video_project",
    "video_id_from_series",
]
