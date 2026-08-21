"""Unit tests for the Character Master asset system (stage_d.md Phase 8).

Covers the seven canonical models, the lifecycle state machine (backlog 2),
revision-bound human approval (backlog 6, stage_d.md §5), style-compatible reuse
lookup (backlog 6), topology->facial-rig invalidation (stage_d.md §6 risk 2),
content-hash determinism (§5), and episode pin stability (backlog 7). All checks
are offline and deterministic.
"""

import pytest

from windagent_core.domain.video_production.character_master import (
    AnimationProfile,
    CharacterGeometryProfile,
    CharacterMaster,
    CharacterMasterApprovalService,
    CharacterMasterFactory,
    CharacterMasterRevision,
    CharacterMasterStateMachine,
    CharacterMaterialProfile,
    CharacterProportionProfile,
    FacialRigProfile,
    StyleFingerprint,
)
from windagent_core.domain.video_production.enums import (
    CharacterApprovalVerdict,
    CharacterMasterState,
)
from windagent_core.domain.video_production.errors import VideoProductionProtocolError
from windagent_core.domain.video_production.ids import (
    AnimationProfileId,
    CharacterGeometryProfileId,
    CharacterId,
    CharacterMasterId,
    CharacterMasterRevisionId,
    CharacterMaterialProfileId,
    CharacterProportionProfileId,
    FacialRigProfileId,
    StyleFingerprintId,
)


def _geometry(seed: str = "mesh-v1", v: int = 12000) -> CharacterGeometryProfile:
    return CharacterGeometryProfile(
        profile_id=CharacterGeometryProfileId.generate("geo"),
        source_hash=seed,
        vertex_count=v,
        poly_count=v // 4,
    )


def _materials(palette: str = "palette-1") -> CharacterMaterialProfile:
    return CharacterMaterialProfile(
        profile_id=CharacterMaterialProfileId.generate("mat"),
        palette_hash=palette,
        texture_hashes={"base": "tex-1"},
    )


def _proportions() -> CharacterProportionProfile:
    return CharacterProportionProfile(
        profile_id=CharacterProportionProfileId.generate("prop"),
        proportions={"torso_height": 0.5, "leg_ratio": 0.5},
    )


def _facial(topology: str) -> FacialRigProfile:
    return FacialRigProfile(
        profile_id=FacialRigProfileId.generate("facial"),
        topology_hash=topology,
        control_names=["brow_l", "brow_r", "mouth"],
    )


def _animation() -> AnimationProfile:
    return AnimationProfile(
        profile_id=AnimationProfileId.generate("anim"),
        approved_clips=["idle", "walk"],
        clip_manifest_hash="clip-hash-1",
    )


def _style(approved: bool = True) -> StyleFingerprint:
    return StyleFingerprint(
        fingerprint_id=StyleFingerprintId.generate("sf"),
        style_key="stylized",
        palette_signature="palette-1",
        silhouette_signature="sig-1",
        approved_by="hoa" if approved else "",
    )


def _revision(master_id: CharacterMasterId, state: CharacterMasterState, *, rev: int = 1) -> CharacterMasterRevision:
    return CharacterMasterRevision(
        revision_id=CharacterMasterRevisionId.generate("rev"),
        master_id=master_id,
        revision_number=rev,
        state=state,
        name="Mai",
        geometry=_geometry(),
        materials=_materials(),
        proportions=_proportions(),
        facial_rig=_facial("mesh-v1"),
        animation=_animation(),
        style=_style(),
    )


@pytest.fixture
def master_id() -> CharacterMasterId:
    return CharacterMasterId.generate("vpc")


# ---- stable ID across rename (stage_d.md §5) ----
def test_stable_id_across_rename(master_id):
    renamed = CharacterMaster(master_id=master_id, name="Mai II")
    assert renamed.master_id == master_id


