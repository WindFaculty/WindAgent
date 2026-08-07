"""
Shared enumerations for the WindAgent Video Production domain (Phase 3).
All enums are canonical WindAgent terms. No upstream (ViMax / VideoClaw) names
leak into public API, schemas, or event payloads.
"""

from __future__ import annotations

from enum import Enum


class ProjectStatus(str, Enum):
    """Lifecycle of a VideoProject aggregate."""

    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    PRODUCTION = "PRODUCTION"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class RevisionStatus(str, Enum):
    """Lifecycle of an immutable ProductionRevision."""

    DRAFT = "DRAFT"
    LOCKED = "LOCKED"


class ScreenplayStatus(str, Enum):
    """Lifecycle of a Screenplay aggregate."""

    DRAFT = "DRAFT"
    LOCKED = "LOCKED"


class InvalidationIntent(str, Enum):
    """Downstream invalidation intent required for screenplay changes.

    A screenplay change must declare how much of the downstream production
    graph becomes stale so schedulers and caches can invalidate correctly.
    """

    NONE = "NONE"
    INVALIDATE_SHOT_PLAN = "INVALIDATE_SHOT_PLAN"
    INVALIDATE_GENERATION = "INVALIDATE_GENERATION"
    INVALIDATE_ASSETS = "INVALIDATE_ASSETS"
    INVALIDATE_ALL = "INVALIDATE_ALL"


class CharacterRole(str, Enum):
    """Role classification within a CharacterBible."""

    LEAD = "LEAD"
    SUPPORTING = "SUPPORTING"
    EXTRAS = "EXTRAS"


class TimeOfDay(str, Enum):
    """Canonical time-of-day tags for scenes."""

    DAY = "DAY"
    NIGHT = "NIGHT"
    DAWN = "DAWN"
    DUSK = "DUSK"
    INTERIOR = "INTERIOR"


class ShotType(str, Enum):
    """Canonical shot types (terminology from road_map.md Phase 9)."""

    ESTABLISHING = "ESTABLISHING"
    MASTER = "MASTER"
    MEDIUM = "MEDIUM"
    CLOSE_UP = "CLOSE_UP"
    EXTREME_CLOSE_UP = "EXTREME_CLOSE_UP"
    OVER_SHOULDER = "OVER_SHOULDER"
    POV = "POV"
    INSERT = "INSERT"
    REACTION = "REACTION"
    TRANSITION = "TRANSITION"


class CameraMovement(str, Enum):
    """Canonical camera movements."""

    STATIC = "STATIC"
    PAN = "PAN"
    TILT = "TILT"
    DOLLY = "DOLLY"
    TRACK = "TRACK"
    CRANE = "CRANE"
    HANDHELD = "HANDHELD"


class TransitionType(str, Enum):
    """Canonical shot transitions."""

    CUT = "CUT"
    FADE = "FADE"
    DISSOLVE = "DISSOLVE"
    WIPE = "WIPE"
    MATCH_CUT = "MATCH_CUT"


class DependencyType(str, Enum):
    """Typed edges in a ShotDependencyGraph (road_map.md Phase 9)."""

    TEMPORAL = "TEMPORAL"
    VISUAL_REFERENCE = "VISUAL_REFERENCE"
    CONTINUITY = "CONTINUITY"
    TRANSITION = "TRANSITION"
    DIALOGUE = "DIALOGUE"
    ASSET = "ASSET"


class AssetSourceType(str, Enum):
    """Origin of a ReferenceAsset."""

    GENERATED = "GENERATED"
    INTERNET = "INTERNET"
    UPLOADED = "UPLOADED"
    PROVIDER = "PROVIDER"
    LOCAL_LIBRARY = "LOCAL_LIBRARY"


class LicenseState(str, Enum):
    """License classification for assets (road_map.md Phase 7)."""

    UNKNOWN = "UNKNOWN"
    LICENSED = "LICENSED"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    CREATIVE_COMMONS = "CREATIVE_COMMONS"
    PROPRIETARY = "PROPRIETARY"
    REJECTED = "REJECTED"


