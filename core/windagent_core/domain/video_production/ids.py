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
]
