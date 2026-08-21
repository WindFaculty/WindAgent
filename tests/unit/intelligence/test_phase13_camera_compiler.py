"""VP3D Phase 13 — Blender Camera Compiler unit tests (stage_g §3/§5).

Covers the full §5 test matrix:

- camera movement quá ngắn (too fast), path xuyên geometry (collision),
  subject ra khỏi frame (out of frame), camera-side flip (180 rule),
  lens bounds, path discontinuity, dialogue timing violation;
- dialogue coverage: eyeline/screen direction kept across
  master -> over-shoulder -> reaction;
- same intent/compiler version -> identical rig manifest hash (determinism);
- changing the camera invalidates only the shot's preview/render, never
  asset/rig/audio (invalidation scope);
- manual camera override pin: respected when matching, fails closed when the
  track revision drifts (backlog 7);
- occlusion preflight samples MULTIPLE frames for moving cameras (backlog 5);
- no bpy / no code-execution markers anywhere in the compiler layer.
"""

from __future__ import annotations

import hashlib

import pytest
from windagent_core.domain.video_production.cinematography import (
    CameraFindingKind,
    CameraIntent,
    CameraKeyframe,
    CameraOverride,
    CameraPath,
    FocusPlan,
    FramingConstraint,
    LensProfile,
)
from windagent_core.domain.video_production.enums import (
    CameraAngle,
    CameraMovement,
    CameraSide,
    EasingKind,
    ScreenDirection,
)
from windagent_core.domain.video_production.errors import (
    CameraOverridePinMismatchError,
)
from windagent_core.domain.video_production.ids import (
    CameraIntentId,
    CameraOverrideId,
    DialogueLineId,
    SceneId,
    ShotId,
)
from windagent_core.domain.video_production.set_dressing import (
    Aabb,
    ForbiddenVolume,
    Vec3,
)
from windagent_intelligence.video.camera.camera_compiler import CameraCompiler
from windagent_intelligence.video.camera.occlusion_preflight import (
    OcclusionPreflight,
)
from windagent_intelligence.video.camera.playblast import (
    PlayblastManifestBuilder,
)
from windagent_intelligence.video.camera.rig_primitives import (
    RIG_PRIMITIVES_VERSION,
    resolve_primitive,
)
from windagent_intelligence.video.errors import ValidationFailureError


