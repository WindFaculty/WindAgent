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


class CharacterMasterState(str, Enum):
    """Lifecycle state of a CharacterMaster revision (VP3D Phase 8).

    Mirrors the ratified transition graph `DRAFT → NORMALIZED → RIGGED →
    VALIDATED → APPROVED → RETIRED` (stage_d.md §3 backlog item 2). A master
    revision is immutable once bound; promoted revisions pin content so
    locked episodes stay stable when a later revision replaces it.
    """

    DRAFT = "DRAFT"
    NORMALIZED = "NORMALIZED"
    RIGGED = "RIGGED"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class CharacterApprovalVerdict(str, Enum):
    """Verdict applied by human approval of a character master revision."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"



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
    MODEL_3D = "model_3d"
    UNKNOWN = "unknown"


class ProductionAssetKind(str, Enum):
    """Production taxonomy by meaning (Stage D UI19)."""

    CHARACTER = "CHARACTER"
    ENVIRONMENT = "ENVIRONMENT"
    PROP = "PROP"
    MODEL_3D = "MODEL_3D"
    MATERIAL = "MATERIAL"
    TEXTURE = "TEXTURE"
    RIG = "RIG"
    ANIMATION = "ANIMATION"
    FACIAL_PROFILE = "FACIAL_PROFILE"
    VOICE_PROFILE = "VOICE_PROFILE"
    VOICE_SAMPLE = "VOICE_SAMPLE"
    DIALOGUE_AUDIO = "DIALOGUE_AUDIO"
    MUSIC = "MUSIC"
    SFX = "SFX"
    AMBIENCE = "AMBIENCE"
    LIGHT_RIG = "LIGHT_RIG"
    CAMERA_RIG = "CAMERA_RIG"
    REFERENCE_IMAGE = "REFERENCE_IMAGE"
    STORYBOARD = "STORYBOARD"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class AssetProcessingState(str, Enum):
    """Operational/processing lifecycle state of an asset job (Stage D UI21)."""

    IDLE = "IDLE"
    DOWNLOADING = "DOWNLOADING"
    NORMALIZING = "NORMALIZING"
    GENERATING_PREVIEW = "GENERATING_PREVIEW"
    VALIDATING = "VALIDATING"
    RIGGING = "RIGGING"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"



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


class EasingKind(str, Enum):
    """Path easing between camera keyframes (VP3D Phase 13)."""

    LINEAR = "LINEAR"
    EASE_IN = "EASE_IN"
    EASE_OUT = "EASE_OUT"
    EASE_IN_OUT = "EASE_IN_OUT"


class LightingMood(str, Enum):
    """Director-facing mood of a scene's light (VP3D Phase 14, stage_g §4).

    Mood is director flavor recorded on the intent; the lighting compiler
    selects the versioned preset from style + time-of-day.
    """

    HAPPY = "HAPPY"
    SAD = "SAD"
    TENSE = "TENSE"
    MYSTERIOUS = "MYSTERIOUS"
    ROMANTIC = "ROMANTIC"
    EPIC = "EPIC"
    NEUTRAL = "NEUTRAL"


class LightingStyle(str, Enum):
    """Canonical lighting styles (road_map.md Phase 14).

    `CHILDREN_3D` is the road_map example style; the preset registry aliases
    it onto the CARTOON family so `mood=HAPPY, time=DAY, style=CHILDREN_3D`
    resolves to CARTOON_DAY.
    """

    CARTOON = "CARTOON"
    CHILDREN_3D = "CHILDREN_3D"
    INTERIOR = "INTERIOR"
    MAGIC_FOREST = "MAGIC_FOREST"
    SUNSET = "SUNSET"
    DRAMATIC = "DRAMATIC"
    COMEDY = "COMEDY"


class LightingEmphasis(str, Enum):
    """What the light rig prioritizes (stage_g §4 backlog 3)."""

    SUBJECT = "SUBJECT"
    ENVIRONMENT = "ENVIRONMENT"
    BALANCED = "BALANCED"


class LightRole(str, Enum):
    """Typed light roles in a rig (engine-neutral; the adapter maps to bpy/Lumen)."""

    KEY = "KEY"
    FILL = "FILL"
    RIM = "RIM"
    BOUNCE = "BOUNCE"
    PRACTICAL = "PRACTICAL"
    AMBIENT = "AMBIENT"


class LightingColorPolicy(str, Enum):
    """How strictly a preset's light colors may deviate (stage_g §4 backlog 2).

    Each policy carries its own CCT spread tolerance in the validator so an
    intentional warm/cool split never trips the "inconsistent color
    temperature" check that a uniform-CCT rig would.
    """

    UNIFORM_CCT = "UNIFORM_CCT"
    WARM_COOL_SPLIT = "WARM_COOL_SPLIT"
    COOL_MOONLIGHT = "COOL_MOONLIGHT"
    WARM_FIRELIGHT = "WARM_FIRELIGHT"
    MULTICOLOR = "MULTICOLOR"


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


class FrameSequenceIssueCode(str, Enum):
    """Typed findings on a rendered PNG/EXR frame sequence (VP3D Phase 24).

    The sequence must be contiguous, unique, readable and dimension/fps/color
    consistent BEFORE any FFmpeg assembly starts (stage_l.md §3 backlog 1).
    """

    FRAME_MISSING = "FRAME_MISSING"
    FRAME_DUPLICATE = "FRAME_DUPLICATE"
    FRAME_GAP = "FRAME_GAP"
    FRAME_CORRUPT = "FRAME_CORRUPT"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    FPS_MISMATCH = "FPS_MISMATCH"
    COLORSPACE_UNSPECIFIED = "COLORSPACE_UNSPECIFIED"


class MixTrackKind(str, Enum):
    """Role of an audio track inside a versioned mix plan (VP3D Phase 24)."""

    DIALOGUE = "DIALOGUE"
    SFX = "SFX"
    BGM = "BGM"


class AssemblyInvalidationScope(str, Enum):
    """Downstream rebuild scope of one changed assembly input (stage_l §3 backlog 9).

    - TIMELINE_FINAL: a rendered shot changed -> EDL timeline + final rebuild
      (audio mix and verified sibling artifacts stay untouched);
    - MIX_FINAL: a dialogue/SFX/BGM track changed -> audio mix + final rebuild,
      visual frame sequences are REUSED (never re-normalized);
    - FINAL_ONLY: subtitle changed -> final remuxed from the verified video
      stream (copy), no frame re-encode and no mix rebuild;
    - NONE: nothing changed -> verified deliverable reused.
    """

    TIMELINE_FINAL = "TIMELINE_FINAL"
    MIX_FINAL = "MIX_FINAL"
    FINAL_ONLY = "FINAL_ONLY"
    NONE = "NONE"


class SemanticBone(str, Enum):
    """Provider-agnostic semantic bone roles (VP3D Phase 9, backlog 1).

    A normalized skeleton exposes these semantic roles regardless of the
    source provider's bone naming. Retarget mapping operates on semantic roles,
    never on raw bone names (stage_d.md §4 backlog 1).
    """

    ROOT = "ROOT"
    PELVIS = "PELVIS"
    SPINE = "SPINE"
    CHEST = "CHEST"
    NECK = "NECK"
    HEAD = "HEAD"
    JAW = "JAW"
    EYE_L = "EYE_L"
    EYE_R = "EYE_R"
    BROW_L = "BROW_L"
    BROW_R = "BROW_R"
    SHOULDER_L = "SHOULDER_L"
    SHOULDER_R = "SHOULDER_R"
    ARM_UPPER_L = "ARM_UPPER_L"
    ARM_UPPER_R = "ARM_UPPER_R"
    ARM_LOWER_L = "ARM_LOWER_L"
    ARM_LOWER_R = "ARM_LOWER_R"
    HAND_L = "HAND_L"
    HAND_R = "HAND_R"
    THIGH_L = "THIGH_L"
    THIGH_R = "THIGH_R"
    SHIN_L = "SHIN_L"
    SHIN_R = "SHIN_R"
    FOOT_L = "FOOT_L"
    FOOT_R = "FOOT_R"
    TOE_L = "TOE_L"
    TOE_R = "TOE_R"


class RigValidationIssueCode(str, Enum):
    """Typed validation findings on a rig (VP3D Phase 9, backlog 2 & 5)."""

    REST_POSE_NOT_BIND = "REST_POSE_NOT_BIND"
    SCALE_OUT_OF_RANGE = "SCALE_OUT_OF_RANGE"
    ROOT_BONE_MISSING = "ROOT_BONE_MISSING"
    ROOT_BONE_ORPHANED = "ROOT_BONE_ORPHANED"
    PARENTING_BROKEN = "PARENTING_BROKEN"
    WEIGHTS_UNASSIGNED = "WEIGHTS_UNASSIGNED"
    WEIGHTS_OVER_BUDGET = "WEIGHTS_OVER_BUDGET"
    JOINT_LIMIT_VIOLATED = "JOINT_LIMIT_VIOLATED"
    FACIAL_CONTROLS_INCOMPATIBLE = "FACIAL_CONTROLS_INCOMPATIBLE"
    SKELETON_MISSING_SEMANTIC_BONES = "SKELETON_MISSING_SEMANTIC_BONES"
    TOPOLOGY_HASH_MISMATCH = "TOPOLOGY_HASH_MISMATCH"


class RigStatus(str, Enum):
    """Lifecycle state of a rig (VP3D Phase 9, backlog 2/6)."""

    DETECTED = "DETECTED"
    NORMALIZED = "NORMALIZED"
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"
    RETARGET_READY = "RETARGET_READY"


class DeformationMetric(str, Enum):
    """Animation deformation metrics measured per clip (VP3D Phase 9, backlog 5)."""

    FOOT_SLIDING = "FOOT_SLIDING"
    LIMB_STRETCH = "LIMB_STRETCH"
    MESH_PENETRATION = "MESH_PENETRATION"
    ROOT_DRIFT = "ROOT_DRIFT"
    POSE_DISCONTINUITY = "POSE_DISCONTINUITY"


class CompatibilityVerdict(str, Enum):
    """Per-clip compatibility verdict (VP3D Phase 9, backlog 6)."""

    APPROVED = "APPROVED"
    FAILED = "FAILED"
    NOT_TESTED = "NOT_TESTED"


class CorrectionBasis(str, Enum):
    """Basis of a manual correction (VP3D Phase 9, backlog 7)."""

    MANUAL = "MANUAL"
    AUTOMATED = "AUTOMATED"


class TtsCapabilityFeature(str, Enum):
    """Capability metadata a TTS provider advertises (stage_e Phase 10, backlog 1).

    Provider ports stay provider-neutral but surface *what* they can return so
    the orchestrator can plan the full audio DAG before fan-in. Feature flags
    cover the alignment-critical capabilities: whether the provider returns
    word, token, or phoneme timing and whether it supports emotion/sample-rate
    variation. A capability the provider does NOT advertise is never assumed;
    the forced-aligner is a separate adapter and never fabricates confidence.
    """

    WORD_TIMESTAMPS = "WORD_TIMESTAMPS"
    TOKEN_TIMESTAMPS = "TOKEN_TIMESTAMPS"
    PHONEME_TIMING = "PHONEME_TIMING"
    EMOTION = "EMOTION"
    MULTI_SAMPLE_RATE = "MULTI_SAMPLE_RATE"


class TtsMode(str, Enum):
    """TTS execution mode (stage_e Phase 10, backlog 1)."""

    LOCAL = "LOCAL"
    API = "API"


class AudioValidationIssueCode(str, Enum):
    """Typed fail-closed findings on a TTS output (stage_e Phase 10, backlog 4).

    An invalid output — wrong sample rate, wrong channel layout, zero/negative
    duration, an undecodable byte stream, a content-hash mismatch, or an
    unsupported locale — is NEVER published to the dialogue track.
    """

    SAMPLE_RATE_INVALID = "SAMPLE_RATE_INVALID"
    CHANNEL_LAYOUT_INVALID = "CHANNEL_LAYOUT_INVALID"
    ZERO_DURATION = "ZERO_DURATION"
    DECODE_FAILED = "DECODE_FAILED"
    CONTENT_HASH_MISMATCH = "CONTENT_HASH_MISMATCH"
    UNSUPPORTED_LOCALE = "UNSUPPORTED_LOCALE"


class LineTimingProposalType(str, Enum):
    """Typed proposal for a line longer than its shot (stage_e Phase 10, backlog 6).

    When a synthesized line does not fit the shot duration the system never
    silently cuts the sentence. It emits a typed proposal the producer resolves:
    extend the shot, shorten the text, change pacing, or escalate to human
    review. `HUMAN_REVIEW` is the default when no mechanical option is safe.
    """

    EXTEND_SHOT = "EXTEND_SHOT"
    SHORTEN_TEXT = "SHORTEN_TEXT"
    CHANGE_PACING = "CHANGE_PACING"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class AudioNodeStatus(str, Enum):
    """Lifecycle of one audio DAG node (stage_e Phase 10, backlog 7 & 8).

    `REUSED` marks a node whose completed audio was reused after a worker
    restart instead of being re-synthesized (resume semantics). `CANCELLED`
    marks a node cancelled by the per-provider cancellation policy; a cancelled
    node never publishes a partial file.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    REUSED = "REUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TransformUnit(str, Enum):
    """Canonical transform unit for compiled objects (stage_f Phase 11)."""

    METERS = "METERS"
    CENTIMETERS = "CENTIMETERS"
    BLENDER_UNITS = "BLENDER_UNITS"


