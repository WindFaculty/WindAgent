"""VP3D Phase 16 — Procedural Animation unit tests (stage_h §4/§6).

Covers the §6 procedural matrix:

- all 10 procedural layers (look-at, head/eye tracking, hand/foot IK, path
  following, object grab, sitting alignment, turning, idle variation) are
  registered with typed bone ownership and default priority;
- a layer never overwrites keyframes outside its ownership: out-of-ownership
  specs and same-priority bone conflicts fail closed before any bake;
- deterministic seed: same recipe+seed+track -> identical bake hash;
  different seed -> different hash;
- validation is fail-closed: foot sliding, hand reach, joint limit,
  collision, balance and transition continuity are DETECTED and blocking;
- wrong/missing anchors for grab/sitting fail closed (ANCHOR_MISMATCH);
- bake is all-or-nothing: a failing bake never publishes a derived action;
- repair is layer-scoped: changing one layer invalidates only that layer's
  baked contribution, never a whole-scene re-bake;
- a changed bake invalidates ONLY the derived action/render, never the body
  clip, assets, rigs or audio.
"""

from __future__ import annotations

import pytest
from windagent_core.domain.video_production.animation import AnimationIntent
from windagent_core.domain.video_production.enums import (
    AnimationAction,
    ProceduralLayerKind,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import ProceduralCompileError
from windagent_core.domain.video_production.ids import (
    AnimationIntentId,
    ProceduralLayerId,
    SkeletonProfileId,
)
from windagent_core.domain.video_production.procedural import (
    BakedAction,
    LAYER_DEFAULT_PRIORITY,
    LAYER_OWNERSHIP,
    ProceduralFindingKind,
    ProceduralLayerSpec,
    ProceduralValidator,
)
from windagent_intelligence.video.animation import AnimationCompiler
from windagent_intelligence.video.animation.library import REQUIRED_HUMANOID_BONES
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.procedural import (
    PROCEDURAL_COMPILER_LAYER_VERSION,
    ProceduralCompiler,
    supported_layer_kinds,
)
from windagent_intelligence.video.procedural.layers import (
    requires_anchor,
)


def _track(action: AnimationAction = AnimationAction.WALK):
    compiler = AnimationCompiler()
    intent = AnimationIntent(
        intent_id=AnimationIntentId("ai-p16"),
        actor_id="char_01",
        action=action,
        fps=24,
        skeleton_profile_id=SkeletonProfileId("skel_humanoid_standard"),
        episode_id="ep-16",
    )
    return compiler.compile(intent=intent,
                            target_bones=REQUIRED_HUMANOID_BONES).track


def _layer(layer_id: str, kind: ProceduralLayerKind, **kw) -> ProceduralLayerSpec:
    return ProceduralLayerSpec(
        layer_id=ProceduralLayerId(layer_id), kind=kind, **kw)


COMPILER = ProceduralCompiler()
WALK = _track()


# ---------------------------------------------------------------------------
# Registry (backlog 1)
# ---------------------------------------------------------------------------
def test_all_ten_layer_kinds_registered():
    assert supported_layer_kinds() == [
        "LOOK_AT", "HEAD_TRACKING", "EYE_TRACKING", "HAND_IK", "FOOT_IK",
        "PATH_FOLLOW", "OBJECT_GRAB", "SITTING_ALIGNMENT", "TURNING",
        "IDLE_VARIATION",
    ]
    for kind in ProceduralLayerKind:
        assert LAYER_OWNERSHIP[kind], f"{kind} has no ownership"
        assert LAYER_DEFAULT_PRIORITY[kind] > 0, f"{kind} has no priority"


def test_grab_and_sitting_require_anchor():
    assert requires_anchor(ProceduralLayerKind.OBJECT_GRAB)
    assert requires_anchor(ProceduralLayerKind.SITTING_ALIGNMENT)
    assert not requires_anchor(ProceduralLayerKind.LOOK_AT)


# ---------------------------------------------------------------------------
# Recipe build (backlog 2 — ownership + conflict)
# ---------------------------------------------------------------------------
def test_recipe_build_applies_default_priority():
    recipe = COMPILER.build_recipe(
        track=WALK, layer_specs=[
            _layer("l1", ProceduralLayerKind.LOOK_AT)])
    assert recipe.layers[0].priority == LAYER_DEFAULT_PRIORITY[
        ProceduralLayerKind.LOOK_AT]
    assert recipe.recipe_hash


def test_recipe_build_outside_ownership_fails_closed():
    # LOOK_AT owns HEAD/NECK only; FOOT_L is outside its ownership
    bad = _layer("l-bad", ProceduralLayerKind.LOOK_AT,
                 affected_bones=[SemanticBone.HEAD, SemanticBone.FOOT_L])
    with pytest.raises(ProceduralCompileError) as exc:
        COMPILER.build_recipe(track=WALK, layer_specs=[bad])
    assert "OUTSIDE_OWNERSHIP" in exc.value.details["kinds"]


def test_recipe_build_same_priority_conflict_fails_closed():
    # PATH_FOLLOW and SITTING_ALIGNMENT both own ROOT/PELVIS; same priority
    # would make the winner arbitrary
    a = _layer("l-a", ProceduralLayerKind.PATH_FOLLOW, priority=50)
    b = _layer("l-b", ProceduralLayerKind.SITTING_ALIGNMENT, priority=50,
               input={"anchor_id": "seat_01"})
    with pytest.raises(ProceduralCompileError) as exc:
        COMPILER.build_recipe(track=WALK, layer_specs=[a, b])
    assert "LAYER_CONFLICT" in exc.value.details["kinds"]


def test_recipe_build_different_priority_overlap_is_legal():
    a = _layer("l-a", ProceduralLayerKind.PATH_FOLLOW, priority=40)
    b = _layer("l-b", ProceduralLayerKind.SITTING_ALIGNMENT, priority=65,
               input={"anchor_id": "seat_01"})
    recipe = COMPILER.build_recipe(track=WALK, layer_specs=[a, b])
    assert recipe.recipe_hash


def test_recipe_build_duplicate_layer_id_fails_closed():
    a = _layer("l-dup", ProceduralLayerKind.LOOK_AT)
    b = _layer("l-dup", ProceduralLayerKind.TURNING)
    with pytest.raises(ProceduralCompileError):
        COMPILER.build_recipe(track=WALK, layer_specs=[a, b])


def test_recipe_ordered_layers_priority_desc_stable():
    recipe = COMPILER.build_recipe(
        track=WALK, layer_specs=[
            _layer("l-idle", ProceduralLayerKind.IDLE_VARIATION, seed=500),
            _layer("l-foot", ProceduralLayerKind.FOOT_IK),
            _layer("l-look", ProceduralLayerKind.LOOK_AT)])
    priorities = [l.priority for l in recipe.ordered_layers()]
    assert priorities == sorted(priorities, reverse=True)
    assert priorities[0] == LAYER_DEFAULT_PRIORITY[ProceduralLayerKind.FOOT_IK]


def test_recipe_hash_changes_when_layer_changes():
    base = COMPILER.build_recipe(
        track=WALK, layer_specs=[
            _layer("l-look", ProceduralLayerKind.LOOK_AT)])
    changed = COMPILER.build_recipe(
        track=WALK, layer_specs=[
            _layer("l-look", ProceduralLayerKind.LOOK_AT,
                   input={"target_dx": 0.9})])
    assert base.recipe_hash != changed.recipe_hash


# ---------------------------------------------------------------------------
# Bake (backlog 3/5 — determinism)
# ---------------------------------------------------------------------------
def _clean_recipe(*layers):
    return COMPILER.build_recipe(track=WALK, layer_specs=list(layers),
                                 seed=500)


def test_bake_deterministic_same_recipe_same_hash():
    recipe = _clean_recipe(
        _layer("l-look", ProceduralLayerKind.LOOK_AT))
    a = COMPILER.bake(recipe=recipe, track=WALK)
    b = COMPILER.bake(recipe=recipe, track=WALK)
    assert a.bake_hash == b.bake_hash
    assert a.baked_action.layers[0].layer_hash == \
        b.baked_action.layers[0].layer_hash


def test_bake_seed_changes_variation_hash():
    recipe_a = _clean_recipe(
        _layer("l-idle", ProceduralLayerKind.IDLE_VARIATION, seed=500))
    recipe_b = _clean_recipe(
        _layer("l-idle", ProceduralLayerKind.IDLE_VARIATION, seed=501))
    assert recipe_a.recipe_hash != recipe_b.recipe_hash
    assert COMPILER.bake(recipe=recipe_a, track=WALK).bake_hash != \
        COMPILER.bake(recipe=recipe_b, track=WALK).bake_hash


def test_every_layer_kind_bakes_clean_with_sane_inputs():
    anchors = {"table_01": {}, "seat_01": {}}
    specs = [
        _layer("l-look", ProceduralLayerKind.LOOK_AT),
        _layer("l-head", ProceduralLayerKind.HEAD_TRACKING),
        _layer("l-eye", ProceduralLayerKind.EYE_TRACKING),
        _layer("l-hand", ProceduralLayerKind.HAND_IK),
        _layer("l-foot", ProceduralLayerKind.FOOT_IK),
        _layer("l-path", ProceduralLayerKind.PATH_FOLLOW),
        _layer("l-grab", ProceduralLayerKind.OBJECT_GRAB,
               input={"anchor_id": "table_01"}),
        _layer("l-sit", ProceduralLayerKind.SITTING_ALIGNMENT,
               input={"anchor_id": "seat_01"}),
        _layer("l-turn", ProceduralLayerKind.TURNING),
        _layer("l-idle", ProceduralLayerKind.IDLE_VARIATION, seed=500),
    ]
    recipe = COMPILER.build_recipe(track=WALK, layer_specs=specs, seed=500)
    receipt = COMPILER.bake(recipe=recipe, track=WALK, anchors=anchors)
    assert receipt.cleaned_ok, receipt.blocking_kinds
    assert len(receipt.baked_action.layers) == 10


def test_bake_layer_never_touches_bones_outside_ownership():
    recipe = _clean_recipe(
        _layer("l-look", ProceduralLayerKind.LOOK_AT,
               affected_bones=[SemanticBone.HEAD]))
    receipt = COMPILER.bake(recipe=recipe, track=WALK)
    result = receipt.baked_action.layers[0]
    assert set(result.owned_bones) == set(
        LAYER_OWNERSHIP[ProceduralLayerKind.LOOK_AT])
    # a LOOK_AT layer never claims lower-body bones
    assert SemanticBone.FOOT_L not in result.owned_bones


# ---------------------------------------------------------------------------
# Validation negative matrix (backlog 4)
# ---------------------------------------------------------------------------
def test_foot_sliding_detected():
    # path longer than the walk clip's root motion -> feet slide
    recipe = _clean_recipe(
        _layer("l-path", ProceduralLayerKind.PATH_FOLLOW,
               input={"path_length_m": 2.0, "obstacle_hits": 0}))
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.bake(recipe=recipe, track=WALK)
    assert "FOOT_SLIDING" in exc.value.details["kinds"]


def test_hand_reach_out_of_bounds_detected():
    recipe = _clean_recipe(
        _layer("l-hand", ProceduralLayerKind.HAND_IK,
               input={"target_distance_m": 1.0, "arm_span_m": 0.7}))
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.bake(recipe=recipe, track=WALK)
    assert "HAND_REACH_OUT_OF_BOUNDS" in exc.value.details["kinds"]


def test_joint_limit_violation_detected():
    # look target far to the side -> head turn beyond the neck limit
    recipe = _clean_recipe(
        _layer("l-look", ProceduralLayerKind.LOOK_AT,
               input={"target_dx": 4.0, "target_dz": 1.0}))
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.bake(recipe=recipe, track=WALK)
    assert "JOINT_LIMIT_VIOLATED" in exc.value.details["kinds"]


def test_collision_detected():
    recipe = _clean_recipe(
        _layer("l-path", ProceduralLayerKind.PATH_FOLLOW,
               input={"path_length_m": 1.6, "obstacle_count": 3,
                      "obstacle_hits": 2}))
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.bake(recipe=recipe, track=WALK)
    assert "COLLISION" in exc.value.details["kinds"]


def test_balance_violated_detected():
    # seed 7 -> deterministic balance offset 0.148m > 0.10m
    recipe = _clean_recipe(
        _layer("l-idle", ProceduralLayerKind.IDLE_VARIATION, seed=7))
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.bake(recipe=recipe, track=WALK)
    assert "BALANCE_VIOLATED" in exc.value.details["kinds"]


def test_transition_continuity_drift_detected():
    # hand-built bake whose frame range drifts from the track boundary
    recipe = _clean_recipe(_layer("l-look", ProceduralLayerKind.LOOK_AT))
    bake = COMPILER.bake(recipe=recipe, track=WALK).baked_action
    drifted = bake.model_copy(update={
        "motion_metrics": {**bake.motion_metrics,
                           "boundary_drift_frames": 3}})
    report = ProceduralValidator().validate_bake(drifted, WALK)
    assert (ProceduralFindingKind.TRANSITION_CONTINUITY_BROKEN
            in report.blocking_kinds)


def test_anchor_mismatch_fails_closed():
    recipe = _clean_recipe(
        _layer("l-grab", ProceduralLayerKind.OBJECT_GRAB,
               input={"anchor_id": "table_01"}))
    with pytest.raises(ProceduralCompileError) as exc:
        COMPILER.bake(recipe=recipe, track=WALK, anchors={})
    assert exc.value.details["kind"] == "ANCHOR_MISMATCH"
    # wrong anchor id also fails closed
    with pytest.raises(ProceduralCompileError):
        COMPILER.bake(recipe=recipe, track=WALK,
                      anchors={"chair_02": {}})


def test_grab_with_valid_anchor_bakes_clean():
    recipe = _clean_recipe(
        _layer("l-grab", ProceduralLayerKind.OBJECT_GRAB,
               input={"anchor_id": "table_01", "target_distance_m": 0.5,
                      "max_reach_m": 0.6}))
    receipt = COMPILER.bake(recipe=recipe, track=WALK,
                            anchors={"table_01": {}})
    assert receipt.cleaned_ok
    assert receipt.baked_action.layers[0].metric["grab_ok"] is True


def test_bake_atomic_no_partial_publish():
    recipe = _clean_recipe(
        _layer("l-path", ProceduralLayerKind.PATH_FOLLOW,
               input={"path_length_m": 3.0}))
    # blocking findings -> the bake raises before any derived action exists
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.bake(recipe=recipe, track=WALK)
    assert "FOOT_SLIDING" in exc.value.details["kinds"]


# ---------------------------------------------------------------------------
# Repair scoping (backlog 6)
# ---------------------------------------------------------------------------
def test_repair_scope_only_changed_layer():
    layers = [
        _layer("l-look", ProceduralLayerKind.LOOK_AT),
        _layer("l-foot", ProceduralLayerKind.FOOT_IK),
    ]
    old = COMPILER.build_recipe(track=WALK, layer_specs=layers, seed=500)
    new = COMPILER.build_recipe(
        track=WALK,
        layer_specs=[
            _layer("l-look", ProceduralLayerKind.LOOK_AT,
                   input={"target_dx": 0.9}),
            _layer("l-foot", ProceduralLayerKind.FOOT_IK),
        ], seed=500)
    scope = COMPILER.repair_scope(old, new)
    assert scope == ["procedural/layer:l-look"]
    # unchanged layers keep their baked contribution
    old_bake = COMPILER.bake(recipe=old, track=WALK)
    new_bake = COMPILER.bake(recipe=new, track=WALK)
    old_by_id = {str(r.layer_id): r for r in old_bake.baked_action.layers}
    new_by_id = {str(r.layer_id): r for r in new_bake.baked_action.layers}
    assert new_by_id["l-foot"].layer_hash == old_by_id["l-foot"].layer_hash
    assert new_by_id["l-look"].layer_hash != old_by_id["l-look"].layer_hash


def test_repair_scope_seed_change_invalidates_all():
    old = COMPILER.build_recipe(
        track=WALK, layer_specs=[
            _layer("l-idle", ProceduralLayerKind.IDLE_VARIATION, seed=500)],
        seed=500)
    new = COMPILER.build_recipe(
        track=WALK, layer_specs=[
            _layer("l-idle", ProceduralLayerKind.IDLE_VARIATION, seed=500)],
        seed=501)
    scope = COMPILER.repair_scope(old, new)
    assert scope == ["procedural/layer:l-idle"]


# ---------------------------------------------------------------------------
# Invalidation (§6)
# ---------------------------------------------------------------------------
def test_invalidation_scoped_to_procedural_bake_only():
    recipe = _clean_recipe(_layer("l-look", ProceduralLayerKind.LOOK_AT))
    first = COMPILER.bake(recipe=recipe, track=WALK)
    assert first.invalidated_artifacts == []
    # unchanged bake -> reuse, nothing invalidated
    same = COMPILER.bake(recipe=recipe, track=WALK,
                         prior_bake_hash=first.bake_hash)
    assert same.invalidated_artifacts == []
    # changed bake -> ONLY the derived action/render
    changed_recipe = _clean_recipe(
        _layer("l-look", ProceduralLayerKind.LOOK_AT,
               input={"target_dx": 0.9}))
    changed = COMPILER.bake(recipe=changed_recipe, track=WALK,
                            prior_bake_hash=first.bake_hash)
    assert changed.invalidated_artifacts == [
        f"procedural/bake:{WALK.track_id}"]


def test_baked_action_is_immutable_frozen():
    recipe = _clean_recipe(_layer("l-look", ProceduralLayerKind.LOOK_AT))
    bake = COMPILER.bake(recipe=recipe, track=WALK).baked_action
    with pytest.raises(ValueError):
        bake.frame_count = 0


def test_bake_records_recipe_and_compiler_version():
    recipe = _clean_recipe(_layer("l-look", ProceduralLayerKind.LOOK_AT))
    bake = COMPILER.bake(recipe=recipe, track=WALK).baked_action
    assert bake.recipe_id == recipe.recipe_id
    assert bake.recipe_hash == recipe.recipe_hash
    assert bake.compiler_version == PROCEDURAL_COMPILER_LAYER_VERSION
    assert bake.schema_version


def test_compiler_layer_version_is_pinned():
    assert PROCEDURAL_COMPILER_LAYER_VERSION == "1.0.0"