class GenerationStatus(str, Enum):
    """Lifecycle of a generation job / candidate."""

    SUBMITTED = "SUBMITTED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ReviewVerdict(str, Enum):
    """Verdict of a ReviewResult (road_map.md Phase 20)."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"
    BLOCKED = "BLOCKED"


class ApprovalRole(str, Enum):
    """Role of an approval actor."""

    OWNER = "OWNER"
    DIRECTOR = "DIRECTOR"
    QUALITY_REVIEWER = "QUALITY_REVIEWER"
    LEGAL = "LEGAL"
    ADMIN = "ADMIN"


class ApprovalDecisionType(str, Enum):
    """Outcome of an ApprovalDecision."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MediaType(str, Enum):
    """Canonical media type families for assets and deliverables."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class DirectorialIssueCategory(str, Enum):
    """Typed categories of directorial issues (road_map.md Phase 8)."""

    DURATION_OVERFLOW = "DURATION_OVERFLOW"
    DIALOGUE_DURATION_MISMATCH = "DIALOGUE_DURATION_MISMATCH"
    UNKNOWN_REFERENCE = "UNKNOWN_REFERENCE"
    MISSING_COVERAGE = "MISSING_COVERAGE"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"


class IssueSeverity(str, Enum):
    """Severity of a directorial issue."""

    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class ProposalStatus(str, Enum):
    """Lifecycle of a ScriptRevisionProposal."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RequiredArtifactType(str, Enum):
    """Artifact a dependency edge requires from its predecessor (Phase 9).

    `NONE` means the edge is a pure ordering/scheduling hint; a non-NONE value
    means the successor cannot start until the predecessor produced that
    artifact (e.g. a tail frame for continuity, both clips for a transition).
    """

    NONE = "NONE"
    TAIL_FRAME = "TAIL_FRAME"
    FIRST_FRAME = "FIRST_FRAME"
    LAST_FRAME = "LAST_FRAME"
    FULL_CLIP = "FULL_CLIP"
    REFERENCE_IMAGE = "REFERENCE_IMAGE"


class CameraAngle(str, Enum):
    """Canonical camera angles (Phase 9 shot specification)."""

    EYE_LEVEL = "EYE_LEVEL"
    LOW_ANGLE = "LOW_ANGLE"
    HIGH_ANGLE = "HIGH_ANGLE"
    OVERHEAD = "OVERHEAD"
    DUTCH = "DUTCH"
    BIRDS_EYE = "BIRDS_EYE"
    WORMS_EYE = "WORMS_EYE"


class CameraSide(str, Enum):
    """Side of the scene action line the camera occupies (180-degree rule).

    Coverage shots in a scene must stay on ONE side of the action line
    (`SIDE_A` by default); `NEUTRAL` is reserved for establishing / POV /
    insert / transition shots that are not part of the line geometry.
    """

    SIDE_A = "SIDE_A"
    SIDE_B = "SIDE_B"
    NEUTRAL = "NEUTRAL"


class ScreenDirection(str, Enum):
    """Screen direction of subject movement within a shot (Phase 9)."""

    LEFT_TO_RIGHT = "LEFT_TO_RIGHT"
    RIGHT_TO_LEFT = "RIGHT_TO_LEFT"
    NEUTRAL = "NEUTRAL"


class CameraDecisionReasonCode(str, Enum):
    """Machine-readable reason behind a camera decision (plan §14.2)."""

    ESTABLISH_GEOGRAPHY = "ESTABLISH_GEOGRAPHY"
    SPATIAL_CONTINUITY = "SPATIAL_CONTINUITY"
    SCREEN_DIRECTION_CONTINUITY = "SCREEN_DIRECTION_CONTINUITY"
    DIALOGUE_ALIGNMENT = "DIALOGUE_ALIGNMENT"
    ACTION_FOLLOW = "ACTION_FOLLOW"
    EMOTIONAL_BEAT = "EMOTIONAL_BEAT"
    POV_SUBJECTIVE = "POV_SUBJECTIVE"
    INSERT_DETAIL = "INSERT_DETAIL"
    REACTION_BEAT = "REACTION_BEAT"
    TRANSITION_ENDPOINT = "TRANSITION_ENDPOINT"


class ShotGraphIssueCode(str, Enum):
    """Typed findings from shot-graph / camera validation (Phase 9).

    Structural codes are blocking (fail closed before publish); camera codes
    are soft warnings that record constraint violations without blocking.
    """

    # Structural graph rules (plan §13) — blocking.
    DUPLICATE_NODE_ID = "DUPLICATE_NODE_ID"
    DUPLICATE_EDGE_ID = "DUPLICATE_EDGE_ID"
    MISSING_NODE = "MISSING_NODE"
    SELF_EDGE = "SELF_EDGE"
    BLOCKING_CYCLE = "BLOCKING_CYCLE"
    INVALID_CROSS_SCENE = "INVALID_CROSS_SCENE"
    # Camera / creative rules (plan §14.2) — non-blocking warnings.
    CAMERA_SIDE_VIOLATION = "CAMERA_SIDE_VIOLATION"
    SCREEN_DIRECTION_FLIP = "SCREEN_DIRECTION_FLIP"
    MOVEMENT_TOO_SHORT = "MOVEMENT_TOO_SHORT"
    ESTABLISHING_ORDER = "ESTABLISHING_ORDER"
    REACTION_MISSING_SOURCE = "REACTION_MISSING_SOURCE"


