"""
Canonical Story artifact identifiers (studio.artifact/v1alpha1).

Every identifier is an opaque stable string, never derived from a display name
or user input. Canon IDs are NEW Story IDs: they map to downstream production
only after Roadmap 1 (Plan B phase B4 rule) and never collide with VP3D IDs.
"""

from __future__ import annotations

from windagent_core.domain.types import OpaqueId
from windagent_core.domain.video_production.ids import CreativeBriefId, DialogueLineId

__all__ = [
    "CreativeBriefId",
    "DialogueLineId",
    "SelectedIdeaId",
    "StoryBibleId",
    "WorldBibleId",
    "StoryCharacterId",
    "StoryLocationId",
    "StoryPropId",
    "BeatSheetId",
    "BeatId",
    "EpisodeOutlineId",
    "OutlineSceneId",
    "ScreenplayDraftId",
    "DraftSceneId",
    "ReviewReportId",
    "RevisionProposalId",
    "LockedScreenplayReceiptId",
    "LockedScreenplayPackageId",
]


class SelectedIdeaId(OpaqueId):
    """Identifier for a SelectedIdea artifact."""


class StoryBibleId(OpaqueId):
    """Identifier for a StoryBible artifact."""


class WorldBibleId(OpaqueId):
    """Identifier for a WorldBible artifact."""


class StoryCharacterId(OpaqueId):
    """Canonical character ID (Plan B canon identity; distinct from VP3D CharacterId)."""


class StoryLocationId(OpaqueId):
    """Canonical recurring-location ID inside a WorldBible."""


class StoryPropId(OpaqueId):
    """Canonical recurring-object/prop ID inside a WorldBible."""


class BeatSheetId(OpaqueId):
    """Identifier for a BeatSheet artifact."""


class BeatId(OpaqueId):
    """Identifier for a single beat inside a BeatSheet."""


class EpisodeOutlineId(OpaqueId):
    """Identifier for an EpisodeOutline artifact."""


class OutlineSceneId(OpaqueId):
    """Identifier for a scene inside an EpisodeOutline."""


class ScreenplayDraftId(OpaqueId):
    """Identifier for a structured ScreenplayDraft artifact."""


class DraftSceneId(OpaqueId):
    """Identifier for a scene inside a ScreenplayDraft."""


class ReviewReportId(OpaqueId):
    """Identifier for a ReviewReport artifact."""


class RevisionProposalId(OpaqueId):
    """Identifier for a RevisionProposal artifact."""


class LockedScreenplayReceiptId(OpaqueId):
    """Identifier for a LockedScreenplayReceipt artifact (A-issued)."""


class LockedScreenplayPackageId(OpaqueId):
    """Identifier for a LockedScreenplayPackage artifact."""
