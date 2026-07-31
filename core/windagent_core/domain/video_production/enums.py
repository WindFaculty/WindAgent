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


class GenerationMode(str, Enum):
    """Canonical media generation modes (road_map.md Phase 9)."""

    TEXT_TO_VIDEO = "TEXT_TO_VIDEO"
    IMAGE_TO_VIDEO = "IMAGE_TO_VIDEO"
    FRAMES_TO_VIDEO = "FRAMES_TO_VIDEO"
    INGREDIENTS_TO_VIDEO = "INGREDIENTS_TO_VIDEO"
    VIDEO_EXTENSION = "VIDEO_EXTENSION"
    VIDEO_TO_VIDEO = "VIDEO_TO_VIDEO"
    TEXT_TO_IMAGE = "TEXT_TO_IMAGE"


class AssetSourceType(str, Enum):
    """Origin of a ReferenceAsset."""

    GENERATED = "GENERATED"
    INTERNET = "INTERNET"
    UPLOADED = "UPLOADED"
    PROVIDER = "PROVIDER"


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
    "GenerationMode",
    "AssetSourceType",
    "LicenseState",
    "GenerationStatus",
    "ReviewVerdict",
    "ApprovalRole",
    "ApprovalDecisionType",
    "MediaType",
]