class BpyOpCode(str, Enum):
    """Closed allow-list of trusted bpy operations the transcriber may emit.

    stage_f §3/§4: compiler only uses the allow-list; no eval/exec of text from
    model or asset metadata. `RUN_ARBITRARY_PY` / `MODULE_IMPORT` / `EXEC_TEXT`
    are declared for completeness but are NEVER produced by the transcriber and
    fail closed if encountered on input.
    """

    NEW_SCENE = "NEW_SCENE"
    CREATE_COLLECTION = "CREATE_COLLECTION"
    CREATE_OBJECT = "CREATE_OBJECT"
    ADD_CAMERA = "ADD_CAMERA"
    ADD_LIGHT = "ADD_LIGHT"
    ADD_ANIMATION = "ADD_ANIMATION"
    SET_FRAME_RANGE = "SET_FRAME_RANGE"
    SET_RENDER_CONFIG = "SET_RENDER_CONFIG"
    SAVE_BLEND = "SAVE_BLEND"
    # never emitted; reserved to make the boundary explicit
    RUN_ARBITRARY_PY = "RUN_ARBITRARY_PY"
    MODULE_IMPORT = "MODULE_IMPORT"
    EXEC_TEXT = "EXEC_TEXT"


class CompileStatus(str, Enum):
    """Outcome of an incremental compile decision (stage_f Phase 11, backlog 7)."""

    REUSED = "REUSED"
    BUILT = "BUILT"
    BUILT_DEPENDENT = "BUILT_DEPENDENT"


