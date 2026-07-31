"""
WindAgent Video Production domain (Phase 3 canonical protocol).

Pure domain models for VideoProductionPackage v1. Core never imports
intelligence, tools, providers, workflows, storage, or third_party.
"""

from windagent_core.domain.video_production.ids import (
    ApprovalId,
    CharacterId,
    CinematicPlanId,
    ContinuityStateId,
    CreativeBriefId,
    DialogueLineId,
    FinalDeliverableId,
    GenerationCandidateId,
    GenerationRequestId,
    LocationId,
    ProductionRevisionId,
    PropId,
    ReferenceAssetId,
    ReviewResultId,
    SceneId,
    ScreenplayId,
    ShotDependencyId,
    ShotId,
    StoryConceptId,
    StyleBibleId,
    VideoProjectId,
)
from windagent_core.domain.video_production.enums import (
    ApprovalDecisionType,
    ApprovalRole,
    AssetSourceType,
    CameraMovement,
    CharacterRole,
    DependencyType,
    GenerationMode,
    GenerationStatus,
    InvalidationIntent,
    LicenseState,
    MediaType,
    ProjectStatus,
    ReviewVerdict,
    RevisionStatus,
    ScreenplayStatus,
    ShotType,
    TimeOfDay,
    TransitionType,
)
from windagent_core.domain.video_production.errors import (
    BrokenReferenceError,
    DuplicateIdentifierError,
    LockedRevisionMutationError,
    UnsupportedMajorVersionError,
    VideoProductionProtocolError,
)
from windagent_core.domain.video_production.project import (
    ProductionRevision,
    RevisionService,
    VideoProject,
    utc_now,
)
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief,
    DialogueLine,
    Screenplay,
    StoryConcept,
)
from windagent_core.domain.video_production.scene import Scene
from windagent_core.domain.video_production.character import CharacterBible
from windagent_core.domain.video_production.location import LocationBible, PropBible, StyleBible
from windagent_core.domain.video_production.shot import (
    CinematicPlan,
    Shot,
    ShotDependency,
    ShotDependencyGraph,
)
from windagent_core.domain.video_production.asset import (
    AssetAcquisitionRecord,
    FinalDeliverable,
    ReferenceAsset,
)
from windagent_core.domain.video_production.continuity import ContinuityState
from windagent_core.domain.video_production.generation_job import (
    GenerationCandidate,
    GenerationRecord,
    GenerationRequest,
)
from windagent_core.domain.video_production.approval import (
    ApprovalDecision,
    ApprovalState,
    ReviewResult,
)
from windagent_core.domain.video_production.package import (
    VIDEO_PRODUCTION_PACKAGE_VERSION,
    PackageProvenance,
    VideoProductionPackage,
    parse_package_major_version,
    validate_package_major,
)
from windagent_core.domain.video_production.validation import (
    ValidationIssue,
    VideoProductionPackageValidator,
)

__all__ = [
    # IDs
    "ApprovalId",
    "CharacterId",
    "CinematicPlanId",
    "ContinuityStateId",
    "CreativeBriefId",
    "DialogueLineId",
    "FinalDeliverableId",
    "GenerationCandidateId",
    "GenerationRequestId",
    "LocationId",
    "ProductionRevisionId",
    "PropId",
    "ReferenceAssetId",
    "ReviewResultId",
    "SceneId",
    "ScreenplayId",
    "ShotDependencyId",
    "ShotId",
    "StoryConceptId",
    "StyleBibleId",
    "VideoProjectId",
    # Enums
    "ApprovalDecisionType",
    "ApprovalRole",
    "AssetSourceType",
    "CameraMovement",
    "CharacterRole",
    "DependencyType",
    "GenerationMode",
    "GenerationStatus",
    "InvalidationIntent",
    "LicenseState",
    "MediaType",
    "ProjectStatus",
    "ReviewVerdict",
    "RevisionStatus",
    "ScreenplayStatus",
    "ShotType",
    "TimeOfDay",
    "TransitionType",
    # Errors
    "BrokenReferenceError",
    "DuplicateIdentifierError",
    "LockedRevisionMutationError",
    "UnsupportedMajorVersionError",
    "VideoProductionProtocolError",
    # Aggregates & entities
    "VideoProject",
    "ProductionRevision",
    "RevisionService",
    "CreativeBrief",
    "StoryConcept",
    "Screenplay",
    "DialogueLine",
    "Scene",
    "CharacterBible",
    "LocationBible",
    "PropBible",
    "StyleBible",
    "Shot",
    "ShotDependency",
    "ShotDependencyGraph",
    "CinematicPlan",
    "ReferenceAsset",
    "AssetAcquisitionRecord",
    "FinalDeliverable",
    "ContinuityState",
    "GenerationRequest",
    "GenerationCandidate",
    "GenerationRecord",
    "ReviewResult",
    "ApprovalDecision",
    "ApprovalState",
    # Package & protocol
    "VIDEO_PRODUCTION_PACKAGE_VERSION",
    "PackageProvenance",
    "VideoProductionPackage",
    "parse_package_major_version",
    "validate_package_major",
    "ValidationIssue",
    "VideoProductionPackageValidator",
    "utc_now",
]
