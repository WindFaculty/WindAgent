"""Unit tests for the Rigging & Retargeting system (stage_d.md Phase 9).

Covers the five canonical models, provider-agnostic skeleton normalization
(backlog 1), fail-closed rig validation (backlog 2, stage_d.md §5), versioned
semantic retarget determinism (backlog 3, §5), fail-closed animation
compatibility gate (backlog 5/6), and manual correction as a derived rig
revision with a manifest (backlog 7). All checks are offline and deterministic.
"""

import pytest

from windagent_core.domain.video_production.enums import (
    CompatibilityVerdict,
    CorrectionBasis,
    DeformationMetric,
    RigStatus,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import (
    RigCompatibilityError,
    VideoProductionProtocolError,
)
from windagent_core.domain.video_production.ids import (
    AnimationCompatibilityProfileId,
    CharacterMasterId,
    RetargetProfileId,
    RigProfileId,
    RigValidationReceiptId,
    SkeletonProfileId,
)
from windagent_core.domain.video_production.rigging import (
    CompatibilityGate,
    DeformationMetricEngine,
    DerivedRigService,
    MINIMAL_CLIP_SUITE,
    RetargetMapper,
    RetargetProfile,
    RigProfile,
    RigValidator,
    SkeletonDetector,
    SkeletonProfile,
)


# ---------------------------------------------------------------------------
# Skeleton builders — two DIFFERENT providers with different bone naming,
# proving normalization is provider-agnostic (backlog 1).
# ---------------------------------------------------------------------------

# Provider A uses Avatar-style names.
_PROVIDER_A = {
    "Root": (SemanticBone.ROOT, ""),
    "Hips": (SemanticBone.PELVIS, "Root"),
    "Spine1": (SemanticBone.SPINE, "Hips"),
    "Spine2": (SemanticBone.CHEST, "Spine1"),
    "Neck": (SemanticBone.NECK, "Spine2"),
    "Head": (SemanticBone.HEAD, "Neck"),
    "Jaw": (SemanticBone.JAW, "Head"),
    "Eye_L": (SemanticBone.EYE_L, "Head"),
    "Eye_R": (SemanticBone.EYE_R, "Head"),
    "Brow_L": (SemanticBone.BROW_L, "Head"),
    "Brow_R": (SemanticBone.BROW_R, "Head"),
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
    "Toe_L": (SemanticBone.TOE_L, "Foot_L"),
    "Toe_R": (SemanticBone.TOE_R, "Foot_R"),
}

# Provider B uses Mixamo-style names; the SAME semantic roles must come out.
_PROVIDER_B = {
    "mixamorig:Root": (SemanticBone.ROOT, ""),
    "mixamorig:Hips": (SemanticBone.PELVIS, "mixamorig:Root"),
    "mixamorig:Spine": (SemanticBone.SPINE, "mixamorig:Hips"),
    "mixamorig:Spine2": (SemanticBone.CHEST, "mixamorig:Spine"),
    "mixamorig:Neck": (SemanticBone.NECK, "mixamorig:Spine2"),
    "mixamorig:Head": (SemanticBone.HEAD, "mixamorig:Neck"),
    "mixamorig:Jaw": (SemanticBone.JAW, "mixamorig:Head"),
    "mixamorig:LeftEye": (SemanticBone.EYE_L, "mixamorig:Head"),
    "mixamorig:RightEye": (SemanticBone.EYE_R, "mixamorig:Head"),
    "mixamorig:LeftBrow": (SemanticBone.BROW_L, "mixamorig:Head"),
    "mixamorig:RightBrow": (SemanticBone.BROW_R, "mixamorig:Head"),
    "mixamorig:LeftShoulder": (SemanticBone.SHOULDER_L, "mixamorig:Spine1"),
    "mixamorig:RightShoulder": (SemanticBone.SHOULDER_R, "mixamorig:Spine1"),
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
    "mixamorig:LeftToeBase": (SemanticBone.TOE_L, "mixamorig:LeftFoot"),
    "mixamorig:RightToeBase": (SemanticBone.TOE_R, "mixamorig:RightFoot"),
}


def _bones_from(provider: dict, root_name: str) -> list:
    out = []
    for name, (_sem, _parent) in provider.items():
        if name == root_name:
            _parent = ""
        out.append({"name": name, "parent": _parent, "position": [0.0, 0.0, 0.0], "length": 0.2})
    return out


def _detect(provider: dict, root_name: str, seed: str) -> "SkeletonProfile":

    detector = SkeletonDetector(
        SkeletonProfileId(seed),
        source_provider="fake_provider",
    )
    return detector.detect(_bones_from(provider, root_name))


# ---- provider-agnostic normalization (backlog 1) ----
def test_provider_a_and_b_normalize_to_same_semantic_roles():
    skel_a = _detect(_PROVIDER_A, "Root", "skel-a")
    skel_b = _detect(_PROVIDER_B, "mixamorig:Root", "skel-b")
    # different topology hashes, but identical semantic coverage
    assert skel_a.topology_hash != skel_b.topology_hash
    assert set(skel_a.semantic_to_bone) == set(skel_b.semantic_to_bone)
    assert set(skel_a.semantic_to_bone) == {s.value for s in SemanticBone}
    assert skel_b.semantic_to_bone[SemanticBone.PELVIS.value] == "mixamorig:Hips"


def test_detection_is_deterministic():
    a = _detect(_PROVIDER_A, "Root", "skel-a")
    b = _detect(_PROVIDER_A, "Root", "skel-a")
    assert a.topology_hash == b.topology_hash


# ---------------------------------------------------------------------------
# Rig validation — fail-closed (backlog 2, stage_d.md §5)
# ---------------------------------------------------------------------------


def _valid_rig(master_id, skel_seed: str = "skel-a") -> RigProfile:
    skel = _detect(_PROVIDER_A, "Root", skel_seed)
    return RigProfile(
        rig_profile_id=RigProfileId("rig-1"),
        master_id=master_id,
        skeleton=skel,
        topology_hash=skel.topology_hash,
        facial_controls=["brow_l", "brow_r", "mouth", "eye_l", "eye_r", "jaw"],
    )


def _validate(rig, **kwargs):
    return RigValidator(
        RigValidationReceiptId("receipt-1"), rig.master_id, geometry_hash=rig.topology_hash
    ).validate(rig, **kwargs)


def test_valid_rig_passes(master_id):
    receipt = _validate(_valid_rig(master_id))
    assert receipt.valid is True
    assert receipt.status == RigStatus.VALIDATED
    assert receipt.issues == []


def test_missing_root_bone_fails_closed(master_id):
    rig = _valid_rig(master_id)
    no_root = rig.skeleton.model_copy(
        update={
            "semantic_to_bone": {
                k: v for k, v in rig.skeleton.semantic_to_bone.items() if k != SemanticBone.ROOT.value
            }
        }
    )
    bare = RigProfile(
        rig_profile_id=RigProfileId("rig-broken"),
        master_id=master_id,
        skeleton=no_root,
        topology_hash=no_root.topology_hash,
        facial_controls=rig.facial_controls,
    )
    receipt = _validate(bare)
    assert receipt.valid is False
    codes = {i.code.value for i in receipt.issues}
    assert "ROOT_BONE_MISSING" in codes


def test_rest_pose_not_in_bind_fails_closed(master_id):
    receipt = _validate(_valid_rig(master_id), rest_pose_in_bind=False)
    assert receipt.valid is False
    assert any(i.code.value == "REST_POSE_NOT_BIND" for i in receipt.issues)


def test_scale_out_of_range_fails_closed(master_id):
    rig = _valid_rig(master_id).model_copy(update={"scale": -3.0})
    receipt = _validate(rig)
    assert receipt.valid is False
    assert any(i.code.value == "SCALE_OUT_OF_RANGE" for i in receipt.issues)


def test_weights_unassigned_fails_closed(master_id):
    receipt = _validate(_valid_rig(master_id), assigned_weight_ratio=0.9)
    assert receipt.valid is False
    assert any(i.code.value == "WEIGHTS_UNASSIGNED" for i in receipt.issues)


def test_joint_limit_violated_fails_closed(master_id):
    receipt = _validate(_valid_rig(master_id), joint_limit_breached=True)
    assert receipt.valid is False
    assert any(i.code.value == "JOINT_LIMIT_VIOLATED" for i in receipt.issues)


def test_facial_controls_incompatible_fails_closed(master_id):
    rig = _valid_rig(master_id).model_copy(update={"facial_controls": []})
    receipt = _validate(rig)
    assert receipt.valid is False
    assert any(i.code.value == "FACIAL_CONTROLS_INCOMPATIBLE" for i in receipt.issues)


# ---------------------------------------------------------------------------
# Retarget mapping — versioned + deterministic (backlog 3, §5)
# ---------------------------------------------------------------------------


@pytest.fixture
def master_id():
    return CharacterMasterId.generate("vpm")


def test_retarget_is_deterministic_and_manifests_stable(master_id):
    src = _detect(_PROVIDER_B, "mixamorig:Root", "skel-anim")
    tgt = _detect(_PROVIDER_A, "Root", "skel-char")
    mapper = RetargetMapper(
        RetargetProfileId("retarget-1"),
        {"source": CharacterMasterId.generate("src"), "target": master_id},
    )
    r1 = mapper.build(src, tgt)
    mapper2 = RetargetMapper(
        RetargetProfileId("retarget-1"),
        {"source": CharacterMasterId.generate("src"), "target": master_id},
    )
    r2 = mapper2.build(src, tgt)
    assert r1.manifest_hash == r2.manifest_hash
    assert r1.mapping[SemanticBone.PELVIS.value] == SemanticBone.PELVIS.value
    assert r1.mapping[SemanticBone.HEAD.value] == SemanticBone.HEAD.value


def test_retarget_missing_target_semantic_fails_closed(master_id):
    src = _detect(_PROVIDER_A, "Root", "skel-full")
    # target skeleton missing EYE/TOE semantics
    tgt_bare = _detect(_PROVIDER_A, "Root", "skel-bare")
    tgt = tgt_bare.model_copy(
        update={
            "semantic_to_bone": {k: v for k, v in tgt_bare.semantic_to_bone.items() if k not in ("EYE_L", "EYE_R", "TOE_L", "TOE_R")}
        }
    )
    mapper = RetargetMapper(
        RetargetProfileId("retarget-2"),
        {"source": CharacterMasterId.generate("src"), "target": master_id},
    )
    with pytest.raises(VideoProductionProtocolError):
        mapper.build(src, tgt)


def test_retarget_version_bumps_change_manifest(master_id):
    src = _detect(_PROVIDER_A, "Root", "skel-anim")
    tgt1 = _detect(_PROVIDER_A, "Root", "skel-char-v1")
    tgt2 = _detect(_PROVIDER_A, "Root", "skel-char-v2")
    mapper = RetargetMapper(
        RetargetProfileId("retarget-3"),
        {"source": CharacterMasterId.generate("src"), "target": master_id},
    )
    base = mapper.build(src, tgt1)
    derived = RetargetMapper.derive_new_version(base, tgt2)
    assert derived.version == base.version + 1
    assert derived.manifest_hash != base.manifest_hash


# ---------------------------------------------------------------------------
# Fail-closed animation compatibility gate (backlog 5/6)
# ---------------------------------------------------------------------------


def _retarget() -> RetargetProfile:
    src = _detect(_PROVIDER_A, "Root", "skel-anim")
    tgt = _detect(_PROVIDER_A, "Root", "skel-char")
    return RetargetMapper(
        RetargetProfileId("retarget-gate"),
        {"source": CharacterMasterId.generate("src"), "target": CharacterMasterId.generate("tgt")},
    ).build(src, tgt)


def _gate() -> CompatibilityGate:
    return CompatibilityGate(DeformationMetricEngine())


def test_clip_under_all_thresholds_is_approved():
    gate = _gate()
    profile = gate.evaluate(
        AnimationCompatibilityProfileId("clip-1"),
        clip="walk",
        retarget=_retarget(),
        measurements={m: 0.0 for m in DeformationMetric},
    )
    assert profile.verdict == CompatibilityVerdict.APPROVED
    assert profile.approved is True
    assert profile.manifest_hash == profile.recompute_manifest_hash()


def test_foot_sliding_over_threshold_fails_closed():
    gate = _gate()
    gate.evaluate(
        AnimationCompatibilityProfileId("clip-2"),
        clip="walk",
        retarget=_retarget(),
        measurements={m: 0.0 for m in DeformationMetric},
    )
    failing = gate.evaluate(
        AnimationCompatibilityProfileId("clip-2b"),
        clip="walk",
        retarget=_retarget(),
        measurements={**{m: 0.0 for m in DeformationMetric}, DeformationMetric.FOOT_SLIDING: 0.5},
    )
    assert failing.verdict == CompatibilityVerdict.FAILED
    assert "FOOT_SLIDING" in failing.breached_metrics


def test_untested_clip_not_approved():
    gate = _gate()
    profile = gate.evaluate(
        AnimationCompatibilityProfileId("clip-3"),
        clip="custom_dance",
        retarget=_retarget(),
        measurements={m: 0.0 for m in DeformationMetric},
        clip_known=False,
    )
    assert profile.verdict == CompatibilityVerdict.NOT_TESTED
    assert not profile.approved


def test_evaluate_or_raise_raises_for_failed_and_untested():
    gate = _gate()
    with pytest.raises(RigCompatibilityError):
        gate.evaluate_or_raise(
            AnimationCompatibilityProfileId("clip-4"),
            clip="walk",
            retarget=_retarget(),
            measurements={**{m: 0.0 for m in DeformationMetric}, DeformationMetric.POSE_DISCONTINUITY: 2.0},
        )
    with pytest.raises(RigCompatibilityError):
        gate.evaluate_or_raise(
            AnimationCompatibilityProfileId("clip-5"),
            clip="unknown_clip",
            retarget=_retarget(),
            measurements={m: 0.0 for m in DeformationMetric},
            clip_known=False,
        )


def test_minimal_clip_suite_is_complete():
    assert MINIMAL_CLIP_SUITE == {
        "idle", "walk", "run", "sit", "stand", "turn", "point", "grab", "talk", "facial_neutral",
    }


# ---------------------------------------------------------------------------
# Manual correction as DERIVED rig revision with manifest (backlog 7)
# ---------------------------------------------------------------------------


def test_derived_correction_carries_manifest_and_never_mutates_source(master_id):
    source = _valid_rig(master_id)
    service = DerivedRigService()
    derived = service.derive(
        RigProfileId("rig-derived-1"),
        source_rig=source,
        edits={"scale": 0.02, "weight_influences": 6},
        basis=CorrectionBasis.MANUAL,
        actor="hoa",
    )
    # source unchanged, new immutable revision references it
    assert source.scale == 1.0
    assert source.derived_from == []
    assert derived.scale == 0.02
    assert derived.derived_from == [str(source.rig_profile_id)]
    assert "correction_manifest" in derived.metadata
    assert derived.metadata["correction_manifest"]["actor"] == "hoa"
    assert derived.metadata["correction_manifest"]["basis"] == CorrectionBasis.MANUAL.value
    assert "correction_manifest_hash" in derived.metadata


def test_derived_correction_requires_edits_and_actor(master_id):
    source = _valid_rig(master_id)
    service = DerivedRigService()
    with pytest.raises(VideoProductionProtocolError):
        service.derive(
            RigProfileId("rig-derived-2"), source_rig=source,
            edits={}, basis=CorrectionBasis.MANUAL, actor="hoa",
        )
    with pytest.raises(VideoProductionProtocolError):
        service.derive(
            RigProfileId("rig-derived-3"), source_rig=source,
            edits={"scale": 0.02}, basis=CorrectionBasis.MANUAL, actor="  ",
        )


def test_models_are_immutable(master_id):
    profile = _gate().evaluate(
        AnimationCompatibilityProfileId("clip-imm"),
        clip="idle",
        retarget=_retarget(),
        measurements={m: 0.0 for m in DeformationMetric},
    )
    with pytest.raises(ValueError):
        profile.verdict = CompatibilityVerdict.FAILED
