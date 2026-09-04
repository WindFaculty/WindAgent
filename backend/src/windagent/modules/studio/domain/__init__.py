"""Domain layer of the Studio bounded context — pure logic, no I/O imports."""

from .approval import (
    ApprovalDecisionValue,
    ApprovalPolicy,
    ApprovalPolicyService,
    StudioApprovalDecision,
)
from .characters.character import Character
from .episodes.episode import Episode
from .episodes.revision import (
    InvalidationIntent,
    LockState,
    ProductionRevision,
    RevisionService,
    RevisionStatus,
    canonical_content_hash,
)
from .errors import (
    StudioApprovalRequiredError,
    StudioArtifactHashMismatchError,
    StudioCapabilityUnavailableError,
    StudioError,
    StudioInvalidTransitionError,
    StudioLockedRevisionError,
    StudioNotFoundError,
    StudioStaleRevisionError,
    StudioStateError,
    StudioValidationError,
)
from .ids import (
    ArtifactId,
    CharacterId,
    EpisodeId,
    ProjectId,
    RevisionId,
    RunId,
    SeriesId,
    StoryboardId,
    WorldEntryId,
)
from .lifecycle import (
    CHECKPOINT_ORDER,
    CHECKPOINT_TO_REVIEW_STATE,
    LOCKED_STATES,
    TERMINAL_FAILURE_STATES,
    TERMINAL_STATES,
    TERMINAL_SUCCESS_STATES,
    ApprovalCheckpoint,
    ApprovalMode,
    EpisodeState,
    EpisodeStateMachine,
)
from .projects.project import Project
from .series.series import SeriesProject
from .story.artifact import ArtifactType, StoryArtifactEnvelope
from .story.bibles import CharacterCanon, StoryBible, WorldBible
from .storyboard.storyboard import Storyboard, StoryboardPanel
from .world.world import WorldBibleAggregate, WorldLocation, WorldProp

__all__ = [
    "ApprovalCheckpoint",
    "ApprovalDecisionValue",
    "ApprovalMode",
    "ApprovalPolicy",
    "ApprovalPolicyService",
    "ArtifactId",
    "ArtifactType",
    "CHECKPOINT_ORDER",
    "CHECKPOINT_TO_REVIEW_STATE",
    "Character",
    "CharacterCanon",
    "CharacterId",
    "Episode",
    "EpisodeId",
    "EpisodeState",
    "EpisodeStateMachine",
    "InvalidationIntent",
    "LOCKED_STATES",
    "LockState",
    "ProductionRevision",
    "Project",
    "ProjectId",
    "RevisionId",
    "RevisionService",
    "RevisionStatus",
    "RunId",
    "SeriesId",
    "SeriesProject",
    "Storyboard",
    "StoryboardId",
    "StoryboardPanel",
    "StoryArtifactEnvelope",
    "StoryBible",
    "StudioApprovalDecision",
    "StudioApprovalRequiredError",
    "StudioArtifactHashMismatchError",
    "StudioCapabilityUnavailableError",
    "StudioError",
    "StudioInvalidTransitionError",
    "StudioLockedRevisionError",
    "StudioNotFoundError",
    "StudioStaleRevisionError",
    "StudioStateError",
    "StudioValidationError",
    "TERMINAL_FAILURE_STATES",
    "TERMINAL_STATES",
    "TERMINAL_SUCCESS_STATES",
    "WorldBible",
    "WorldBibleAggregate",
    "WorldEntryId",
    "WorldLocation",
    "WorldProp",
    "canonical_content_hash",
]