class PlanAffected(str, Enum):
    """Which plans a changed input field invalidates (stage_f Phase 11, backlog 7)."""

    ALL = "ALL"
    OBJECT = "OBJECT"
    ANIMATION = "ANIMATION"
    UNKNOWN = "UNKNOWN"


class AnimationAction(str, Enum):
    """Library actions (stage_h §3 backlog 2 — the minimal 13-clip library)."""

    IDLE = "IDLE"
    WALK = "WALK"
    RUN = "RUN"
    JUMP = "JUMP"
    SIT = "SIT"
    STAND = "STAND"
    TALK = "TALK"
    LAUGH = "LAUGH"
    CRY = "CRY"
    POINT = "POINT"
    WAVE = "WAVE"
    PICK_UP = "PICK_UP"
    PUT_DOWN = "PUT_DOWN"


class AnimationEmotion(str, Enum):
    """Emotional flavor on an intent/clip (stage_h §3 backlog 3)."""

    NEUTRAL = "NEUTRAL"
    HAPPY = "HAPPY"
    SAD = "SAD"
    ANGRY = "ANGRY"
    FEARFUL = "FEARFUL"
    SURPRISED = "SURPRISED"
    EXCITED = "EXCITED"
    CALM = "CALM"


class ClipSource(str, Enum):
    """Provenance source of a clip (stage_h §1/§3 backlog 1)."""

    LIBRARY = "LIBRARY"
    MOCAP_CAPTURE = "MOCAP_CAPTURE"
    PROCEDURAL = "PROCEDURAL"          # Phase 16
    AI_MOTION = "AI_MOTION"            # Phase 17


