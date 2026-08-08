"""VP3D Phase 15 — Animation Layer V1: Library + Mocap unit tests (stage_h §3/§6).

Covers the §6 animation matrix:

- all 13 library clips (idle, walk, run, jump, sit, stand, talk, laugh, cry,
  point, wave, pick-up, put-down) are registered, versioned, carry provenance
  and a deterministic content hash;
- intent resolution is by actor/action/emotion/destination/duration +
  compatible skeleton — NEVER display name; missing action, incompatible
  skeleton and missing destination fail closed;
- retarget normalizes fps/root motion/units through a Stage D profile;
  non-resamplable clips and missing semantic bones fail closed;
- time-warp is bounded [0.5, 2.0]; outside the band the compile fails closed
  (pick another clip or request a plan revision);
- blend transitions keep stable frame boundaries; excess overlap fails
  closed (ownership/conflict is never silent);
- episode pins lock a clip revision: a library update changes nothing for a
  pinned episode, and any other revision fails closed;
- fps/duration mismatch and root drift are DETECTED and blocking;
- a failed compile never publishes a track; tracks are immutable;
- companion (facial/audio) changes with unchanged timing never invalidate
  the body clip; a body change invalidates ONLY the animation preview.
"""

from __future__ import annotations

import hashlib

import pytest
from windagent_core.domain.video_production.animation import (
    AnimationClip,
    AnimationFindingKind,
    AnimationIntent,
    AnimationValidator,
    ClipProvenance,
)
from windagent_core.domain.video_production.enums import (
    AnimationAction,
    AnimationEmotion,
    ClipSource,
    CompatibilityVerdict,
    LicenseState,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import (
    AnimationCompileError,
    AnimationPinMismatchError,
    ClipRetargetError,
)
from windagent_core.domain.video_production.ids import (
    AnimationClipId,
    AnimationIntentId,
    RetargetProfileId,
    SkeletonProfileId,
)
from windagent_intelligence.video.animation import (
    ANIMATION_COMPILER_LAYER_VERSION,
    ANIMATION_LIBRARY_VERSION,
    AnimationCompiler,
    AnimationLibrary,
    all_clips,
    resolve_clip,
    supported_clip_actions,
)
from windagent_intelligence.video.animation.library import (
    COMPATIBLE_SKELETONS,
    REQUIRED_HUMANOID_BONES,
)
from windagent_intelligence.video.errors import ValidationFailureError


def _h(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _bones() -> list[SemanticBone]:
    return list(REQUIRED_HUMANOID_BONES)


def _intent(
    action: AnimationAction = AnimationAction.WALK,
    shot: str = "ai-1",
    emotion: AnimationEmotion = AnimationEmotion.HAPPY,
    destination: str = "chair_03",
    fps: int = 24,
    duration_seconds: float | None = None,
    episode_id: str = "ep-1",
    metadata: dict | None = None,
) -> AnimationIntent:
    return AnimationIntent(
        intent_id=AnimationIntentId(f"ai-{shot}"),
        actor_id="char_01",
        action=action,
        emotion=emotion,
        destination=destination,
        fps=fps,
        duration_seconds=duration_seconds,
        skeleton_profile_id=SkeletonProfileId("skel_humanoid_standard"),
        episode_id=episode_id,
        metadata=metadata or {},
    )


COMPILER = AnimationCompiler()


# ---------------------------------------------------------------------------
# Library (backlog 1/2)
# ---------------------------------------------------------------------------
def test_all_thirteen_clips_are_registered_and_versioned():
    assert supported_clip_actions() == [
        "IDLE", "WALK", "RUN", "JUMP", "SIT", "STAND", "TALK", "LAUGH",
        "CRY", "POINT", "WAVE", "PICK_UP", "PUT_DOWN",
    ]
    clips = all_clips()
    assert len(clips) == 13
    for clip in clips:
        assert clip.version == ANIMATION_LIBRARY_VERSION
        assert clip.content_hash()
        assert clip.provenance.source == ClipSource.MOCAP_CAPTURE


def test_clips_carry_provenance_and_license():
    walk = resolve_clip(action=AnimationAction.WALK, target_bones=_bones())
    assert walk.provenance.provider == "library"
    assert walk.provenance.license == LicenseState.LICENSED
    assert walk.root_motion_meters == pytest.approx(1.6)
    assert walk.compatible_skeleton_ids == COMPATIBLE_SKELETONS


def test_clip_content_hash_is_deterministic_and_provenance_stable():
    a = resolve_clip(action=AnimationAction.RUN, target_bones=_bones())
    b = resolve_clip(action=AnimationAction.RUN, target_bones=_bones())
    assert a.content_hash() == b.content_hash()
    # imported_at is excluded from the hash (recording provenance)
    c = a.model_copy(update={"provenance": a.provenance.model_copy(
        update={"imported_at": "2026-08-08T00:00:00Z"})})
    assert c.content_hash() == a.content_hash()


# ---------------------------------------------------------------------------
# Resolution (backlog 3 — never display name)
# ---------------------------------------------------------------------------
def test_resolution_exact_action_emotion():
    clip = resolve_clip(
        action=AnimationAction.LAUGH, emotion=AnimationEmotion.HAPPY,
        target_bones=_bones())
    assert clip.action == AnimationAction.LAUGH
    assert clip.emotion == AnimationEmotion.HAPPY


def test_resolution_emotion_falls_back_to_neutral():
    # no walk+FEARFUL clip exists; NEUTRAL walk must be chosen
    clip = resolve_clip(
        action=AnimationAction.WALK, emotion=AnimationEmotion.FEARFUL,
        target_bones=_bones())
    assert clip.action == AnimationAction.WALK
    assert clip.emotion == AnimationEmotion.NEUTRAL


def test_resolution_never_uses_display_name():
    # a clip NAMED "walk" with action=IDLE must never resolve as WALK
    decoy = AnimationClip(
        clip_id=AnimationClipId("acl_decoy_name"),
        name="walk",
        action=AnimationAction.IDLE,
        skeleton_profile_id=SkeletonProfileId("skel_library_humanoid"),
        required_bones=list(REQUIRED_HUMANOID_BONES),
        duration_seconds=4.0,
        fps=30,
        root_motion_meters=0.0,
        provenance=ClipProvenance(source=ClipSource.LIBRARY),
    )
    library = AnimationLibrary(clips=[decoy])
    with pytest.raises(AnimationCompileError) as exc:
        library.resolve(action=AnimationAction.WALK, target_bones=_bones())
    assert exc.value.details["kind"] == "MISSING_ACTION"
    # the same clip IS the IDLE resolution (by action field, not name)
    assert library.resolve(
        action=AnimationAction.IDLE, target_bones=_bones()).clip_id \
        == decoy.clip_id


def test_resolution_missing_action_fails_closed():
    # a library without any WALK clip cannot resolve a WALK intent
    no_walk = AnimationLibrary(clips=[
        c for c in all_clips() if c.action != AnimationAction.WALK])
    with pytest.raises(AnimationCompileError) as exc:
        no_walk.resolve(action=AnimationAction.WALK, target_bones=_bones())
    assert exc.value.details["kind"] == "MISSING_ACTION"


def test_resolution_incompatible_skeleton_fails_closed():
    # a hand skeleton with no bones can never satisfy required_bones
    with pytest.raises(AnimationCompileError) as exc:
        resolve_clip(action=AnimationAction.WALK, target_bones=[])
    assert exc.value.details["kind"] == "INCOMPATIBLE_SKELETON"
    # a partial skeleton (legs only) fails for a full-body clip
    partial = [SemanticBone.ROOT, SemanticBone.THIGH_L, SemanticBone.THIGH_R]
    with pytest.raises(AnimationCompileError) as exc:
        resolve_clip(action=AnimationAction.WALK, target_bones=partial)
    assert exc.value.details["kind"] == "INCOMPATIBLE_SKELETON"


def test_resolution_missing_destination_fails_closed():
    with pytest.raises(AnimationCompileError) as exc:
        resolve_clip(action=AnimationAction.PICK_UP, target_bones=_bones(),
                     destination=None)
    assert exc.value.details["kind"] == "MISSING_DESTINATION"
    clip = resolve_clip(action=AnimationAction.PICK_UP, target_bones=_bones(),
                        destination="table_01")
    assert clip.action == AnimationAction.PICK_UP


# ---------------------------------------------------------------------------
# Retarget (backlog 4)
# ---------------------------------------------------------------------------
def test_retarget_normalizes_fps_units_and_root_motion():
    intent = _intent(fps=24)
    receipt = COMPILER.compile(intent=intent, target_bones=_bones()).retarget
    assert receipt.source_fps == 30
    assert receipt.target_fps == 24
    assert receipt.resample_ratio == pytest.approx(0.8)
    assert receipt.units_normalized is True
    # displacement preserved; meters/second normalized
    assert receipt.root_motion_meters == pytest.approx(1.6)
    assert receipt.root_motion_mps == pytest.approx(0.8)


def test_retarget_with_stage_d_profile_records_profile_id():
    profile_id = RetargetProfileId("rp_humanoid_mixamo")
    receipt = COMPILER.retarget_service.build_receipt(
        clip=_walk_clip(COMPILER), target_fps=24, target_bones=_bones(),
        retarget_profile_id=profile_id,
        retarget_profile_hash=_h("profile-v1"))
    assert str(receipt.retarget_profile_id) == "rp_humanoid_mixamo"
    assert receipt.retarget_profile_hash == _h("profile-v1")


def _walk_clip(compiler: AnimationCompiler):
    return compiler.library.resolve(
        action=AnimationAction.WALK, target_bones=_bones())


def test_retarget_non_resamplable_clip_fails_closed():
    locked = _walk_clip(COMPILER).model_copy(update={"resamplable": False})
    library = AnimationLibrary(
        clips=[c for c in all_clips() if c.action != AnimationAction.WALK]
        + [locked])
    compiler = AnimationCompiler(library=library)
    with pytest.raises(ClipRetargetError) as exc:
        compiler.compile(intent=_intent(fps=24), target_bones=_bones())
    assert exc.value.details["kind"] == "FPS_MISMATCH"


def test_retarget_missing_semantic_bones_fails_closed():
    compiler = AnimationCompiler()
    clip = _walk_clip(compiler)
    partial = [SemanticBone.ROOT, SemanticBone.HEAD]
    with pytest.raises(ClipRetargetError) as exc:
        compiler.retarget_service.build_receipt(
            clip=clip, target_fps=24, target_bones=partial)
    assert "missing_bones" in exc.value.details


# ---------------------------------------------------------------------------
# Time-warp (backlog 5)
# ---------------------------------------------------------------------------
def test_warp_in_bounds_applies():
    intent = _intent(duration_seconds=1.0)  # walk 2.0s -> 1.0s (ratio 0.5)
    receipt = COMPILER.compile(intent=intent, target_bones=_bones())
    assert receipt.warp.ratio == pytest.approx(0.5)
    assert receipt.track.frame_count == 24  # 1.0s * 24fps
    assert receipt.track.duration_seconds == pytest.approx(1.0)
    # root displacement preserved under warp
    assert receipt.track.root_motion_meters == pytest.approx(1.6)


def test_warp_out_of_bounds_fails_closed():
    # walk 2.0s -> 0.4s = ratio 0.2 < 0.5
    with pytest.raises(AnimationCompileError) as exc:
        COMPILER.compile(
            intent=_intent(duration_seconds=0.4), target_bones=_bones())
    assert exc.value.details["kind"] == "WARP_OUT_OF_BOUNDS"
    # 2.0s -> 6.0s = ratio 3.0 > 2.0
    with pytest.raises(AnimationCompileError) as exc:
        COMPILER.compile(
            intent=_intent(duration_seconds=6.0), target_bones=_bones())
    assert exc.value.details["kind"] == "WARP_OUT_OF_BOUNDS"


def test_duration_mismatch_detected():
    # hand-built track whose frames disagree with the intent's duration
    intent = _intent(duration_seconds=2.0)
    clip = _walk_clip(COMPILER)
    good = COMPILER.compile(intent=intent, target_bones=_bones()).track
    report = AnimationValidator().validate_track(
        intent=intent, clip=clip,
        track=good.model_copy(update={
            "start_frame": 0, "end_frame": 40,  # 40 != 48
            "content_hash": ""}))
    assert AnimationFindingKind.DURATION_MISMATCH in report.blocking_kinds


# ---------------------------------------------------------------------------
# Determinism + companion refs + invalidation (§5/§6)
# ---------------------------------------------------------------------------
def test_same_input_same_track_hash():
    a = COMPILER.compile(intent=_intent(), target_bones=_bones())
    b = COMPILER.compile(intent=_intent(), target_bones=_bones())
    assert a.track.content_hash == b.track.content_hash
    assert a.track.track_id == b.track.track_id


def test_companion_change_keeps_track_hash():
    base = COMPILER.compile(intent=_intent(), target_bones=_bones()).track
    with_companion = COMPILER.compile(
        intent=_intent(metadata={"companion_refs": {
            "facial": "ft-1", "audio": "at-1"}}),
        target_bones=_bones()).track
    assert with_companion.companion_refs == {
        "facial": "ft-1", "audio": "at-1"}
    # §6: replacing facial/audio track with unchanged timing keeps the body
    # clip hash -> nothing invalidates
    assert with_companion.content_hash == base.content_hash


def test_invalidation_scoped_to_animation_preview_only():
    intent = _intent()
    first = COMPILER.compile(intent=intent, target_bones=_bones())
    assert first.invalidated_artifacts == []
    # unchanged body -> reuse, nothing invalidated
    same = COMPILER.compile(intent=intent, target_bones=_bones(),
                            prior_track_hash=first.track.content_hash)
    assert same.invalidated_artifacts == []
    # changed body (different clip) -> ONLY the animation preview
    changed = COMPILER.compile(
        intent=_intent(action=AnimationAction.RUN),
        target_bones=_bones(),
        prior_track_hash=first.track.content_hash)
    assert changed.invalidated_artifacts == [
        f"animation/preview:{changed.track.track_id}"]


# ---------------------------------------------------------------------------
# Blend transitions (backlog 6)
# ---------------------------------------------------------------------------
def test_blend_plan_stable_boundary():
    walk = COMPILER.compile(intent=_intent(), target_bones=_bones()).track
    idle = COMPILER.compile(
        intent=_intent(shot="ai-b", action=AnimationAction.IDLE,
                       emotion=AnimationEmotion.NEUTRAL,
                       duration_seconds=None),
        target_bones=_bones(),
        start_frame=walk.end_frame - 4,  # 4-frame overlap <= 6-frame window
        blend_in_frames=6, blend_out_frames=6).track
    transition = COMPILER.plan_blend(track_a=walk, track_b=idle)
    assert transition.boundary_frame == walk.end_frame  # stable boundary
    assert transition.blend_window_frames == 6
    assert transition.from_track_id == walk.track_id
    assert transition.to_track_id == idle.track_id


def test_blend_excess_overlap_fails_closed():
    walk = COMPILER.compile(intent=_intent(), target_bones=_bones()).track
    idle = COMPILER.compile(
        intent=_intent(shot="ai-b", action=AnimationAction.IDLE,
                       emotion=AnimationEmotion.NEUTRAL,
                       duration_seconds=None),
        target_bones=_bones(),
        start_frame=walk.end_frame - 10,  # 10-frame overlap > 6 window
        blend_in_frames=6, blend_out_frames=6).track
    with pytest.raises(AnimationCompileError) as exc:
        COMPILER.plan_blend(track_a=walk, track_b=idle)
    assert exc.value.details["kind"] == "OVERLAP_CONFLICT"
    assert exc.value.details["overlap_frames"] == 10


def test_overlap_conflict_detected_by_validator():
    intent = _intent()
    clip = _walk_clip(COMPILER)
    first = COMPILER.compile(intent=intent, target_bones=_bones()).track
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(
            intent=_intent(shot="ai-b", action=AnimationAction.IDLE,
                           emotion=AnimationEmotion.NEUTRAL,
                           duration_seconds=None),
            target_bones=_bones(),
            start_frame=first.end_frame - 10,  # no blend window declared
            previous_track=first)
    assert "OVERLAP_CONFLICT" in exc.value.details["kinds"]


def test_blend_across_actors_fails_closed():
    walk = COMPILER.compile(intent=_intent(), target_bones=_bones()).track
    other = walk.model_copy(update={"actor_id": "char_02"})
    with pytest.raises(AnimationCompileError) as exc:
        COMPILER.plan_blend(track_a=walk, track_b=other)
    assert exc.value.details["kind"] == "OVERLAP_CONFLICT"


# ---------------------------------------------------------------------------
# Episode pinning (backlog 7)
# ---------------------------------------------------------------------------
def test_episode_pin_locks_clip_revision_across_library_update():
    intent = _intent()
    first = COMPILER.compile(intent=intent, target_bones=_bones())
    clip_v1 = first.clip
    pin = COMPILER.pin(episode_id="ep-1", actor_id="char_01", clip=clip_v1)

    # library updates to v2 (longer clips)
    v2_clips = [
        c.model_copy(update={"version": "2.0.0",
                             "duration_seconds": c.duration_seconds * 1.1})
        for c in all_clips()
    ]
    upgraded = AnimationCompiler(library=AnimationLibrary(clips=v2_clips))

    # unpinned compile on the new library picks v2 -> changed body
    fresh = upgraded.compile(intent=intent, target_bones=_bones(),
                             prior_track_hash=first.track.content_hash)
    assert fresh.clip.version == "2.0.0"
    assert fresh.track.content_hash != first.track.content_hash
    assert fresh.invalidated_artifacts == [
        f"animation/preview:{fresh.track.track_id}"]

    # pinned episode keeps compiling against v1 -> identical track hash,
    # nothing invalidates (locked production unchanged)
    locked = upgraded.compile(intent=intent, target_bones=_bones(),
                              pin=pin, pinned_clip=clip_v1,
                              prior_track_hash=first.track.content_hash)
    assert locked.clip.version == "1.0.0"
    assert locked.track.content_hash == first.track.content_hash
    assert locked.invalidated_artifacts == []


def test_episode_pin_mismatch_fails_closed():
    intent = _intent()
    clip_v1 = COMPILER.compile(intent=intent, target_bones=_bones()).clip
    pin = COMPILER.pin(episode_id="ep-1", actor_id="char_01", clip=clip_v1)
    v2 = clip_v1.model_copy(update={"version": "2.0.0"})
    with pytest.raises(AnimationPinMismatchError) as exc:
        COMPILER.compile(intent=intent, target_bones=_bones(),
                         pin=pin, pinned_clip=v2)
    assert exc.value.details["pinned_version"] == "1.0.0"
    assert exc.value.details["given_version"] == "2.0.0"


def test_pinned_episode_without_clip_fails_closed():
    intent = _intent()
    clip_v1 = COMPILER.compile(intent=intent, target_bones=_bones()).clip
    pin = COMPILER.pin(episode_id="ep-1", actor_id="char_01", clip=clip_v1)
    with pytest.raises(AnimationPinMismatchError):
        COMPILER.compile(intent=intent, target_bones=_bones(), pin=pin)


# ---------------------------------------------------------------------------
# Validation negative matrix (§6)
# ---------------------------------------------------------------------------
def test_root_drift_detected():
    intent = _intent()
    clip = _walk_clip(COMPILER)
    good = COMPILER.compile(intent=intent, target_bones=_bones()).track
    drifted = good.model_copy(update={
        "root_motion_meters": 2.0,  # 1.6 expected -> 25% drift
        "content_hash": ""})
    report = AnimationValidator().validate_track(
        intent=intent, clip=clip, track=drifted)
    assert AnimationFindingKind.ROOT_DRIFT in report.blocking_kinds
    assert report.blocking_findings[0].measured["drift"] > 0.10


def test_fps_mismatch_in_track_detected():
    intent = _intent(fps=24)
    clip = _walk_clip(COMPILER)
    good = COMPILER.compile(intent=intent, target_bones=_bones()).track
    wrong_fps = good.model_copy(update={"fps": 12, "content_hash": ""})
    report = AnimationValidator().validate_track(
        intent=intent, clip=clip, track=wrong_fps)
    assert AnimationFindingKind.FPS_MISMATCH in report.blocking_kinds


def test_warp_bounds_in_track_detected():
    intent = _intent()
    clip = _walk_clip(COMPILER)
    good = COMPILER.compile(intent=intent, target_bones=_bones()).track
    stretched = good.model_copy(update={"warp_ratio": 3.0,
                                        "content_hash": ""})
    report = AnimationValidator().validate_track(
        intent=intent, clip=clip, track=stretched)
    assert AnimationFindingKind.WARP_OUT_OF_BOUNDS in report.blocking_kinds


def test_failed_compile_never_publishes_a_track():
    # warp out of bounds -> AnimationCompileError, no track object exists
    with pytest.raises(AnimationCompileError):
        COMPILER.compile(
            intent=_intent(action=AnimationAction.RUN,
                           duration_seconds=6.0),  # ratio 5.0 -> warp OOB
            target_bones=_bones())
    with pytest.raises(AnimationCompileError):
        COMPILER.compile(intent=_intent(duration_seconds=0.4),
                         target_bones=_bones())
    # validation failure (overlap conflict) -> ValidationFailureError
    first = COMPILER.compile(intent=_intent(), target_bones=_bones()).track
    with pytest.raises(ValidationFailureError):
        COMPILER.compile(
            intent=_intent(shot="ai-b", action=AnimationAction.IDLE,
                           emotion=AnimationEmotion.NEUTRAL,
                           duration_seconds=None),
            target_bones=_bones(),
            start_frame=first.end_frame - 10,  # no blend window declared
            previous_track=first)


def test_track_is_immutable_frozen():
    track = COMPILER.compile(intent=_intent(), target_bones=_bones()).track
    with pytest.raises(ValueError):
        track.actor_id = "other"  # frozen attribute assignment


def test_compiler_layer_version_is_pinned():
    assert ANIMATION_COMPILER_LAYER_VERSION == "1.0.0"
    assert ANIMATION_LIBRARY_VERSION == "1.0.0"


def test_intent_resolution_matches_roadmap_example():
    # road_map.md Phase 15: AnimationIntent(actor="char_01", action="walk",
    # destination="chair_03", emotion="happy")
    clip = COMPILER.resolve_clip(
        intent=_intent(action=AnimationAction.WALK,
                       emotion=AnimationEmotion.HAPPY,
                       destination="chair_03"),
        target_bones=_bones())[0]
    assert clip.action == AnimationAction.WALK
    assert clip.emotion == AnimationEmotion.NEUTRAL  # neutral fallback