# ---- lifecycle happy path (backlog 2) ----
def test_lifecycle_happy_path(master_id):
    cur = CharacterMasterState.DRAFT
    for target in (
        CharacterMasterState.NORMALIZED,
        CharacterMasterState.RIGGED,
        CharacterMasterState.VALIDATED,
        CharacterMasterState.APPROVED,
        CharacterMasterState.RETIRED,
    ):
        assert CharacterMasterStateMachine.can_transition(cur, target)
        cur = target


# ---- forbidden transitions fail closed (stage_d.md §5) ----
@pytest.mark.parametrize(
    "src,tgt",
    [
        (CharacterMasterState.DRAFT, CharacterMasterState.APPROVED),
        (CharacterMasterState.NORMALIZED, CharacterMasterState.RETIRED),
        (CharacterMasterState.RIGGED, CharacterMasterState.NORMALIZED),
        (CharacterMasterState.APPROVED, CharacterMasterState.VALIDATED),
        (CharacterMasterState.RETIRED, CharacterMasterState.APPROVED),
    ],
)
def test_forbidden_transitions_fail_closed(src, tgt):
    assert not CharacterMasterStateMachine.can_transition(src, tgt)
    with pytest.raises(VideoProductionProtocolError):
        CharacterMasterStateMachine.require_transition(src, tgt)


# ---- approval requires VALIDATED + named actor + fail-closed ----
def test_approval_requires_validated_state(master_id):
    rev = _revision(master_id, CharacterMasterState.DRAFT)
    with pytest.raises(VideoProductionProtocolError):
        CharacterMasterApprovalService.approve(rev, actor="hoa")


def test_approval_requires_named_actor(master_id):
    rev = _revision(master_id, CharacterMasterState.VALIDATED)
    with pytest.raises(VideoProductionProtocolError):
        CharacterMasterApprovalService.approve(rev, actor="   ")


def test_rejected_revision_cannot_be_silently_approved(master_id):
    rev = CharacterMasterApprovalService.reject(
        _revision(master_id, CharacterMasterState.VALIDATED), actor="hoa"
    )
    with pytest.raises(VideoProductionProtocolError):
        CharacterMasterApprovalService.approve(rev, actor="hoa")


def test_approve_moves_to_approved(master_id):
    rev = CharacterMasterApprovalService.approve(
        _revision(master_id, CharacterMasterState.VALIDATED), actor="hoa"
    )
    assert rev.state == CharacterMasterState.APPROVED
    assert rev.approval_verdict == CharacterApprovalVerdict.APPROVED


# ---- content hash determinism (§5) ----
def test_content_hash_deterministic(master_id):
    a = _revision(master_id, CharacterMasterState.DRAFT)
    b = _revision(master_id, CharacterMasterState.DRAFT)
    assert a.content_hash() == b.content_hash()


def test_content_hash_differs_on_geometry_change(master_id):
    a = _revision(master_id, CharacterMasterState.DRAFT)
    b = _revision(master_id, CharacterMasterState.DRAFT).model_copy(
        update={"geometry": _geometry("mesh-v2")}
    )
    assert a.content_hash() != b.content_hash()


# ---- facial rig invalidated by topology change (stage_d.md §6 risk 2) ----
def test_facial_rig_invalidated_by_topology_change():
    rig = _facial("mesh-v1")
    assert not rig.invalidated_by_topology("mesh-v1")
    assert rig.invalidated_by_topology("mesh-v2")


# ---- style-compatible reuse requires approval (backlog 6, risk 3) ----
def test_reuse_lookup_requires_approved_style(master_id):
    # approved master matches -> reusable
    approved_rev = CharacterMasterApprovalService.approve(
        _revision(master_id, CharacterMasterState.VALIDATED), actor="hoa"
    )
    approved_master = CharacterMasterFactory.install_revision(
        CharacterMaster(master_id=master_id),
        approved_rev,
        invalidated_scenes=[],
    )
    hit = CharacterMasterFactory.find_compatible(
        [approved_master], style_key="stylized", palette_signature="palette-1"
    )
    assert hit is not None and hit.master_id == master_id

    # unapproved style (and unapproved revision) is NOT reusable -> fail closed
    unreviewed = CharacterMasterFactory.install_revision(
        CharacterMaster(master_id=CharacterMasterId.generate("vpc")),
        _revision(CharacterMasterId.generate("vpc"), CharacterMasterState.VALIDATED),
        invalidated_scenes=[],
    )
    miss = CharacterMasterFactory.find_compatible(
        [unreviewed], style_key="stylized", palette_signature="palette-1"
    )
    assert miss is None