class ProceduralLayerKind(str, Enum):
    """Procedural animation layers (stage_h §4 backlog 1)."""

    LOOK_AT = "LOOK_AT"
    HEAD_TRACKING = "HEAD_TRACKING"
    EYE_TRACKING = "EYE_TRACKING"
    HAND_IK = "HAND_IK"
    FOOT_IK = "FOOT_IK"
    PATH_FOLLOW = "PATH_FOLLOW"
    OBJECT_GRAB = "OBJECT_GRAB"
    SITTING_ALIGNMENT = "SITTING_ALIGNMENT"
    TURNING = "TURNING"
    IDLE_VARIATION = "IDLE_VARIATION"


class MotionOutputFormat(str, Enum):
    """AI motion output formats (stage_h §5 backlog 1 capability contract)."""

    FBX = "FBX"
    GLTF = "GLTF"
    BVH = "BVH"
    RAW_JSON = "RAW_JSON"


class MotionCandidateStatus(str, Enum):
    """Lifecycle of one AI motion candidate (stage_h §5 backlog 6)."""

    QUARANTINED = "QUARANTINED"
    REMAPPED = "REMAPPED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MotionRetryKind(str, Enum):
    """Retry cause classification (stage_h §5 backlog 6)."""

    TRANSIENT_PROVIDER = "TRANSIENT_PROVIDER"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"


