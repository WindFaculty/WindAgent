"""
Character Master asset system (stage_d.md Phase 8).

A `CharacterMaster` is the canonical, versioned home for one character's 3D
asset definition: canonical mesh (`CharacterGeometryProfile`), skeleton wiring,
facial rig, materials/textures, proportions, voice profile, approved animation
sets and art-direction style fingerprint. A character used across many
episodes ALWAYS shares the same `CharacterMasterId` — it is never regenerated
per shot (road_map.md Stage D; stage_d.md §1, §3).

Design rules enforced here:
  - IDs are stable and opaque (`CharacterMasterId`); a rename never changes it.
  - Master *revisions* are immutable once bound. `CharacterInstance` in the
    Production IR references a pinned revision, not a mutable master. A locked
    episode keeps pinning the old revision; installing a new revision only
    invalidates dependent scenes/shots (backlog 7).
  - Approval is human + revision-bound and fail-closed: unapproved assets are
    never reusable, and a REJECTED revision cannot silently promote itself.
  - Geometry/topology change invalidates the facial rig, and any material /
    topology / palette change must be reconciled against the style
    fingerprint before reuse (stage_d.md §6 risks).

Models are immutable (ConfigDict frozen) so a bound revision cannot drift.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    CharacterApprovalVerdict,
    CharacterMasterState,
    CharacterRole,
)
from windagent_core.domain.video_production.ids import (
    AnimationProfileId,
    CharacterGeometryProfileId,
    CharacterId,
    CharacterMasterId,
    CharacterMasterRevisionId,
    CharacterMaterialProfileId,
    CharacterProportionProfileId,
    CharacterVoiceProfileId,
    FacialRigProfileId,
    StyleFingerprintId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Valid transitions: source -> allowed targets.
_TRANSITIONS: Dict[CharacterMasterState, FrozenSet[CharacterMasterState]] = {
    CharacterMasterState.DRAFT: frozenset({CharacterMasterState.NORMALIZED}),
    CharacterMasterState.NORMALIZED: frozenset({CharacterMasterState.RIGGED}),
    CharacterMasterState.RIGGED: frozenset({CharacterMasterState.VALIDATED}),
    CharacterMasterState.VALIDATED: frozenset({CharacterMasterState.APPROVED}),
    # A RETIRED revision may be superseded by a fresh revision, but it can never
    # return to production (locked episodes continue pinning the retired one).
    CharacterMasterState.APPROVED: frozenset({CharacterMasterState.RETIRED}),
    CharacterMasterState.RETIRED: frozenset(),
}


class CharacterGeometryProfile(BaseModel):
    """Canonical mesh definition (backlog 3).

    `source_hash` is the content hash of the canonical mesh asset. It anchors
    topology changes: any new source_hash represents a geometry change that
    invalidates the facial rig (stage_d.md §6 risk 2).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: CharacterGeometryProfileId
    source_hash: str = Field(min_length=1)
    vertex_count: int = Field(ge=0)
    poly_count: int = Field(ge=0)
    unit: str = "1 unit = 1 meter"
    z_up: bool = True
    bounds: Dict[str, float] = Field(default_factory=dict)
    polycount_target: float = Field(default=1.0, gt=0)
    quality: str = "base"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CharacterMaterialProfile(BaseModel):
    """Materials and textures for the character (backlog 3)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: CharacterMaterialProfileId
    material_names: List[str] = Field(default_factory=list)
    texture_hashes: Dict[str, str] = Field(default_factory=dict)
    palette_hash: str = Field(min_length=1)
    pbr: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CharacterProportionProfile(BaseModel):
    """Body proportions (backlog 3). Density checks depend on these."""

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: CharacterProportionProfileId
    height_units: float = Field(default=1.8, gt=0)
    scale: float = Field(default=1.0, gt=0)
    proportions: Dict[str, float] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FacialRigProfile(BaseModel):
    """Facial rig controls (backlog 3).

    Bound to the `geometry_hash` they were validated against. If the geometry
    source_hash changes, facial rigs authored for the old topology are
    invalidated (stage_d.md §6 risk 2) — callers must re-author or re-validate.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: FacialRigProfileId
    control_names: List[str] = Field(default_factory=list)
    topology_hash: str = Field(default="")
    lipsync_mapping_version: str = Field(default="1.0")
    valid: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def invalidated_by_topology(self, source_hash: str) -> bool:
        """Return True if this facial rig is invalid for the given geometry."""
        return self.topology_hash != "" and self.topology_hash != source_hash


class AnimationProfile(BaseModel):
    """Approved animation set for a character (backlog 3, backlog 6).

    Only clips pass fail-closed checks (Phase 9 gate) enter the approved set.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: AnimationProfileId
    approved_clips: List[str] = Field(default_factory=list)
    clip_manifest_hash: str = Field(min_length=1)
    retarget_readiness: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StyleFingerprint(BaseModel):
    """Art-direction style fingerprint (backlog 3, backlog 6).

    Reuse lookup by style/compatibility is only allowed when the fingerprint
    matches AND a human approval is recorded (`approved_by`). A reuse that
    preserves identity but breaks art direction is forbidden without it
    (stage_d.md §6 risk 3).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    fingerprint_id: StyleFingerprintId
    style_key: str = Field(min_length=1)
    palette_signature: str = Field(min_length=1)
    silhouette_signature: str = Field(min_length=1)
    approved_by: str = ""
    approved_at: Optional[datetime] = None

    @property
    def approved(self) -> bool:
        return bool(self.approved_by)