class ContinuityFieldSource(str, Enum):
    """Provenance of a continuity state field (plan 03 §18).

    Every important continuity field records where its value came from so the
    ledger can be traced, reviewed, and invalidated deterministically:
    screenplay facts, entity/style bibles, approved references, explicit
    director decisions, predecessor shot output, or a human override.
    """

    SCREENPLAY_FACT = "SCREENPLAY_FACT"
    BIBLE_FACT = "BIBLE_FACT"
    APPROVED_REFERENCE = "APPROVED_REFERENCE"
    DIRECTOR_DECISION = "DIRECTOR_DECISION"
    PREDECESSOR_OUTPUT = "PREDECESSOR_OUTPUT"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"


class ContinuityIssueCode(str, Enum):
    """Typed continuity findings (plan 03 §18-§20).

    Structural continuity defects are blocking (fail closed before publish):
    an unexplained prop change, a change outside the shot's allowed set, an
    identity/reference hash mismatch, or a camera-side (180-degree) violation.
    Parallel-branch conflicts are raised as blocking issues until a merge rule
    is provided; missing required state is a non-blocking warning.
    """

    PROP_UNEXPLAINED_CHANGE = "PROP_UNEXPLAINED_CHANGE"
    CHANGE_OUTSIDE_ALLOWED = "CHANGE_OUTSIDE_ALLOWED"
    IDENTITY_HASH_MISMATCH = "IDENTITY_HASH_MISMATCH"
    CAMERA_SIDE_VIOLATION = "CAMERA_SIDE_VIOLATION"
    PARALLEL_CONFLICT = "PARALLEL_CONFLICT"
    MISSING_REQUIRED_STATE = "MISSING_REQUIRED_STATE"


class ReferenceBindingRole(str, Enum):
    """Role a bound reference asset plays for a shot (plan 03 §24.1).

    Identity/location/prop/style assets are bound per content hash; first/last
    frames and predecessor clips are required by specific dependency
    semantics; ingredients are the generic fallback reference role.
    """

    IDENTITY = "IDENTITY"
    LOCATION = "LOCATION"
    PROP = "PROP"
    STYLE = "STYLE"
    FIRST_FRAME = "FIRST_FRAME"
    LAST_FRAME = "LAST_FRAME"
    INGREDIENT = "INGREDIENT"
    PREDECESSOR_CLIP = "PREDECESSOR_CLIP"


class ReferenceBindingIssueCode(str, Enum):
    """Typed findings from reference binding validation (plan 03 §24.1).

    Only APPROVED assets of the correct revision may be bound; a missing,
    unapproved, stale (hash-mismatched) or wrong-revision asset, or a
    duplicate binding for the same shot, is BLOCKING (fail closed).
    """

    UNKNOWN_ASSET = "UNKNOWN_ASSET"
    NOT_APPROVED = "NOT_APPROVED"
    STALE_HASH = "STALE_HASH"
    WRONG_REVISION = "WRONG_REVISION"
    DUPLICATE_BINDING = "DUPLICATE_BINDING"
    MISSING_REQUIRED_BINDING = "MISSING_REQUIRED_BINDING"


class PromptBlockType(str, Enum):
    """Canonical prompt blocks (plan 03 §24.2).

    The block list, order and format are versioned by the prompt template
    version. Empty OPTIONAL blocks are dropped by rule; a missing REQUIRED
    block fails compilation (no partial prompt is published).
    """

    PROJECT_STYLE = "PROJECT_STYLE"
    IDENTITY = "IDENTITY"
    LOCATION = "LOCATION"
    PROPS = "PROPS"
    SHOT_COMPOSITION = "SHOT_COMPOSITION"
    ACTION = "ACTION"
    CAMERA = "CAMERA"
    LIGHTING = "LIGHTING"
    CONTINUITY = "CONTINUITY"
    DIALOGUE_AUDIO_INTENT = "DIALOGUE_AUDIO_INTENT"
    DURATION = "DURATION"
    NEGATIVE_CONSTRAINTS = "NEGATIVE_CONSTRAINTS"


class AudioIntentType(str, Enum):
    """Kind of spoken audio line (plan 06 §8.1)."""

    SPOKEN_DIALOGUE = "SPOKEN_DIALOGUE"
    NARRATION = "NARRATION"
    NON_VERBAL_CUE = "NON_VERBAL_CUE"


class AudioCueKind(str, Enum):
    """Kind of non-dialogue audio cue (plan 06 §8.5)."""

    SFX = "SFX"
    BGM = "BGM"
    AMBIENCE = "AMBIENCE"


class VoiceRightsState(str, Enum):
    """Rights/consent state of a voice or likeness (plan 06 §7).

    Real-voice likenesses REQUIRE consent metadata + approval; synthetic
    voices are LICENSED per the provider terms.
    """

    UNKNOWN = "UNKNOWN"
    CONSENTED = "CONSENTED"
    LICENSED = "LICENSED"
    REJECTED = "REJECTED"