# ---------------------------------------------------------------------------
# Stage I Facial Animation (VP3D Phase 18 — Lip-sync / Facial Pipeline)
# ---------------------------------------------------------------------------
class VisemeShape(str, Enum):
    """Mouth shape classes used by the viseme map (stage_i §3 backlog 2)."""

    NEUTRAL = "NEUTRAL"
    AA = "AA"  # open vowel a
    E = "E"  # spread vowel e/i
    I = "I"  # narrow spread i  # noqa: E741
    O = "O"  # rounded o  # noqa: E741
    U = "U"  # rounded u
    M_B_P = "M_B_P"  # bilabial closure
    F_V = "F_V"  # labiodental
    T_D_S = "T_D_S"  # alveolar tongue
    K_G = "K_G"  # velar
    L_N = "L_N"  # lateral/nasal
    R = "R"
    W_Q = "W_Q"
    CLOSED = "CLOSED"  # mouth closed (silence / rest)


class FacialLayerKind(str, Enum):
    """Layer ownership classes inside a facial track (stage_i backlog 6)."""

    LIP_SYNC = "LIP_SYNC"
    EMOTION = "EMOTION"
    BLINK = "BLINK"
    GAZE = "GAZE"
    EYEBROW = "EYEBROW"
    HEAD_MOTION = "HEAD_MOTION"