class CharacterMasterRevision(BaseModel):
    """One immutable snapshot of a character's canonical asset definition.

    `instance` in the Production IR references `revision_id`, never a mutable
    master. Content is pinned by the constituent profile ids + hashes.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    revision_id: CharacterMasterRevisionId
    master_id: CharacterMasterId
    revision_number: int = Field(ge=0, default=0)
    state: CharacterMasterState = CharacterMasterState.DRAFT
    role: CharacterRole = CharacterRole.SUPPORTING
    name: str = ""
    geometry: Optional[CharacterGeometryProfile] = None
    materials: Optional[CharacterMaterialProfile] = None
    proportions: Optional[CharacterProportionProfile] = None
    facial_rig: Optional[FacialRigProfile] = None
    animation: Optional[AnimationProfile] = None
    style: Optional[StyleFingerprint] = None
    voice_profile_id: Optional[CharacterVoiceProfileId] = None
    approval_verdict: CharacterApprovalVerdict = CharacterApprovalVerdict.PENDING
    approval_actor: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    invalidates_scenes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        """Deterministic hash over the revision's pinned asset identity.

        Re-run on identical inputs yields the same hash — the Phase 8
        retarget/action-manifest determinism property (stage_d.md §5).
        """
        canonical = json.dumps(
            {
                "master_id": str(self.master_id),
                "revision_number": self.revision_number,
                "name": self.name,
                "geometry_hash": self.geometry.source_hash if self.geometry else "",
                "topology_hash": self.facial_rig.topology_hash if self.facial_rig else "",
                "palette": self.materials.palette_hash if self.materials else "",
                "proportions": self.proportions.proportions if self.proportions else {},
                "approved_clips": self.animation.approved_clips if self.animation else [],
                "style_key": self.style.style_key if self.style else "",
                "voice_profile_id": str(self.voice_profile_id or ""),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return _sha256(canonical.encode("utf-8"))

    def with_state(self, state: CharacterMasterState, *, actor: str = "") -> "CharacterMasterRevision":
        """Return a new immutable revision at the given lifecycle state."""
        return self.model_copy(update={"state": state, "approval_actor": actor})


class CharacterMaster(BaseModel):
    """The versioned aggregate for one character.

    Holds the stable `master_id`, the currently active revision, and the
    complete approved history. `retired_pins` maps episode/scene keys to the
    revision they are pinned to, so a locked episode continues using a retired
    revision without mutation (backlog 7).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    master_id: CharacterMasterId
    character_bible_id: Optional[CharacterId] = None  # source Creative input (backlog 1)
    name: str = ""
    role: CharacterRole = CharacterRole.SUPPORTING
    active_revision_id: Optional[CharacterMasterRevisionId] = None
    revisions: List[CharacterMasterRevision] = Field(default_factory=list)
    episode_pins: Dict[str, CharacterMasterRevisionId] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def revision(self, revision_id: CharacterMasterRevisionId) -> Optional[CharacterMasterRevision]:
        for rev in self.revisions:
            if rev.revision_id == revision_id:
                return rev
        return None

    def active_revision(self) -> Optional[CharacterMasterRevision]:
        if self.active_revision_id is None:
            return None
        return self.revision(self.active_revision_id)

    def approved_revisions(self) -> List[CharacterMasterRevision]:
        return [
            rev
            for rev in self.revisions
            if rev.state == CharacterMasterState.APPROVED
            and rev.approval_verdict == CharacterApprovalVerdict.APPROVED
        ]

    def pin_episode(self, episode_key: str) -> Optional[CharacterMasterRevision]:
        """Pin the active revision for a locked episode, or resolve an old pin.

        If the episode already has a pin, return the pinned revision unchanged
        (immutable continuity). Otherwise pin the current active revision.
        """
        existing = self.episode_pins.get(episode_key)
        if existing is not None:
            return self.revision(existing)
        if self.active_revision_id is None:
            return None
        # Immutable aggregate: this is a read-side fixture helper. Callers that
        # need to actually mutate the pin set a new CharacterMaster via
        # `with_pin` (below) so history is never silently rewritten.
        return self.revision(self.active_revision_id)

    def with_pin(self, episode_key: str) -> "CharacterMaster":
        """Return a new master with the active revision pinned to `episode_key`."""
        if self.active_revision_id is None:
            return self
        pins = dict(self.episode_pins)
        pins[episode_key] = self.active_revision_id
        return self.model_copy(update={"episode_pins": pins})


