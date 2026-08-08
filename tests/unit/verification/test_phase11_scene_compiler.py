"""VP3D Phase 11 — Scene Compiler domain tests (stage_f §3 backlog 1-7).

Covers the typed plan, completeness validation (approval/revision/continuity),
deterministic hashing, the bpy allow-list transcriber + operation guard
(no eval/exec of model/metadata text), save->reopen->publish inspection, the
IR->data-block mapping manifest, and incremental compile invalidation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from windagent_core.domain.video_production.enums import (
    BpyOpCode,
    CompileStatus,
    PlanAffected,
    TransformUnit,
)
from windagent_core.domain.video_production.errors import (
    AssetRevisionMismatchError,
    ScenePlanIncompleteError,
    UnapprovedAssetError,
    UnsafeCompilerOperationError,
)
from windagent_core.domain.video_production.ids import (
    BlendInspectionReceiptId,
    BlenderScenePlanId,
    IrMappingManifestId,
    ProductionRevisionId,
    SceneId,
    VideoProjectId,
)
from windagent_core.domain.video_production.production_ir.models import (
    AssetReference,
    CharacterInstance,
    EnvironmentInstance,
    ProductionIrDocument,
    RenderProfile,
    SceneDescription,
    ShotExecutionIntent,
)
from windagent_core.domain.video_production.scene_compiler import (
    AnimationBinding,
    BlendInspector,
    BlendSnapshot,
    BlenderObject,
    BlenderScenePlan,
    BpyTranscriber,
    CameraBinding,
    CompilerOperationGuard,
    FrameRange,
    IncrementalCompileService,
    IrMappingEntry,
    IrMappingManifest,
    LightBinding,
    RenderConfiguration,
    ScenePlanDraft,
    ScenePlanValidator,
    compute_plan_hash,
)

HASH64 = "a" * 64


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _asset(role: str) -> AssetReference:
    return AssetReference(
        asset_id=f"ra-{role}",
        role=role,
        uri=f"artifacts://{role}",
        content_hash=HASH64,
        format="GLTF",
    )


def _ir(*, locked: bool = True) -> ProductionIrDocument:
    scene = SceneDescription(
        scene_id=f"sd-1",
        screenplay_scene_id=SceneId("sc1"),
        characters=[CharacterInstance(
            instance_id="ci-1", character_id="ch-1", display_name="Mai",
            mesh=_asset("CHARACTER_MESH")),
        ],
        environment=[EnvironmentInstance(
            instance_id="env-1", location_id="loc-1", asset=_asset("ENVIRONMENT"))],
        action="Mai walks across the room",
    )
    shot = ShotExecutionIntent(
        intent_id="se-1", shot_id="sh-1", scene_id="sd-1", order=1,
        characters=["ci-1"], environment=["env-1"],
        camera=_camera_track(),
        duration_seconds=5.0,
        render_profile_id="rp-1",
    )
    return ProductionIrDocument(
        ir_id="ir-1", project_id=VideoProjectId("p1"),
        revision_id=ProductionRevisionId("r1"), locked=locked,
        scenes=[scene], shots=[shot],
        render_profiles=[RenderProfile(profile_id="rp-1")],
    )


def _camera_track():
    from windagent_core.domain.video_production.production_ir.models import CameraTrack
    return CameraTrack(track_id="ct-1", duration_seconds=5.0)


def _frame(start: int = 1, end: int = 120, fps: int = 24) -> FrameRange:
    return FrameRange(start=start, end=end, fps=fps)


def _render(frame: FrameRange) -> RenderConfiguration:
    return RenderConfiguration(
        profile_id="rp-1", quality="HIGH", samples=32,
        resolution={"width": 1920, "height": 1080}, denoise=True, frame_range=frame,
    )


def _plan(**overrides) -> BlenderScenePlan:
    fr = overrides.pop("frame_range", _frame())
    base = dict(
        plan_id=BlenderScenePlanId("plan-1"), project_id=VideoProjectId("p1"),
        revision_id=ProductionRevisionId("r1"), scene_id=SceneId("sc1"),
        ir_hash=HASH64, frame_range=fr, render_config=_render(fr),
    )
    base.update(overrides)
    plan = BlenderScenePlan(**base)
    return plan.model_copy(update={"plan_hash": plan.compute_stable_hash()})


def _populated_plan() -> BlenderScenePlan:
    plan = _plan(objects=[
        BlenderObject(object_id="obj-mai", source_id="ci-1", source_type="CHARACTER",
                      asset_revision_hash=HASH64, kind="MESH"),
        BlenderObject(object_id="obj-ground", source_id="env-1", source_type="ENVIRONMENT",
                      asset_revision_hash=HASH64, kind="MESH"),
    ], cameras=[CameraBinding(object_id="cam-1", track_id="ct-1", lens_mm=35.0)],
        lights=[LightBinding(object_id="key-1", rig_id="lg-1", light_kind="AREA", energy=3.0)],
        animations=[AnimationBinding(
            binding_id="ab-1", track_id="at-1", target_object_ids=["obj-mai"],
            start_frame=1, end_frame=80, action="walk_to_desk")])
    return plan


# ---------------------------------------------------------------------------
# backlog 1 — typed plan
# ---------------------------------------------------------------------------
def test_plan_is_immutable():
    plan = _plan()
    with pytest.raises(ValidationError):
        plan.scene_id = SceneId("other")  # frozen attrs blocked


def test_plan_holds_instances_and_render():
    plan = _populated_plan()
    assert plan.frame_range.validate_range()
    assert plan.render_config.samples == 32
    assert plan.objects[0].source_type == "CHARACTER"
    assert plan.objects[0].asset_revision_hash == HASH64


# ---------------------------------------------------------------------------
# backlog 2 — completeness / fail-closed
# ---------------------------------------------------------------------------
def test_validator_requires_continuity_and_shot_graph():
    draft = ScenePlanDraft(
        project_id=VideoProjectId("p1"), revision_id=ProductionRevisionId("r1"),
        scene_id=SceneId("sc1"), ir=_ir(), approved_asset_revisions={"ci-1": HASH64},
        shot_graph=None, continuity=None,
    )
    with pytest.raises(ScenePlanIncompleteError):
        ScenePlanValidator().validate(draft)


def test_validator_rejects_unapproved_asset():
    draft = ScenePlanDraft(
        project_id=VideoProjectId("p1"), revision_id=ProductionRevisionId("r1"),
        scene_id=SceneId("sc1"), ir=_ir(), approved_asset_revisions={},  # empty
        shot_graph={}, continuity={},
    )
    with pytest.raises(UnapprovedAssetError):
        ScenePlanValidator().validate(draft)


def test_validator_rejects_revision_mismatch():
    draft = ScenePlanDraft(
        project_id=VideoProjectId("p1"), revision_id=ProductionRevisionId("r1"),
        scene_id=SceneId("sc1"), ir=_ir(),
        approved_asset_revisions={"ci-1": HASH64.replace("a", "b", 1)},
        shot_graph={}, continuity={},
    )
    with pytest.raises(AssetRevisionMismatchError):
        ScenePlanValidator().validate(draft)


def test_validator_passes_complete_inputs():
    draft = ScenePlanDraft(
        project_id=VideoProjectId("p1"), revision_id=ProductionRevisionId("r1"),
        scene_id=SceneId("sc1"), ir=_ir(),
        approved_asset_revisions={"ci-1": HASH64, "env-1": HASH64},
        shot_graph={}, continuity={},
    )
    # no raise => complete (all referenced entities are approved)
    ScenePlanValidator().validate(draft)


# ---------------------------------------------------------------------------
# backlog 3 — deterministic hashing
# ---------------------------------------------------------------------------
def test_same_input_same_hash():
    assert compute_plan_hash(plan={"a": 1, "b": [1, 2]}) == compute_plan_hash(
        plan={"b": [1, 2], "a": 1})
    assert compute_plan_hash(plan={"a": 1}) != compute_plan_hash(plan={"a": 2})


def test_plan_hash_deterministic():
    p1 = _populated_plan()
    p2 = _populated_plan()
    assert p1.plan_hash == p2.plan_hash


def test_adding_object_changes_hash():
    base = _populated_plan()
    extra = base.model_copy(update={"objects": base.objects + [BlenderObject(
        object_id="obj-2", source_id="ci-2", source_type="CHARACTER", kind="MESH")]})
    assert extra.compute_stable_hash() != base.compute_stable_hash()


# ---------------------------------------------------------------------------
# backlog 4 — allow-list / no eval·exec
# ---------------------------------------------------------------------------
def test_transcriber_emits_only_allowlisted_ops():
    plan = _populated_plan()
    ops = BpyTranscriber().transcribe(plan)
    allowed = {op.value for op in BpyOpCode}
    assert all(op.op.value in allowed for op in ops)
    # structural: NEW_SCENE first, SAVE_BLEND last
    assert ops[0].op == BpyOpCode.NEW_SCENE
    assert ops[-1].op == BpyOpCode.SAVE_BLEND
    # never emits arbitrary execution ops
    assert all(op.op not in {BpyOpCode.RUN_ARBITRARY_PY,
                              BpyOpCode.MODULE_IMPORT, BpyOpCode.EXEC_TEXT} for op in ops)


def test_transcriber_set_frame_range_from_plan():
    plan = _populated_plan()
    ops = BpyTranscriber().transcribe(plan)
    frame_ops = [o for o in ops if o.op == BpyOpCode.SET_FRAME_RANGE]
    assert frame_ops
    assert frame_ops[0].args["end"] == 120
    assert frame_ops[0].args["fps"] == 24


def test_guard_rejects_code_in_description():
    guard = CompilerOperationGuard()
    with pytest.raises(UnsafeCompilerOperationError):
        guard.guard_string("table with __import__('os').system('x')", "description")
    with pytest.raises(UnsafeCompilerOperationError):
        guard.guard_string("perform exec('malicious')", "metadata")


def test_guard_rejects_code_in_plan():
    plan = _populated_plan().model_copy(update={
        "metadata": {"note": "evil import os; os.system('rm -rf /')"},
    })
    with pytest.raises(UnsafeCompilerOperationError):
        CompilerOperationGuard().guard_plan(plan)


def test_guard_accepts_benign_text():
    guard = CompilerOperationGuard()
    guard.guard_string("Mai walks to the oak desk under warm sunlight", "action")


# ---------------------------------------------------------------------------
# backlog 5 — save -> reopen -> inspect -> publish
# ---------------------------------------------------------------------------
def test_inspector_publishes_when_matching():
    plan = _populated_plan()
    snapshot = BlendSnapshot(plan=plan)
    receipt = BlendInspector().inspect(
        receipt_id=BlendInspectionReceiptId("insp-1"), plan=plan, snapshot=snapshot)
    assert receipt.valid is True
    assert receipt.published is True
    assert receipt.issues == []


def test_inspector_fails_closed_on_drift():
    plan = _populated_plan()
    # simulate a reopened blend with an extra unplanned object + frame mismatch
    snapshot = BlendSnapshot(plan=plan)
    snapshot._object_ids = snapshot.object_ids() + ["HACK-object"]
    snapshot._frame = {"start": 1, "end": 999, "fps": 24}
    receipt = BlendInspector().inspect(
        receipt_id=BlendInspectionReceiptId("insp-2"), plan=plan, snapshot=snapshot)
    assert receipt.valid is False
    assert receipt.published is False
    codes = {i.code for i in receipt.issues}
    assert "OBJECT_NAME_MISMATCH" in codes and "FRAME_RANGE_MISMATCH" in codes


def test_inspector_frame_range_preserved_on_reopen():
    plan = _populated_plan()
    snapshot = BlendSnapshot(plan=plan)
    assert snapshot.frame_range()["end"] == plan.frame_range.end


# ---------------------------------------------------------------------------
# backlog 6 — IR -> data-block mapping manifest
# ---------------------------------------------------------------------------
def test_mapping_manifest_hashes_and_reconciles():
    manifest = IrMappingManifest(
        manifest_id=IrMappingManifestId("map-1"), plan_id=BlenderScenePlanId("plan-1"),
        entries=[IrMappingEntry(
            ir_entity_id="ci-1", ir_entity_type="CHARACTER_INSTANCE",
            datablock_name="obj-mai", asset_revision_hash=HASH64)],
    )
    mh = manifest.compute_hash()
    assert len(mh) == 64
    assert manifest.reconcile_mapping() is True


# ---------------------------------------------------------------------------
# backlog 7 — incremental compile
# ---------------------------------------------------------------------------
def test_incremental_reuses_unchanged_blend():
    svc = IncrementalCompileService()
    st = svc.compile_scene(ir_hash=HASH64, existing_blend_ir_hash=HASH64,
                           changed_tracks=[])
    assert st == CompileStatus.REUSED


def test_incremental_rebuilds_on_track_change():
    svc = IncrementalCompileService()
    st = svc.compile_scene(ir_hash=HASH64, existing_blend_ir_hash=HASH64,
                           changed_tracks=["at-1"])
    assert st == CompileStatus.BUILT_DEPENDENT


def test_incremental_rebuilds_when_no_hash():
    svc = IncrementalCompileService()
    assert svc.compile_scene(ir_hash=HASH64, existing_blend_ir_hash=None,
                             changed_tracks=[]) == CompileStatus.BUILT_DEPENDENT


def test_incremental_built_on_new_input():
    svc = IncrementalCompileService()
    assert svc.compile_scene(ir_hash=HASH64, existing_blend_ir_hash="b" * 64,
                             changed_tracks=[]) == CompileStatus.BUILT


def test_invalidated_scope_for_prop_change_is_object_only():
    svc = IncrementalCompileService()
    assert svc.affected_by(changed_field="object") == PlanAffected.OBJECT
    assert svc.affected_by(changed_field="frame_range") == PlanAffected.ALL
    assert svc.affected_by(changed_field="animation") == PlanAffected.ANIMATION