class AudioAlignmentStatus(str, Enum):
    """Forced-alignment outcome for a dialogue track (plan 06 §8.4)."""

    UNALIGNED = "UNALIGNED"  # audio present but forced alignment not done
    ALIGNED = "ALIGNED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    OVERLONG_LINE = "OVERLONG_LINE"
    TIMING_PROPOSED = "TIMING_PROPOSED"


class AudioInvalidationScope(str, Enum):
    """Downstream invalidation scope of an audio change (plan 06 §8.5).

    A dialogue/text change invalidates its audio + mix + final cut; a BGM
    change invalidates ONLY the mix/final cut, never the visual clips.
    """

    TRACK_AND_MIX = "TRACK_AND_MIX"
    MIX_ONLY = "MIX_ONLY"
    NONE = "NONE"


class PromptCompilerIssueCode(str, Enum):
    """Typed findings from prompt compilation (plan 03 §24.2-§24.5).

    Missing required blocks, missing mode-specific inputs, oversized prompts,
    forbidden/sensitive content, unknown fields, or injection-suspect text are
    BLOCKING (fail closed — the request is never published).
    """

    MISSING_REQUIRED_BLOCK = "MISSING_REQUIRED_BLOCK"
    MODE_MISSING_INPUT = "MODE_MISSING_INPUT"
    PROMPT_OVERSIZED = "PROMPT_OVERSIZED"
    FORBIDDEN_CONTENT = "FORBIDDEN_CONTENT"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    INJECTION_SUSPECT = "INJECTION_SUSPECT"


class PostProductionStatus(str, Enum):
    """Execution status of a post-production render job (plan 06 §13)."""

    PENDING = "PENDING"
    NORMALIZING = "NORMALIZING"
    ASSEMBLING = "ASSEMBLING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class EncodingPreset(str, Enum):
    """Pre-defined encoding profile presets (plan 06 §13.3)."""

    MAIN_1080P_H264 = "MAIN_1080P_H264"
    PROXY_720P_H264 = "PROXY_720P_H264"
    THUMBNAIL_JPEG = "THUMBNAIL_JPEG"


class ContainerFormat(str, Enum):
    """Supported container formats."""

    MP4 = "MP4"
    JPG = "JPG"


class PostProductionVerificationStatus(str, Enum):
    """Outcome of quality verification checks on rendered deliverable."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class PostProductionIssueCode(str, Enum):
    """Typed findings from post-production assembly & verification."""

    INPUT_CLIP_MISSING = "INPUT_CLIP_MISSING"
    INPUT_CORRUPT = "INPUT_CORRUPT"
    ASPECT_RATIO_VIOLATION = "ASPECT_RATIO_VIOLATION"
    DURATION_OUT_OF_TOLERANCE = "DURATION_OUT_OF_TOLERANCE"
    BLACK_FRAMES_DETECTED = "BLACK_FRAMES_DETECTED"
    TRUNCATED_ENDING = "TRUNCATED_ENDING"
    AUDIO_STREAM_MISSING = "AUDIO_STREAM_MISSING"
    LOUDNESS_OUT_OF_BOUNDS = "LOUDNESS_OUT_OF_BOUNDS"
    PEAK_CEILING_EXCEEDED = "PEAK_CEILING_EXCEEDED"
    SUBTITLE_BOUNDS_INVALID = "SUBTITLE_BOUNDS_INVALID"
    REPRODUCIBILITY_MISMATCH = "REPRODUCIBILITY_MISMATCH"


__all__ = [
    "ProjectStatus",
    "RevisionStatus",
    "ScreenplayStatus",
    "InvalidationIntent",
    "CharacterRole",
    "TimeOfDay",
    "ShotType",
    "CameraMovement",
    "TransitionType",
    "DependencyType",
    "AssetSourceType",
    "LicenseState",
    "GenerationStatus",
    "ReviewVerdict",
    "ApprovalRole",
    "ApprovalDecisionType",
    "MediaType",
    "DirectorialIssueCategory",
    "IssueSeverity",
    "ProposalStatus",
    "RequiredArtifactType",
    "CameraAngle",
    "CameraSide",
    "ScreenDirection",
    "CameraDecisionReasonCode",
    "ShotGraphIssueCode",
    "ReferenceBindingRole",
    "ReferenceBindingIssueCode",
    "PromptBlockType",
    "PromptCompilerIssueCode",
    "AudioIntentType",
    "AudioCueKind",
    "VoiceRightsState",
    "AudioAlignmentStatus",
    "AudioInvalidationScope",
    "PostProductionStatus",
    "EncodingPreset",
    "ContainerFormat",
    "PostProductionVerificationStatus",
    "PostProductionIssueCode",
]