class CharacterMasterStateMachine:
    """Pure transition rules for the CharacterMaster lifecycle (backlog 2)."""

    @staticmethod
    def allowed_transitions(state: CharacterMasterState) -> FrozenSet[CharacterMasterState]:
        return _TRANSITIONS[state]

    @classmethod
    def can_transition(cls, current: CharacterMasterState, target: CharacterMasterState) -> bool:
        return target in _TRANSITIONS[current]

    @classmethod
    def require_transition(cls, current: CharacterMasterState, target: CharacterMasterState) -> None:
        if not cls.can_transition(current, target):
            from windagent_core.domain.video_production.errors import (
                VideoProductionProtocolError,
            )

            raise VideoProductionProtocolError(
                f"Illegal character master transition {current.value} -> {target.value}.",
                details={"current": current.value, "target": target.value},
            )


class CharacterMasterApprovalService:
    """Human approval that is revision-bound and fail-closed (backlog 6, §5).

    An unapproved revision is never reusable. A rejected revision cannot be
    silently approved by a later automated pass.
    """

    @staticmethod
    def approve(revision: CharacterMasterRevision, *, actor: str) -> CharacterMasterRevision:
        if revision.state != CharacterMasterState.VALIDATED:
            raise _protocol(f"Cannot approve a revision in {revision.state.value}; must be VALIDATED.")
        if revision.approval_verdict == CharacterApprovalVerdict.REJECTED:
            raise _protocol("Rejected revision cannot be silently re-approved; author a fresh revision.")
        if not actor.strip():
            raise _protocol("Approval requires a named human actor.")
        CharacterMasterStateMachine.require_transition(
            revision.state, CharacterMasterState.APPROVED
        )
        return revision.model_copy(
            update={
                "state": CharacterMasterState.APPROVED,
                "approval_verdict": CharacterApprovalVerdict.APPROVED,
                "approval_actor": actor,
            }
        )

    @staticmethod
    def reject(revision: CharacterMasterRevision, *, actor: str) -> CharacterMasterRevision:
        if not actor.strip():
            raise _protocol("Rejection requires a named human actor.")
        return revision.model_copy(
            update={
                "approval_verdict": CharacterApprovalVerdict.REJECTED,
                "approval_actor": actor,
            }
        )


class CharacterMasterFactory:
    """Pure creation + revision logic (backlog 6, 7).

    Generation only happens when no compatible approved master exists or the
    user explicitly requests a new revision (backlog 6). Installing a new
    revision invalidates only the scenes it breaks (backlog 7).
    """

    @staticmethod
    def find_compatible(
        masters: List[CharacterMaster],
        *,
        style_key: str,
        palette_signature: str,
    ) -> Optional[CharacterMaster]:
        """Find a reusable approved master matching the requested style."""
        compatible = []
        for master in masters:
            for rev in master.approved_revisions():
                if (
                    rev.style is not None
                    and rev.style.style_key == style_key
                    and rev.style.palette_signature == palette_signature
                    and rev.style.approved
                ):
                    compatible.append(master)
                    break
        return compatible[0] if compatible else None

    @staticmethod
    def install_revision(
        master: CharacterMaster,
        revision: CharacterMasterRevision,
        *,
        invalidated_scenes: List[str],
    ) -> CharacterMaster:
        """Append a new revision as the active one, invalidating only targets.

        The invalidation scope is stamped onto the installed revision and stays
        immutable (backlog 7): replacing a master revision invalidates only the
        scenes/shots that depend on the changed content, and nothing else.
        """
        existing = master.revision(revision.revision_id)
        if existing is not None:
            return master  # idempotent: same revision id already installed
        if revision.invalidates_scenes != invalidated_scenes:
            revision = revision.model_copy(
                update={"invalidates_scenes": list(invalidated_scenes)}
            )
        updates = {
            "revisions": list(master.revisions) + [revision],
            "active_revision_id": revision.revision_id,
        }
        return master.model_copy(update=updates)

    @staticmethod
    def link_to_bible(master: CharacterMaster, *, bible_id: CharacterId) -> CharacterMaster:
        """Record the CharacterBible as the creative input for this master (backlog 1).

        `CharacterBible` stays the creative reference (design intent, costume
        descriptions, visual traits); the master is the approved 3D asset. The
        link is identity-only — no mesh/rig data is copied from the bible.
        """
        return master.model_copy(update={"character_bible_id": bible_id})

    @staticmethod
    def find_by_bible(
        masters: List[CharacterMaster], bible_id: CharacterId
    ) -> Optional[CharacterMaster]:
        """Resolve a master from its source bible id (stable identity)."""
        for master in masters:
            if master.character_bible_id == bible_id:
                return master
        return None



def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _protocol(message: str):
    from windagent_core.domain.video_production.errors import VideoProductionProtocolError

    return VideoProductionProtocolError(message)


__all__ = [
    "CharacterGeometryProfile",
    "CharacterMaterialProfile",
    "CharacterProportionProfile",
    "FacialRigProfile",
    "AnimationProfile",
    "StyleFingerprint",
    "CharacterMasterRevision",
    "CharacterMaster",
    "CharacterMasterStateMachine",
    "CharacterMasterApprovalService",
    "CharacterMasterFactory",
]