class FacialTrackStatus(str, Enum):
    """Status of a compiled/validated facial track (stage_i §4)."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    REJECTED = "REJECTED"


class HeadBlendPolicy(str, Enum):
    """How facial head motion blends with body animation (stage_i backlog 6)."""

    FACIAL_OWNS_HEAD = "FACIAL_OWNS_HEAD"
    BLEND_LIMITED = "BLEND_LIMITED"
    BODY_OWNS_HEAD = "BODY_OWNS_HEAD"


class FacialFindingKind(str, Enum):
    """Facial validation finding classes (stage_i §4 matrix)."""

    NON_MONOTONIC = "NON_MONOTONIC"
    OUT_OF_SHOT_RANGE = "OUT_OF_SHOT_RANGE"
    DRIFT_EXCEEDED = "DRIFT_EXCEEDED"
    LOW_CONFIDENCE_ALIGNMENT = "LOW_CONFIDENCE_ALIGNMENT"
    RIG_CONTROL_MISSING = "RIG_CONTROL_MISSING"
    SILENCE_MOUTH_MOVEMENT = "SILENCE_MOUTH_MOVEMENT"
    FACIAL_POP = "FACIAL_POP"
    IDLE_SPEECH = "IDLE_SPEECH"
    HEAD_JOINT_LIMIT_EXCEEDED = "HEAD_JOINT_LIMIT_EXCEEDED"
    EMOTION_ARTICULATION_OVERLAP = "EMOTION_ARTICULATION_OVERLAP"
    UNKNOWN_PHONEME_NO_RULE = "UNKNOWN_PHONEME_NO_RULE"


class FacialRepairScope(str, Enum):
    """Per-layer repair scope (stage_i backlog 8)."""

    LIP_SYNC = "LIP_SYNC"
    GAZE = "GAZE"
    EMOTION = "EMOTION"
    BLINK = "BLINK"
    HEAD_MOTION = "HEAD_MOTION"


class FacialInvalidationScope(str, Enum):
    """Downstream invalidation breadth after a repair (stage_i backlog 8)."""

    TRACK_LAYER_ONLY = "TRACK_LAYER_ONLY"
    TRACK_AND_RENDER_FINAL = "TRACK_AND_RENDER_FINAL"


# ---------------------------------------------------------------------------
# Stage M End-to-End (VP3D Phase 25 — Golden Scene)
# ---------------------------------------------------------------------------
class GoldenSceneNodeKind(str, Enum):
    """The ten pipeline nodes of the golden scene run (stage_m.md §3)."""

    SCRIPT = "SCRIPT"
    IR = "IR"
    ASSETS = "ASSETS"
    SCENE = "SCENE"
    ANIMATION_AUDIO = "ANIMATION_AUDIO"
    FACIAL = "FACIAL"
    RENDER = "RENDER"
    REVIEW_REPAIR = "REVIEW_REPAIR"
    FFMPEG = "FFMPEG"
    FINAL = "FINAL"


class GoldenSceneNodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class GoldenSceneVerdict(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"


# ---------------------------------------------------------------------------
# Stage M End-to-End (VP3D Phase 26 — Multi-Scene Episode)
# ---------------------------------------------------------------------------
class EpisodeVerdict(str, Enum):
    """Verdict of a multi-scene episode production run (stage_m.md §4)."""

    PASS = "PASS"
    REJECT = "REJECT"


class EpisodeArtifactKind(str, Enum):
    """Kinds of artifacts the episode run produces or reuses (backlog 1)."""

    CHARACTER_ASSET = "CHARACTER_ASSET"
    ENVIRONMENT_ASSET = "ENVIRONMENT_ASSET"
    ANIMATION_CLIP = "ANIMATION_CLIP"
    AUDIO_ASSET = "AUDIO_ASSET"
    SCENE_PLAN = "SCENE_PLAN"
    RENDER_FRAMES = "RENDER_FRAMES"
    REVIEW_REPORT = "REVIEW_REPORT"
    SCENE_MEDIA = "SCENE_MEDIA"
    EPISODE_MEDIA = "EPISODE_MEDIA"


class EpisodeCacheDecision(str, Enum):
    """Asset cache decisions (backlog 6): hit / miss / invalidated / rejected."""

    HIT = "HIT"
    MISS = "MISS"
    INVALIDATED = "INVALIDATED"
    REJECTED_REUSE = "REJECTED_REUSE"


class EpisodeChunkStatus(str, Enum):
    """Render chunk lifecycle (backlog 4 — kill/resume granularity)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class EpisodeBranchKind(str, Enum):
    """Parallel branch kinds (backlog 3 — critical path / idle)."""

    ASSET_PREP = "ASSET_PREP"
    AUDIO_PREP = "AUDIO_PREP"
    SCENE_COMPILE = "SCENE_COMPILE"
    RENDER = "RENDER"
    REVIEW_REPAIR = "REVIEW_REPAIR"
    POST_PRODUCTION = "POST_PRODUCTION"


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
    "ProductionAssetKind",
    "AssetProcessingState",
    "DirectorialIssueCategory",
    "IssueSeverity",
    "ProposalStatus",
    "RequiredArtifactType",
    "CameraAngle",
    "CameraSide",
    "ScreenDirection",
    "EasingKind",
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
    "FrameSequenceIssueCode",
    "MixTrackKind",
    "AssemblyInvalidationScope",
    "SemanticBone",
    "RigValidationIssueCode",
    "RigStatus",
    "DeformationMetric",
    "CompatibilityVerdict",
    "CorrectionBasis",
    "TtsCapabilityFeature",
    "TtsMode",
    "AudioValidationIssueCode",
    "LineTimingProposalType",
    "AudioNodeStatus",
    "TransformUnit",
    "BpyOpCode",
    "CompileStatus",
    "PlanAffected",
    # Stage H Animation (VP3D Phase 15)
    "AnimationAction",
    "AnimationEmotion",
    "ClipSource",
    # Stage H Animation (VP3D Phase 16)
    "ProceduralLayerKind",
    # Stage H AI Motion Adapter (VP3D Phase 17)
    "MotionOutputFormat",
    "MotionCandidateStatus",
    "MotionRetryKind",
    # Stage I Facial Animation (VP3D Phase 18)
    "VisemeShape",
    "FacialLayerKind",
    "FacialTrackStatus",
    "HeadBlendPolicy",
    "FacialFindingKind",
    "FacialRepairScope",
    "FacialInvalidationScope",
    # Stage M End-to-End (VP3D Phase 25 — Golden Scene)
    "GoldenSceneNodeKind",
    "GoldenSceneNodeStatus",
    "GoldenSceneVerdict",
    # Stage M End-to-End (VP3D Phase 26 — Multi-Scene Episode)
    "EpisodeVerdict",
    "EpisodeArtifactKind",
    "EpisodeCacheDecision",
    "EpisodeChunkStatus",
    "EpisodeBranchKind",
]