def _h(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _lens(focal: float = 35.0) -> LensProfile:
    return LensProfile(focal_mm=focal, sensor_width_mm=36.0)


def _focus(distance: float = 3.0) -> FocusPlan:
    return FocusPlan(focus_distance_m=distance,
                     dof_near_m=max(0.1, distance - 1.0),
                     dof_far_m=distance + 2.0)


def _intent(
    shot: str = "sh-1",
    movement: CameraMovement = CameraMovement.STATIC,
    side: CameraSide = CameraSide.SIDE_A,
    direction: ScreenDirection = ScreenDirection.NEUTRAL,
    duration: float = 3.0,
    focal: float = 35.0,
    path=None,
    dialogue=None,
    fps: int = 24,
) -> CameraIntent:
    path = path or CameraPath(keyframes=[
        CameraKeyframe(frame=0, position=Vec3(x=0.0, y=-5.0, z=1.6),
                       look_at=Vec3(x=0.0, y=0.0, z=1.2)),
    ])
    return CameraIntent(
        intent_id=CameraIntentId(f"ci-{shot}"),
        shot_id=ShotId(shot),
        scene_id=SceneId("sc-1"),
        movement=movement,
        angle=CameraAngle.EYE_LEVEL,
        side=side,
        screen_direction=direction,
        lens=_lens(focal),
        focus=_focus(),
        framing=FramingConstraint(),
        path=path,
        duration_seconds=duration,
        fps=fps,
        dialogue_timing=dialogue or [],
    )


SUBJECT = Aabb(min=Vec3(x=-0.5, y=-0.5, z=0.0),
               max=Vec3(x=0.5, y=0.5, z=1.6))
FACING = Vec3(x=0.0, y=1.0, z=0.0)
COMPILER = CameraCompiler()


# ---------------------------------------------------------------------------
# §5 matrix: each failure mode must be DETECTED
# ---------------------------------------------------------------------------
def test_camera_movement_too_short_detected():
    path = CameraPath(keyframes=[
        CameraKeyframe(frame=0, position=Vec3(x=0, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
        CameraKeyframe(frame=24, position=Vec3(x=0, y=5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
    ])
    intent = _intent("sh-fast", movement=CameraMovement.DOLLY,
                     duration=0.2, path=path)
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                         subject_facing=FACING)
    assert "MOTION_TOO_FAST" in exc.value.details["kinds"]


def test_path_through_geometry_detected():
    wall = ForbiddenVolume(name="wall",
                           bounds=Aabb(min=Vec3(x=-1, y=-0.3, z=0),
                                       max=Vec3(x=1, y=0.3, z=3)))
    # camera dollies THROUGH the wall: path segment crosses the volume
    path = CameraPath(keyframes=[
        CameraKeyframe(frame=0, position=Vec3(x=0, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
        CameraKeyframe(frame=24, position=Vec3(x=0, y=5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
    ])
    intent = _intent("sh-collide", movement=CameraMovement.DOLLY, path=path)
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                         subject_facing=FACING,
                         forbidden_volumes=[wall])
    assert "CAMERA_COLLISION" in exc.value.details["kinds"]


def test_subject_out_of_frame_detected():
    # camera looks AWAY from the subject
    path = CameraPath(keyframes=[
        CameraKeyframe(frame=0, position=Vec3(x=0, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=-10, z=1.2)),
    ])
    intent = _intent("sh-away", path=path)
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                         subject_facing=FACING)
    assert "SUBJECT_OUT_OF_FRAME" in exc.value.details["kinds"]


def test_camera_side_flip_detected():
    previous = _intent("sh-master", side=CameraSide.SIDE_A,
                       direction=ScreenDirection.LEFT_TO_RIGHT)
    flipped = _intent("sh-os", side=CameraSide.SIDE_B,
                      direction=ScreenDirection.LEFT_TO_RIGHT)
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=flipped, previous_intent=previous,
                         subject_bounds=SUBJECT, subject_facing=FACING)
    assert "SIDE_FLIP" in exc.value.details["kinds"]


def test_screen_direction_flip_detected():
    previous = _intent("sh-a", side=CameraSide.SIDE_A,
                       direction=ScreenDirection.LEFT_TO_RIGHT)
    flipped = _intent("sh-b", side=CameraSide.SIDE_A,
                      direction=ScreenDirection.RIGHT_TO_LEFT)
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=flipped, previous_intent=previous,
                         subject_bounds=SUBJECT, subject_facing=FACING)
    assert "SCREEN_DIRECTION_FLIP" in exc.value.details["kinds"]


def test_lens_out_of_bounds_detected():
    intent = _intent("sh-lens", focal=500.0)
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                         subject_facing=FACING)
    assert "LENS_OUT_OF_BOUNDS" in exc.value.details["kinds"]


def test_focus_target_invalid_detected():
    intent = _intent("sh-focus")
    bad = intent.model_copy(update={"focus": FocusPlan(
        focus_distance_m=10.0, dof_near_m=1.0, dof_far_m=2.0)})
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=bad, subject_bounds=SUBJECT,
                         subject_facing=FACING)
    assert "FOCUS_INVALID" in exc.value.details["kinds"]


def test_path_discontinuity_detected():
    path = CameraPath(keyframes=[
        CameraKeyframe(frame=0, position=Vec3(x=0, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
        CameraKeyframe(frame=1, position=Vec3(x=0, y=50, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
    ])
    intent = _intent("sh-jump", movement=CameraMovement.DOLLY, path=path)
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                         subject_facing=FACING)
    assert "PATH_DISCONTINUITY" in exc.value.details["kinds"]


def test_dialogue_timing_outside_shot_detected():
    from windagent_core.domain.video_production.cinematography import (
        DialogueTiming,
    )
    intent = _intent("sh-dlg", duration=2.0, dialogue=[
        DialogueTiming(line_id=DialogueLineId("dl-1"),
                       start_second=0.0, end_second=3.0),  # longer than shot
    ])
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                         subject_facing=FACING)
    assert "DIALOGUE_TIMING_VIOLATION" in exc.value.details["kinds"]


def test_head_room_violation_detected():
    # camera very low and close: subject head projects above the head-room line
    path = CameraPath(keyframes=[
        CameraKeyframe(frame=0, position=Vec3(x=0, y=-0.9, z=0.1),
                       look_at=Vec3(x=0, y=0, z=0.8)),
    ])
    intent = _intent("sh-head", path=path)
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                         subject_facing=FACING)
    assert "HEAD_ROOM_VIOLATION" in exc.value.details["kinds"]


# ---------------------------------------------------------------------------
# Dialogue coverage: eyeline + screen direction kept across coverage shots
# ---------------------------------------------------------------------------
def test_dialogue_coverage_keeps_eyeline_and_screen_direction():
    master = _intent("sh-master", side=CameraSide.SIDE_A,
                     direction=ScreenDirection.LEFT_TO_RIGHT)
    os = _intent("sh-os", side=CameraSide.SIDE_A,
                 direction=ScreenDirection.LEFT_TO_RIGHT)
    reaction = _intent("sh-reaction", side=CameraSide.SIDE_A,
                       direction=ScreenDirection.LEFT_TO_RIGHT)
    # NEUTRAL shots (insert/POV/transition) never flip the line
    insert = _intent("sh-insert", side=CameraSide.NEUTRAL,
                     direction=ScreenDirection.NEUTRAL)

    receipt = COMPILER.compile(intent=master, subject_bounds=SUBJECT,
                               subject_facing=FACING)
    assert receipt.cleaned_ok and receipt.plan.plan_hash
    receipt2 = COMPILER.compile(intent=os, previous_intent=master,
                                subject_bounds=SUBJECT,
                                subject_facing=FACING)
    assert receipt2.cleaned_ok
    receipt3 = COMPILER.compile(intent=reaction, previous_intent=os,
                                subject_bounds=SUBJECT,
                                subject_facing=FACING)
    assert receipt3.cleaned_ok
    receipt4 = COMPILER.compile(intent=insert, previous_intent=reaction,
                                subject_bounds=SUBJECT,
                                subject_facing=FACING)
    assert receipt4.cleaned_ok


# ---------------------------------------------------------------------------
# Determinism + invalidation
# ---------------------------------------------------------------------------
def test_same_input_same_rig_manifest_hash():
    a = COMPILER.compile(intent=_intent(), subject_bounds=SUBJECT,
                         subject_facing=FACING)
    b = COMPILER.compile(intent=_intent(), subject_bounds=SUBJECT,
                         subject_facing=FACING)
    assert a.plan.plan_hash == b.plan.plan_hash
    assert a.plan.primitive_id == b.plan.primitive_id
    assert a.plan.primitive_version == RIG_PRIMITIVES_VERSION


def test_changed_intent_changes_hash_and_invalidates_only_shot():
    base = COMPILER.compile(intent=_intent(), subject_bounds=SUBJECT,
                            subject_facing=FACING)
    assert base.invalidated_shot_ids == []  # no prior artifact

    changed = _intent("sh-1", focal=50.0)
    receipt = COMPILER.compile(intent=changed, subject_bounds=SUBJECT,
                               subject_facing=FACING,
                               prior_plan_hash=base.plan.plan_hash)
    assert receipt.plan.plan_hash != base.plan.plan_hash
    # stage_g §5: camera change invalidates ONLY the shot's camera/preview;
    # asset/rig/audio carry their own revision hashes and are untouched.
    assert receipt.invalidated_shot_ids == ["sh-1"]

    same = COMPILER.compile(intent=_intent(), subject_bounds=SUBJECT,
                            subject_facing=FACING,
                            prior_plan_hash=base.plan.plan_hash)
    assert same.invalidated_shot_ids == []


def test_frame_range_from_duration_and_fps():
    intent = _intent("sh-frames", duration=2.0, fps=24)
    receipt = COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                               subject_facing=FACING)
    assert receipt.plan.start_frame == 1
    assert receipt.plan.end_frame == 48  # 2.0s * 24fps


# ---------------------------------------------------------------------------
# Rig primitives (backlog 1)
# ---------------------------------------------------------------------------
def test_all_movements_resolve_to_versioned_primitives():
    # stage_g §3: exactly STATIC/PAN/TILT/DOLLY/TRACK/CRANE map to primitives;
    # HANDHELD is not a versioned rig primitive and fails closed.
    from windagent_core.domain.video_production.errors import CameraCompileError

    for movement in (CameraMovement.STATIC, CameraMovement.PAN,
                     CameraMovement.TILT, CameraMovement.DOLLY,
                     CameraMovement.TRACK, CameraMovement.CRANE):
        primitive = resolve_primitive(movement)
        assert primitive.primitive_id.startswith("cam_rig/")
        assert primitive.version == RIG_PRIMITIVES_VERSION
    assert resolve_primitive(CameraMovement.STATIC).motion_axes == []
    assert resolve_primitive(CameraMovement.PAN).motion_axes == ["yaw"]
    assert resolve_primitive(CameraMovement.DOLLY).motion_axes == ["forward"]
    with pytest.raises(CameraCompileError):
        resolve_primitive(CameraMovement.HANDHELD)


def test_rig_plan_embeds_primitive_and_easing():
    path = CameraPath(keyframes=[
        CameraKeyframe(frame=0, position=Vec3(x=0, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2),
                       easing=EasingKind.EASE_IN_OUT),
    ])
    intent = _intent("sh-prim", movement=CameraMovement.TRACK, path=path)
    receipt = COMPILER.compile(intent=intent, subject_bounds=SUBJECT,
                               subject_facing=FACING)
    assert receipt.plan.primitive_id == "cam_rig/track/v1"
    assert receipt.plan.path.keyframes[0].easing == EasingKind.EASE_IN_OUT


# ---------------------------------------------------------------------------
# Override pin (backlog 7)
# ---------------------------------------------------------------------------
def test_override_pin_respected_when_revision_matches():
    rev = _h("track-v3")
    override = CameraOverride(
        override_id=CameraOverrideId("covr-1"), shot_id=ShotId("sh-1"),
        pinned_track_revision=rev,
        position=Vec3(x=1.0, y=-6.0, z=2.0))
    receipt = COMPILER.compile(intent=_intent(), override=override,
                               track_revision=rev, subject_bounds=SUBJECT,
                               subject_facing=FACING)
    assert receipt.plan.override_id == "covr-1"
    assert receipt.plan.path.keyframes[0].position == Vec3(x=1.0, y=-6.0, z=2.0)


def test_override_pin_mismatch_fails_closed():
    override = CameraOverride(
        override_id=CameraOverrideId("covr-2"), shot_id=ShotId("sh-1"),
        pinned_track_revision=_h("track-v2"))
    with pytest.raises(CameraOverridePinMismatchError):
        COMPILER.compile(intent=_intent(), override=override,
                         track_revision=_h("track-v3"),
                         subject_bounds=SUBJECT, subject_facing=FACING)


def test_inactive_override_ignored():
    override = CameraOverride(
        override_id=CameraOverrideId("covr-3"), shot_id=ShotId("sh-1"),
        pinned_track_revision=_h("track-v1"), active=False)
    receipt = COMPILER.compile(intent=_intent(), override=override,
                               track_revision=_h("track-v9"),
                               subject_bounds=SUBJECT, subject_facing=FACING)
    assert receipt.plan.override_id == ""


# ---------------------------------------------------------------------------
# Occlusion preflight (backlog 5): multi-frame sampling for moving cameras
# ---------------------------------------------------------------------------
def test_occlusion_sampled_on_multiple_frames_for_moving_camera():
    path = CameraPath(keyframes=[
        CameraKeyframe(frame=0, position=Vec3(x=-3, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
        CameraKeyframe(frame=6, position=Vec3(x=-1.5, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
        CameraKeyframe(frame=12, position=Vec3(x=0, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
        CameraKeyframe(frame=18, position=Vec3(x=1.5, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
        CameraKeyframe(frame=24, position=Vec3(x=3, y=-5, z=1.6),
                       look_at=Vec3(x=0, y=0, z=1.2)),
    ])
    plan = COMPILER.compile(
        intent=_intent("sh-track", movement=CameraMovement.TRACK, path=path,
                       duration=2.0),
        subject_bounds=SUBJECT, subject_facing=FACING,
        occlusion_preflight=OcclusionPreflight()).plan

    pillar = ForbiddenVolume(name="pillar",
                             bounds=Aabb(min=Vec3(x=-3.0, y=-4.6, z=0),
                                         max=Vec3(x=3.0, y=-3.6, z=3)))
    findings = OcclusionPreflight().preflight(
        plan=plan, subject_bounds=SUBJECT, forbidden_volumes=[pillar])
    assert findings, "moving camera behind a pillar must be flagged"
    assert all(f.kind == CameraFindingKind.OCCLUSION for f in findings)
    frames = {f.frame for f in findings}
    assert len(frames) >= 2, (
        f"expected multi-frame sampling, got frames {sorted(frames)}")


def test_static_camera_samples_single_frame():
    plan = COMPILER.compile(
        intent=_intent("sh-static"), subject_bounds=SUBJECT,
        subject_facing=FACING,
        occlusion_preflight=OcclusionPreflight()).plan
    assert OcclusionPreflight()._sample_count(plan) == 1


# ---------------------------------------------------------------------------
# Playblast manifest (backlog 6)
# ---------------------------------------------------------------------------
def test_playblast_manifest_deterministic_and_carries_framing():
    builder = PlayblastManifestBuilder()
    plan = COMPILER.compile(intent=_intent(), subject_bounds=SUBJECT,
                            subject_facing=FACING).plan
    manifest = builder.build(plan=plan, subject_bounds=SUBJECT, sample_count=5)
    again = builder.build(plan=plan, subject_bounds=SUBJECT, sample_count=5)
    assert manifest.manifest_hash == again.manifest_hash
    assert manifest.samples and manifest.samples[0].subject_visible
    assert manifest.primitive_id.startswith("cam_rig/")
    assert manifest.keyframes[0]["easing"] == "LINEAR"


# ---------------------------------------------------------------------------
# Immutability + neutrality
# ---------------------------------------------------------------------------
def test_rig_plan_models_are_frozen():
    plan = COMPILER.compile(intent=_intent(), subject_bounds=SUBJECT,
                            subject_facing=FACING).plan
    with pytest.raises(ValueError):
        plan.fps = 30  # type: ignore[misc]


def test_compiler_layer_never_mentions_bpy_or_exec():
    import inspect
    import windagent_intelligence.video.camera as camera_pkg
    import windagent_core.domain.video_production.cinematography as cine

    for module in (camera_pkg, cine):
        text = inspect.getsource(module)
        assert "import bpy" not in text
        assert "bpy." not in text
        assert "eval(" not in text and "exec(" not in text
