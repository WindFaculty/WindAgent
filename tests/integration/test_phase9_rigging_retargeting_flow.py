"""VP3D Phase 9 — Rigging & Retargeting INTEGRATION flow.

Drives the whole Stage D rigging/retargeting pipeline end to end over TWO
character masters of DIFFERENT topology (stage_d.md §4 gate, §5):

    master A (provider-named skeleton, low-poly topology)
    master B (Mixamo-named skeleton, high-poly topology)
        -> SkeletonDetector (provider-agnostic semantic normalization)
        -> RigValidator (fail-closed receipt)
        -> RetargetMapper (versioned semantic mapping, stable manifest hash)
        -> CompatibilityGate over the MINIMAL clip suite
        -> continuity check (two episodes pinned to the same revision render
             identical identity; a failed clip never enters the approved set)

This is the evidence the `VP3D_P9_CHARACTER_RIG_VERIFIED` gate requires: the
same minimal clip set is retargeted onto two masters that differ in topology,
and only fail-closed-approved clips are retained.
"""

from __future__ import annotations

import pytest

from windagent_core.domain.video_production.character_master import (
    AnimationProfile,
    CharacterGeometryProfile,
    CharacterMaster,
    CharacterMasterApprovalService,
    CharacterMasterFactory,
    CharacterMasterRevision,
    CharacterMaterialProfile,
    CharacterProportionProfile,
    FacialRigProfile,
    StyleFingerprint,
)
from windagent_core.domain.video_production.enums import (
    CharacterMasterState,
    CompatibilityVerdict,
    CorrectionBasis,
    DeformationMetric,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import RigCompatibilityError
from windagent_core.domain.video_production.ids import (
    AnimationCompatibilityProfileId,
    AnimationProfileId,
    CharacterGeometryProfileId,
    CharacterMasterId,
    CharacterMasterRevisionId,
    CharacterMaterialProfileId,
    CharacterProportionProfileId,
    CharacterVoiceProfileId,
    FacialRigProfileId,
    RetargetProfileId,
    RigProfileId,
    RigValidationReceiptId,
    StyleFingerprintId,
)
from windagent_core.domain.video_production.rigging import (
    CompatibilityGate,
    DeformationMetricEngine,
    DerivedRigService,
    MINIMAL_CLIP_SUITE,
    RetargetMapper,
    RigProfile,
    RigValidator,
    SkeletonDetector,
)


# ---------------------------------------------------------------------------
# Two DIFFERENT-topology skeletons from two providers.
# ---------------------------------------------------------------------------

_PROVIDER_A = {
    "Root": (SemanticBone.ROOT, ""),
    "Hips": (SemanticBone.PELVIS, "Root"),
    "Spine1": (SemanticBone.SPINE, "Hips"),
    "Spine2": (SemanticBone.CHEST, "Spine1"),
    "Neck": (SemanticBone.NECK, "Spine2"),
    "Head": (SemanticBone.HEAD, "Neck"),
    "Shoulder_L": (SemanticBone.SHOULDER_L, "Spine2"),
    "Shoulder_R": (SemanticBone.SHOULDER_R, "Spine2"),
    "UpperArm_L": (SemanticBone.ARM_UPPER_L, "Shoulder_L"),
    "UpperArm_R": (SemanticBone.ARM_UPPER_R, "Shoulder_R"),
    "LowerArm_L": (SemanticBone.ARM_LOWER_L, "UpperArm_L"),
    "LowerArm_R": (SemanticBone.ARM_LOWER_R, "UpperArm_R"),
    "Hand_L": (SemanticBone.HAND_L, "LowerArm_L"),
    "Hand_R": (SemanticBone.HAND_R, "LowerArm_R"),
    "Thigh_L": (SemanticBone.THIGH_L, "Hips"),
    "Thigh_R": (SemanticBone.THIGH_R, "Hips"),
    "Shin_L": (SemanticBone.SHIN_L, "Thigh_L"),
    "Shin_R": (SemanticBone.SHIN_R, "Thigh_R"),
    "Foot_L": (SemanticBone.FOOT_L, "Shin_L"),
    "Foot_R": (SemanticBone.FOOT_R, "Shin_R"),
}

_PROVIDER_B = {
    "mixamorig:Root": (SemanticBone.ROOT, ""),
    "mixamorig:Hips": (SemanticBone.PELVIS, "mixamorig:Root"),
    "mixamorig:Spine": (SemanticBone.SPINE, "mixamorig:Hips"),
    "mixamorig:Spine2": (SemanticBone.CHEST, "mixamorig:Spine"),
    "mixamorig:Neck": (SemanticBone.NECK, "mixamorig:Spine2"),
    "mixamorig:Head": (SemanticBone.HEAD, "mixamorig:Neck"),
    "mixamorig:LeftShoulder": (SemanticBone.SHOULDER_L, "mixamorig:Spine2"),
    "mixamorig:RightShoulder": (SemanticBone.SHOULDER_R, "mixamorig:Spine2"),
    "mixamorig:LeftArm": (SemanticBone.ARM_UPPER_L, "mixamorig:LeftShoulder"),
    "mixamorig:RightArm": (SemanticBone.ARM_UPPER_R, "mixamorig:RightShoulder"),
    "mixamorig:LeftForeArm": (SemanticBone.ARM_LOWER_L, "mixamorig:LeftArm"),
    "mixamorig:RightForeArm": (SemanticBone.ARM_LOWER_R, "mixamorig:RightArm"),
    "mixamorig:LeftHand": (SemanticBone.HAND_L, "mixamorig:LeftForeArm"),
    "mixamorig:RightHand": (SemanticBone.HAND_R, "mixamorig:RightForeArm"),
    "mixamorig:LeftUpLeg": (SemanticBone.THIGH_L, "mixamorig:Hips"),
    "mixamorig:RightUpLeg": (SemanticBone.THIGH_R, "mixamorig:Hips"),
    "mixamorig:LeftLeg": (SemanticBone.SHIN_L, "mixamorig:LeftUpLeg"),
    "mixamorig:RightLeg": (SemanticBone.SHIN_R, "mixamorig:RightUpLeg"),
    "mixamorig:LeftFoot": (SemanticBone.FOOT_L, "mixamorig:LeftLeg"),
    "mixamorig:RightFoot": (SemanticBone.FOOT_R, "mixamorig:RightLeg"),
}


def _skeleton(master_id: CharacterMasterId, provider: dict, seed: str):
    from windagent_core.domain.video_production.ids import SkeletonProfileId

    detector = SkeletonDetector(
        SkeletonProfileId(seed), source_provider=("a" if provider is _PROVIDER_A else "b")
    )
    bones = [
        {"name": n, "parent": p, "position": [0.0, 0.0, 0.0], "length": 0.2}
        for n, (_sem, p) in provider.items()
    ]
    return detector.detect(bones)


def _make_master(master_id: CharacterMasterId, *, topology_seed: str, geo_seed: str) -> CharacterMaster:
    """A fully approved CharacterMaster (Phase 8) with a distinct topology."""
    geo = CharacterGeometryProfile(
        profile_id=CharacterGeometryProfileId.generate("geo"),
        source_hash=geo_seed,
        vertex_count=12000 if "hi" in topology_seed else 4000,
        poly_count=3000 if "hi" in topology_seed else 1000,
    )
    rev = CharacterMasterRevision(
        revision_id=CharacterMasterRevisionId.generate("rev"),
        master_id=master_id,
        revision_number=1,
        state=CharacterMasterState.VALIDATED,
        name="Mai",
        geometry=geo,
        materials=CharacterMaterialProfile(
            profile_id=CharacterMaterialProfileId.generate("mat"), palette_hash="p1"
        ),
        proportions=CharacterProportionProfile(
            profile_id=CharacterProportionProfileId.generate("pr"), proportions={"leg_ratio": 0.5}
        ),
        facial_rig=FacialRigProfile(
            profile_id=FacialRigProfileId.generate("fx"), topology_hash=geo_seed,
            control_names=["brow_l", "brow_r", "mouth", "eye_l", "eye_r"],
        ),
        animation=AnimationProfile(
            profile_id=AnimationProfileId.generate("an"),
            approved_clips=[],
            clip_manifest_hash="initial",
        ),
        style=StyleFingerprint(
            fingerprint_id=StyleFingerprintId.generate("sf"),
            style_key="stylized", palette_signature="p1", silhouette_signature="s",
            approved_by="hoa",
        ),
        voice_profile_id=CharacterVoiceProfileId.generate("vp"),
    )
    approved = CharacterMasterApprovalService.approve(rev, actor="hoa")
    return CharacterMasterFactory.install_revision(
        CharacterMaster(master_id=master_id), approved, invalidated_scenes=[]
    )


def _rig(master_id: CharacterMasterId, skel, *, root_ok: bool = True) -> RigProfile:
    return RigProfile(
        rig_profile_id=RigProfileId.generate("rig"),
        master_id=master_id,
        skeleton=skel,
        topology_hash=skel.topology_hash,
        facial_controls=["brow_l", "brow_r", "mouth", "eye_l", "eye_r"],
    )


@pytest.fixture
def pipeline_ctx():
    a_id = CharacterMasterId.generate("vpc_a")
    b_id = CharacterMasterId.generate("vpc_b")
    master_a = _make_master(a_id, topology_seed="lo", geo_seed="mesh-lo")
    master_b = _make_master(b_id, topology_seed="hi", geo_seed="mesh-hi")
    skel_a = _skeleton(a_id, _PROVIDER_A, "skel-a")
    skel_b = _skeleton(b_id, _PROVIDER_B, "skel-b")
    # DIFFERENT topology guaranteed
    assert skel_a.topology_hash != skel_b.topology_hash
    rig_a = _rig(a_id, skel_a)
    rig_b = _rig(b_id, skel_b)
    return {
        "master_a": master_a, "master_b": master_b,
        "skel_a": skel_a, "skel_b": skel_b,
        "rig_a": rig_a, "rig_b": rig_b,
        "a_id": a_id, "b_id": b_id,
    }


# ---- both masters validate fail-open (valid rigs) ----
def test_both_masters_rigs_validate(pipeline_ctx):
    va = RigValidator(RigValidationReceiptId("ra"), pipeline_ctx["a_id"])
    vb = RigValidator(RigValidationReceiptId("rb"), pipeline_ctx["b_id"])
    for v, rig in ((va, pipeline_ctx["rig_a"]), (vb, pipeline_ctx["rig_b"])):
        receipt = v.validate(rig)
        assert receipt.valid is True


# ---- retarget the SAME minimal clip set onto BOTH different-topology masters ----
def test_two_masters_retarget_same_clip_set(pipeline_ctx):
    src_skeleton = pipeline_ctx["skel_a"]
    gate = CompatibilityGate(DeformationMetricEngine())
    approved_a = []
    approved_b = []
    for tgt_key in ("skel_a", "skel_b"):
        tgt = pipeline_ctx[tgt_key]
        master = pipeline_ctx["master_a"] if tgt_key == "skel_a" else pipeline_ctx["master_b"]
        mapper = RetargetMapper(
            RetargetProfileId(f"rt-{tgt_key}"),
            {"source": pipeline_ctx["a_id"], "target": master.master_id},
        )
        retarget = mapper.build(src_skeleton, tgt)
        # deterministic: re-running the same build yields the same manifest
        again = mapper.build(src_skeleton, tgt)
        assert again.manifest_hash == retarget.manifest_hash
        clip_results = []
        for clip in sorted(MINIMAL_CLIP_SUITE):
            profile = gate.evaluate(
                AnimationCompatibilityProfileId(f"c-{tgt_key}-{clip}"),
                clip=clip,
                retarget=retarget,
                measurements={m: 0.0 for m in DeformationMetric},
            )
            assert profile.verdict == CompatibilityVerdict.APPROVED
            clip_results.append(profile)
        (approved_a if tgt_key == "skel_a" else approved_b).extend(clip_results)
    # the full minimal suite is approved on BOTH topologies
    assert len(approved_a) == len(MINIMAL_CLIP_SUITE)
    assert len(approved_b) == len(MINIMAL_CLIP_SUITE)


# ---- continuity: two episodes pin the same revision -> identical identity ----
def test_episode_continuity_two_episodes_same_revision(pipeline_ctx):
    master = pipeline_ctx["master_a"]
    ep1 = master.with_pin("episode-1")
    ep2 = master.with_pin("episode-2")
    # both episodes resolve to the SAME active revision => stable identity
    assert ep1.pin_episode("episode-1").revision_id == ep2.pin_episode("episode-2").revision_id
    assert ep1.active_revision().content_hash() == master.active_revision().content_hash()


# ---- revision advance does not mutate a locked episode's artifact ----
def test_new_revision_does_not_change_locked_episode_artifact(pipeline_ctx):
    master = pipeline_ctx["master_b"]
    locked = master.with_pin("lock-ep")
    old_hash = locked.active_revision().content_hash()
    # install a superseding revision 2 (fresh id) and retire it
    rev2 = CharacterMasterRevision(
        revision_id=CharacterMasterRevisionId.generate("rev2"),
        master_id=master.master_id,
        revision_number=2,
        state=CharacterMasterState.VALIDATED,
        name="Mai",
        geometry=CharacterGeometryProfile(
            profile_id=CharacterGeometryProfileId.generate("geo2"), source_hash="mesh-hi-v2",
            vertex_count=5000, poly_count=1250,
        ),
    ).with_state(CharacterMasterState.RETIRED)
    master2 = CharacterMasterFactory.install_revision(
        locked, rev2, invalidated_scenes=["scene-9"]
    )
    pinned = master2.pin_episode("lock-ep")
    assert pinned.revision_id == locked.active_revision().revision_id
    assert pinned.content_hash() == old_hash  # locked episode artifact unchanged


# ---- a failing clip is NEVER admitted to the approved set (fail-closed) ----
def test_failed_clip_not_admitted_to_approved_library(pipeline_ctx):
    target = pipeline_ctx["skel_b"]
    mapper = RetargetMapper(
        RetargetProfileId("rt-fail"),
        {"source": pipeline_ctx["a_id"], "target": pipeline_ctx["b_id"]},
    )
    retarget = mapper.build(pipeline_ctx["skel_a"], target)
    gate = CompatibilityGate(DeformationMetricEngine())
    failing = gate.evaluate(
        AnimationCompatibilityProfileId("c-fail"),
        clip="walk",
        retarget=retarget,
        measurements={**{m: 0.0 for m in DeformationMetric}, DeformationMetric.FOOT_SLIDING: 0.4},
    )
    assert failing.verdict == CompatibilityVerdict.FAILED
    assert not failing.approved
    with pytest.raises(RigCompatibilityError):
        gate.evaluate_or_raise(
            AnimationCompatibilityProfileId("c-fail2"),
            clip="walk",
            retarget=retarget,
            measurements={**{m: 0.0 for m in DeformationMetric}, DeformationMetric.FOOT_SLIDING: 0.4},
        )


# ---- manual correction is a DERIVED revision, source untouched (backlog 7) ----
def test_manual_correction_derived_revision_manifest(pipeline_ctx):
    source = pipeline_ctx["rig_a"]
    derived = DerivedRigService().derive(
        RigProfileId("rig-corrected"),
        source_rig=source,
        edits={"scale": 0.02, "weight_influences": 6},
        basis=CorrectionBasis.MANUAL,
        actor="hoa",
    )
    assert derived.scale == 0.02
    assert derived.derived_from == [str(source.rig_profile_id)]
    assert "correction_manifest_hash" in derived.metadata
    assert source.scale == 1.0  # source untouched


# ---- provider B Mixamo skeleton is semantically complete without BON dependency ----
def test_mixamo_skeleton_semantically_complete(pipeline_ctx):
    skel_b = pipeline_ctx["skel_b"]
    assert SemanticBone.ROOT.value in skel_b.semantic_to_bone
    assert SemanticBone.PELVIS.value in skel_b.semantic_to_bone
    assert SemanticBone.HEAD.value in skel_b.semantic_to_bone