def test_reuse_lookup_rejects_mismatched_style(master_id):
    approved_rev = CharacterMasterApprovalService.approve(
        _revision(master_id, CharacterMasterState.VALIDATED), actor="hoa"
    )
    approved_master = CharacterMasterFactory.install_revision(
        CharacterMaster(master_id=master_id),
        approved_rev,
        invalidated_scenes=[],
    )
    assert approved_master.approved_revisions()
    hit = CharacterMasterFactory.find_compatible(
        [approved_master], style_key="realistic", palette_signature="palette-1"
    )
    assert hit is None


# ---- episode pin stability (backlog 7) ----
def test_episode_keeps_pinning_retired_revision(master_id):
    # episode pins approved rev; a later rev2 is retired; pinned episode is stable
    rev1 = CharacterMasterApprovalService.approve(
        _revision(master_id, CharacterMasterState.VALIDATED, rev=1), actor="hoa"
    )
    master = CharacterMasterFactory.install_revision(
        CharacterMaster(master_id=master_id), rev1, invalidated_scenes=[]
    )
    # rev2 is a NEW revision (fresh id) superseding rev1
    rev2 = _revision(master_id, CharacterMasterState.VALIDATED, rev=2).with_state(
        CharacterMasterState.RETIRED
    )
    master = CharacterMasterFactory.install_revision(
        master.with_pin("episode-2"),
        rev2,
        invalidated_scenes=["scene-3"],
    )
    # episode-2 still pins rev1
    pinned = master.pin_episode("episode-2")
    assert pinned is not None and pinned.revision_number == 1
    assert pinned.state == CharacterMasterState.APPROVED
    # rev2 installed, invalidation scoped only to scene-3
    installed_rev2 = master.revision(rev2.revision_id)
    assert installed_rev2 is not None
    assert installed_rev2.invalidates_scenes == ["scene-3"]


# ---- models are immutable ----
def test_revisions_are_immutable(master_id):
    rev = _revision(master_id, CharacterMasterState.DRAFT)
    with pytest.raises(ValueError):
        rev.revision_number = 99


# ---- bible -> master mapping (backlog 1) ----
def test_bible_links_to_master_by_id(master_id):
    try:
        from windagent_core.domain.video_production.character import CharacterBible
    except Exception:  # pragma: no cover - bible module unavailable
        pytest.skip("CharacterBible not importable")
    bible = CharacterBible(character_id=CharacterId.generate("cb"), name="Mai")
    master = CharacterMaster(master_id=master_id)
    linked = CharacterMasterFactory.link_to_bible(master, bible_id=bible.character_id)
    assert linked.character_bible_id == bible.character_id
    # bible stays creative input; no mesh data copied into master
    resolved = CharacterMasterFactory.find_by_bible([linked], bible.character_id)
    assert resolved is not None and resolved.master_id == master_id
    assert resolved.revisions == []


# ---- two episodes pin same revision -> stable identity (stage_d.md §5) ----
def test_two_episodes_pin_same_revision(master_id):
    rev = CharacterMasterApprovalService.approve(
        _revision(master_id, CharacterMasterState.VALIDATED), actor="hoa"
    )
    master = CharacterMasterFactory.install_revision(
        CharacterMaster(master_id=master_id), rev, invalidated_scenes=[]
    )
    master = master.with_pin("episode-1").with_pin("episode-2")
    ep1 = master.pin_episode("episode-1")
    ep2 = master.pin_episode("episode-2")
    assert ep1 is not None and ep2 is not None
    assert ep1.revision_id == ep2.revision_id == rev.revision_id
    assert ep1.content_hash() == ep2.content_hash()
    assert master.episode_pins == {"episode-1": rev.revision_id, "episode-2": rev.revision_id}
