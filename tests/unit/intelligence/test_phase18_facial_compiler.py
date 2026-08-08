"""VP3D Phase 18 — Facial pipeline unit tests (stage_i §3/§4).

Covers the backlog and the §4 quality matrix:
- normalize_phoneme_track (backlog 1): seconds->frames per fps + shot
  offset, source alignment hash preserved, monotonic + in-range fail-closed;
- viseme map (backlog 2): versioned by language + rig profile, explicit
  fallback rule for unknown phonemes, no silent skip;
- compile (backlog 3-6): coarticulation, min hold, bounded amplitude,
  silence no mouth movement, emotion never overlaps articulation,
  deterministic blink/gaze/head from seed, layer ownership + blend policy;
- validate (§4): monotonic ordering, shot range, drift at line start/mid/
  end within tolerance, silence check, facial pop, idle speech, head joint
  limit, low-confidence -> REQUIRES_HUMAN_REVIEW, rig missing controls ->
  REQUIRES_HUMAN_REVIEW;
- bake (backlog 7): derived action records compiler version + input hashes +
  frame range, non-APPROVED fails closed;
- repair (backlog 8): per-layer scope, invalidation only touches the layer
  + render/final, body clip untouched when timing unchanged;
- preview manifest (backlog 9) + determinism (same input/profile/seed ->
  same curve manifest hash).
"""

from __future__ import annotations

import pytest
from windagent_core.domain.video_production.concurrent_audio import (
    AlignmentResult,
)
from windagent_core.domain.video_production.enums import (
    AnimationEmotion,
    FacialFindingKind,
    FacialInvalidationScope,
    FacialLayerKind,
    FacialRepairScope,
    FacialTrackStatus,
    HeadBlendPolicy,
    VisemeShape,
)
from windagent_core.domain.video_production.errors import (
    FacialBakeError,
    FacialCompileError,
    FacialRepairError,
    VisemeMapMissingPhonemeError,
)
from windagent_core.domain.video_production.facial import (
    ARTICULATION_CONTROLS,
    DRIFT_TOLERANCE_FRAMES,
    FACIAL_COMPILER_VERSION,
    FACIAL_POP_MAX_DELTA,
    HEAD_JOINT_LIMIT_DEGREES,
    PhonemeTrack,
    VisemeMap,
    VisemeTarget,
    bake_facial_track,
    build_preview_manifest,
    build_viseme_map,
    compile_facial_track,
    normalize_phoneme_track,
    repair_facial_track,
    validate_facial_track,
)
from windagent_core.domain.video_production.ids import (
    BakedFacialActionId,
    EmotionCurveId,
    FacialRepairReceiptId,
    FacialTrackId,
    FacialValidationReceiptId,
    PhonemeTrackId,
    VisemeMapId,
)
from windagent_intelligence.video.facial import (
    VIETNAMESE_LINE_A,
    FacialAnimationCompiler,
    FacialCompileRequest,
    fake_alignment,
)

FPS = 24
SHOT_START = 100
SHOT_END = 300
RIG_CONTROLS = list(ARTICULATION_CONTROLS) + [
    "blink_l", "blink_r", "brow_raise_l", "brow_raise_r",
    "eye_target_x", "eye_target_y", "head_yaw", "head_pitch",
]


def _track(alignment: AlignmentResult,
           map_version: str = "1.0") -> PhonemeTrack:
    return normalize_phoneme_track(
        track_id=PhonemeTrackId("pt-p18-a"),
        alignment=alignment,
        fps=FPS,
        shot_start_frame=SHOT_START,
        shot_end_frame=SHOT_END,
    )


def _viseme_map(fallback: str = "NEUTRAL") -> VisemeMap:
    return build_viseme_map(
        map_id=VisemeMapId("vm-p18-vi"),
        language="vi-VN",
        rig_profile_id="rig-p18",
        map_version="1.0",
        fallback_rule=fallback,
        entries={
            "ch": VisemeTarget(shape=VisemeShape.T_D_S,
                               controls={"jaw_open": 0.6, "lips_close": 0.2}),
            "ao": VisemeTarget(shape=VisemeShape.AA,
                               controls={"jaw_open": 0.9, "lips_close": 0.1}),
            "b": VisemeTarget(shape=VisemeShape.M_B_P,
                              controls={"lips_close": 1.0}),
            "an": VisemeTarget(shape=VisemeShape.AA,
                               controls={"jaw_open": 0.8}),
            "h": VisemeTarget(shape=VisemeShape.NEUTRAL,
                              controls={"jaw_open": 0.2}),
            "om": VisemeTarget(shape=VisemeShape.O,
                               controls={"jaw_open": 0.7, "lips_close": 0.3}),
            "n": VisemeTarget(shape=VisemeShape.L_N,
                              controls={"jaw_open": 0.5}),
            "ay": VisemeTarget(shape=VisemeShape.I,
                               controls={"jaw_open": 0.6}),
            "th": VisemeTarget(shape=VisemeShape.T_D_S,
                               controls={"jaw_open": 0.5}),
            "e": VisemeTarget(shape=VisemeShape.E,
                              controls={"jaw_open": 0.75}),
            "t": VisemeTarget(shape=VisemeShape.T_D_S,
                              controls={"jaw_open": 0.55}),
            "oi": VisemeTarget(shape=VisemeShape.O,
                               controls={"jaw_open": 0.7}),
            "o": VisemeTarget(shape=VisemeShape.O,
                              controls={"jaw_open": 0.65}),
            "k": VisemeTarget(shape=VisemeShape.K_G,
                              controls={"jaw_open": 0.5}),
            "am": VisemeTarget(shape=VisemeShape.M_B_P,
                               controls={"lips_close": 0.95}),
        },
    )


def _happy_curve(seed: int = 1):
    from windagent_core.domain.video_production.facial import EmotionCurve
    return EmotionCurve(
        curve_id=EmotionCurveId(f"ec-p18-{seed}"),
        emotion=AnimationEmotion.HAPPY,
        frame_start=SHOT_START,
        frame_end=SHOT_END,
        controls={"brow_raise_l": 0.5, "brow_raise_r": 0.5},
        intensity=0.6,
    )


@pytest.fixture
def alignment():
    return fake_alignment(text=VIETNAMESE_LINE_A)


@pytest.fixture
def phoneme_track(alignment):
    return _track(alignment)


@pytest.fixture
def viseme_map():
    return _viseme_map()


@pytest.fixture
def compiler():
    return FacialAnimationCompiler()


# ---------------------------------------------------------------------------
# Backlog 1 — timing normalization
# ---------------------------------------------------------------------------
def test_normalize_preserves_alignment_hash_and_offsets(alignment):
    track = _track(alignment)
    assert track.source_alignment_hash == alignment.alignment_hash
    assert track.fps == FPS
    assert track.shot_start_frame == SHOT_START
    assert all(p.start_frame >= SHOT_START for p in track.phonemes)
    assert all(p.end_frame <= SHOT_END for p in track.phonemes)
    # 0.0s -> frame SHOT_START; 0.10s -> SHOT_START + round(0.10*24)
    assert track.phonemes[0].start_frame == SHOT_START
    assert track.phonemes[0].phoneme == "ch"


def test_normalize_deterministic_hash():
    a = _track(fake_alignment(text=VIETNAMESE_LINE_A))
    b = _track(fake_alignment(text=VIETNAMESE_LINE_A))
    assert a.content_hash() == b.content_hash()


def test_normalize_non_monotonic_fails_closed():
    from windagent_core.domain.video_production.facial import PhonemeSpan
    result = fake_alignment(text=VIETNAMESE_LINE_A)
    result = result.model_copy(update={"phoneme_timestamps": [
        {"phoneme": "a", "start_seconds": 0.5, "end_seconds": 0.6,
         "confidence": 0.9, "is_silence": False},
        {"phoneme": "b", "start_seconds": 0.55, "end_seconds": 0.7,
         "confidence": 0.9, "is_silence": False},
    ]})
    with pytest.raises(FacialCompileError) as exc:
        _track(result)
    assert "NON_MONOTONIC" in exc.value.details.get("kinds", [])


def test_normalize_out_of_shot_range_fails_closed():
    result = fake_alignment(text=VIETNAMESE_LINE_A)
    result = result.model_copy(update={"phoneme_timestamps": [
        {"phoneme": "a", "start_seconds": 9.0, "end_seconds": 9.5,
         "confidence": 0.9, "is_silence": False},
    ]})
    with pytest.raises(FacialCompileError) as exc:
        _track(result)
    assert "OUT_OF_SHOT_RANGE" in exc.value.details.get("kinds", [])


# ---------------------------------------------------------------------------
# Backlog 2 — viseme map versioning + fallback rule
# ---------------------------------------------------------------------------
def test_viseme_map_versioned_by_language_and_rig():
    m = _viseme_map()
    assert m.language == "vi-VN"
    assert m.rig_profile_id == "rig-p18"
    assert m.map_version == "1.0"
    assert m.content_hash() == _viseme_map().content_hash()


def test_viseme_map_unknown_phoneme_uses_explicit_fallback(viseme_map):
    target = viseme_map.resolve("zzz")
    assert target.shape is VisemeShape.NEUTRAL


def test_viseme_map_unknown_phoneme_no_rule_fails_closed():
    m = _viseme_map(fallback="")
    with pytest.raises(VisemeMapMissingPhonemeError):
        m.resolve("zzz")


def test_viseme_map_rejects_unknown_fallback_rule():
    with pytest.raises(FacialCompileError):
        build_viseme_map(
            map_id=VisemeMapId("vm-bad"), language="vi-VN",
            rig_profile_id="rig", map_version="1.0",
            fallback_rule="SILENT_SKIP", entries={},
        )


def test_viseme_map_rejects_unbounded_amplitude():
    # pydantic enforces amplitude <= AMPLITUDE_MAX at construction
    with pytest.raises(ValueError):
        VisemeTarget(shape=VisemeShape.AA, controls={"jaw_open": 0.5},
                     amplitude=2.0)


# ---------------------------------------------------------------------------
# Backlog 3-6 — compile
# ---------------------------------------------------------------------------
def test_compile_produces_curves_with_bounded_amplitude(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    assert track.curves
    assert "jaw_open" in track.curves
    for control, keyframes in track.curves.items():
        assert keyframes, f"{control} has no keyframes"
        for kf in keyframes:
            assert 0.0 <= kf.value <= 1.0, "amplitude must be bounded"
            assert SHOT_START <= kf.frame <= SHOT_END


def test_compile_deterministic_manifest(phoneme_track, viseme_map):
    a = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    b = compile_facial_track(
        track_id=FacialTrackId("ft-p18-b"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    assert a.content_hash() == b.content_hash()


def test_compile_silence_produces_no_mouth_movement(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    # The fake alignment has SIL spans between words; no keyframes inside them
    # (exclusive bounds: a keyframe on the shared boundary frame belongs to
    # the adjacent speech span)
    for span in phoneme_track.phonemes:
        if not span.is_silence:
            continue
        for control in ARTICULATION_CONTROLS:
            for kf in track.curves.get(control, []):
                assert not (span.start_frame < kf.frame < span.end_frame
                            and kf.value > 0.01)


def test_compile_emotion_overlap_fails_closed(phoneme_track, viseme_map):
    from windagent_core.domain.video_production.facial import EmotionCurve
    bad = EmotionCurve(
        curve_id=EmotionCurveId("ec-bad"),
        emotion=AnimationEmotion.HAPPY,
        frame_start=SHOT_START, frame_end=SHOT_END,
        controls={"jaw_open": 0.9},  # articulation overlap
        intensity=0.5,
    )
    with pytest.raises(FacialCompileError) as exc:
        compile_facial_track(
            track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
            shot_id="shot-1", phoneme_track=phoneme_track,
            viseme_map=viseme_map, seed=42,
            emotion_curves=[bad], facial_rig_controls=RIG_CONTROLS,
        )
    assert "EMOTION_ARTICULATION_OVERLAP" in exc.value.details.get("kinds", [])


def test_compile_emotion_uses_brow_controls_only(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, emotion_curves=[_happy_curve()],
        facial_rig_controls=RIG_CONTROLS,
    )
    assert track.emotion_curves
    curve = track.emotion_curves[0]
    assert set(curve.controls) & set(ARTICULATION_CONTROLS) == set()


def test_compile_blink_gaze_head_deterministic(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    assert track.blink is not None and track.blink.events
    assert track.gaze is not None and track.gaze.samples
    assert track.head_motion
    assert all(kf.value <= 0.15 for kf in track.head_motion)
    # different seed -> different gaze/blink (deterministic per seed)
    other = compile_facial_track(
        track_id=FacialTrackId("ft-p18-b"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=43, facial_rig_controls=RIG_CONTROLS,
    )
    assert track.blink.events != other.blink.events or \
        track.gaze.samples != other.gaze.samples


def test_compile_ownership_and_head_blend_policy(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, head_blend_policy=HeadBlendPolicy.BODY_OWNS_HEAD,
        facial_rig_controls=RIG_CONTROLS,
    )
    assert track.ownership["jaw_open"] is FacialLayerKind.LIP_SYNC
    assert track.ownership["blink_l"] is FacialLayerKind.BLINK
    assert track.head_blend_policy is HeadBlendPolicy.BODY_OWNS_HEAD
    assert track.head_motion == [], "BODY_OWNS_HEAD must emit no head motion"


def test_compile_records_input_hashes(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    assert track.input_hashes["alignment"] == phoneme_track.source_alignment_hash
    assert track.input_hashes["viseme_map"] == viseme_map.content_hash()
    assert len(track.input_hashes["rig_controls"]) == 64


# ---------------------------------------------------------------------------
# §4 — validation matrix
# ---------------------------------------------------------------------------
def _validated(phoneme_track, viseme_map, **kw):
    kw.setdefault("facial_rig_controls", RIG_CONTROLS)
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=kw["facial_rig_controls"],
    )
    return validate_facial_track(
        receipt_id=FacialValidationReceiptId("fvr-p18-a"),
        track=track, phoneme_track=phoneme_track, **kw,
    )


def test_validate_clean_track_approved(phoneme_track, viseme_map):
    receipt = _validated(phoneme_track, viseme_map)
    assert receipt.status is FacialTrackStatus.APPROVED
    assert receipt.gate_passed
    assert receipt.findings == []


def test_validate_drift_measured_at_line_start_mid_end(phoneme_track,
                                                       viseme_map):
    receipt = _validated(phoneme_track, viseme_map)
    lines = receipt.sync_metrics["lines"]
    assert lines, "sync_metrics must contain per-line drift"
    for line in lines:
        assert line["max_drift_frames"] <= DRIFT_TOLERANCE_FRAMES
        assert set(line) >= {"start_drift_frames", "mid_drift_frames",
                             "end_drift_frames", "max_drift_frames"}


def test_validate_non_monotonic_rejected():
    from windagent_core.domain.video_production.facial import (
        VisemeKeyframe, FacialAnimationTrack,
    )
    track = FacialAnimationTrack(
        track_id=FacialTrackId("ft-bad"), character_id="c", shot_id="s",
        fps=FPS, frame_start=SHOT_START, frame_end=SHOT_END,
        phoneme_track_id="pt", source_alignment_hash="0" * 64,
        curves={"jaw_open": [
            VisemeKeyframe(control="jaw_open", frame=SHOT_START + 5, value=0.5),
            VisemeKeyframe(control="jaw_open", frame=SHOT_START + 3, value=0.9),
        ]},
    )
    receipt = validate_facial_track(
        receipt_id=FacialValidationReceiptId("fvr-bad"), track=track,
    )
    assert receipt.status is FacialTrackStatus.REJECTED
    assert any(f.kind is FacialFindingKind.NON_MONOTONIC
               for f in receipt.findings)


def test_validate_keyframe_out_of_shot_range_rejected():
    from windagent_core.domain.video_production.facial import (
        VisemeKeyframe, FacialAnimationTrack,
    )
    track = FacialAnimationTrack(
        track_id=FacialTrackId("ft-bad"), character_id="c", shot_id="s",
        fps=FPS, frame_start=SHOT_START, frame_end=SHOT_END,
        phoneme_track_id="pt", source_alignment_hash="0" * 64,
        curves={"jaw_open": [
            VisemeKeyframe(control="jaw_open", frame=SHOT_END + 10, value=0.5),
        ]},
    )
    receipt = validate_facial_track(
        receipt_id=FacialValidationReceiptId("fvr-bad"), track=track,
    )
    assert receipt.status is FacialTrackStatus.REJECTED
    assert any(f.kind is FacialFindingKind.OUT_OF_SHOT_RANGE
               for f in receipt.findings)


def test_validate_low_confidence_routes_to_human_review(viseme_map):
    alignment = fake_alignment(text=VIETNAMESE_LINE_A,
                               segment_confidence=0.3)
    pt = _track(alignment)
    receipt = _validated(pt, viseme_map)
    assert receipt.status is FacialTrackStatus.REQUIRES_HUMAN_REVIEW
    assert any(f.kind is FacialFindingKind.LOW_CONFIDENCE_ALIGNMENT
               for f in receipt.findings)
    assert not receipt.gate_passed


def test_validate_rig_missing_controls_routes_to_human_review(phoneme_track,
                                                              viseme_map):
    receipt = _validated(phoneme_track, viseme_map,
                         facial_rig_controls=["jaw_open"])
    assert receipt.status is FacialTrackStatus.REQUIRES_HUMAN_REVIEW
    assert any(f.kind is FacialFindingKind.RIG_CONTROL_MISSING
               for f in receipt.findings)


def test_validate_idle_speech_flagged(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS, idle=True,
    )
    receipt = validate_facial_track(
        receipt_id=FacialValidationReceiptId("fvr-idle"),
        track=track, phoneme_track=phoneme_track,
        facial_rig_controls=RIG_CONTROLS,
    )
    assert receipt.status is FacialTrackStatus.REQUIRES_HUMAN_REVIEW
    assert any(f.kind is FacialFindingKind.IDLE_SPEECH
               for f in receipt.findings)


def test_validate_head_joint_limit(phoneme_track, viseme_map):
    receipt = _validated(phoneme_track, viseme_map,
                         body_head_turn_degrees=HEAD_JOINT_LIMIT_DEGREES)
    # facial head adds amplitude*limit on top of body turn -> exceeded
    assert any(f.kind is FacialFindingKind.HEAD_JOINT_LIMIT_EXCEEDED
               for f in receipt.findings)
    assert receipt.status is FacialTrackStatus.REQUIRES_HUMAN_REVIEW


def test_validate_silence_mouth_movement_flagged():
    from windagent_core.domain.video_production.facial import (
        PhonemeSpan, VisemeKeyframe, FacialAnimationTrack, PhonemeTrack,
    )
    pt = PhonemeTrack(
        track_id=PhonemeTrackId("pt-sil"), alignment_receipt_id="",
        source_alignment_hash="0" * 64, fps=FPS,
        shot_start_frame=SHOT_START, shot_end_frame=SHOT_END,
        segment_confidence=0.9,
        phonemes=[
            PhonemeSpan(phoneme="SIL", start_frame=SHOT_START + 10,
                        end_frame=SHOT_START + 30, start_seconds=0.5,
                        end_seconds=1.0, confidence=1.0, is_silence=True),
        ],
    )
    track = FacialAnimationTrack(
        track_id=FacialTrackId("ft-sil"), character_id="c", shot_id="s",
        fps=FPS, frame_start=SHOT_START, frame_end=SHOT_END,
        phoneme_track_id="pt-sil", source_alignment_hash="0" * 64,
        curves={"jaw_open": [
            VisemeKeyframe(control="jaw_open", frame=SHOT_START + 15, value=0.8),
        ]},
    )
    receipt = validate_facial_track(
        receipt_id=FacialValidationReceiptId("fvr-sil"),
        track=track, phoneme_track=pt,
    )
    assert any(f.kind is FacialFindingKind.SILENCE_MOUTH_MOVEMENT
               for f in receipt.findings)


def test_validate_facial_pop_flagged():
    from windagent_core.domain.video_production.facial import (
        VisemeKeyframe, FacialAnimationTrack,
    )
    track = FacialAnimationTrack(
        track_id=FacialTrackId("ft-pop"), character_id="c", shot_id="s",
        fps=FPS, frame_start=SHOT_START, frame_end=SHOT_END,
        phoneme_track_id="pt", source_alignment_hash="0" * 64,
        curves={"jaw_open": [
            VisemeKeyframe(control="jaw_open", frame=SHOT_START, value=0.0),
            VisemeKeyframe(control="jaw_open", frame=SHOT_START + 1, value=0.95),
        ]},
    )
    receipt = validate_facial_track(
        receipt_id=FacialValidationReceiptId("fvr-pop"), track=track,
    )
    assert any(f.kind is FacialFindingKind.FACIAL_POP
               for f in receipt.findings)


# ---------------------------------------------------------------------------
# Backlog 7 — bake
# ---------------------------------------------------------------------------
def test_bake_records_compiler_version_hashes_frame_range(phoneme_track,
                                                          viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    receipt = validate_facial_track(
        receipt_id=FacialValidationReceiptId("fvr-bake"),
        track=track, phoneme_track=phoneme_track,
        facial_rig_controls=RIG_CONTROLS,
    )
    approved = track.model_copy(update={"status": receipt.status})
    action = bake_facial_track(
        action_id=BakedFacialActionId("bfa-p18"), track=approved,
    )
    assert action.compiler_version == FACIAL_COMPILER_VERSION
    assert action.input_hashes == approved.input_hashes
    assert [action.frame_start, action.frame_end] == [SHOT_START, SHOT_END]
    assert action.fps == FPS
    assert len(action.action_hash) == 64


def test_bake_rejects_non_approved(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    with pytest.raises(FacialBakeError):
        bake_facial_track(action_id=BakedFacialActionId("bfa-bad"),
                          track=track)


# ---------------------------------------------------------------------------
# Backlog 8 — repair
# ---------------------------------------------------------------------------
def test_repair_gaze_only_touches_gaze(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    receipt = repair_facial_track(
        receipt_id=FacialRepairReceiptId("frr-p18"),
        track=track, scope=FacialRepairScope.GAZE, seed=999,
    )
    assert receipt.scope is FacialRepairScope.GAZE
    assert receipt.rebuilt_layers == ["gaze"]
    assert receipt.invalidation is FacialInvalidationScope.TRACK_AND_RENDER_FINAL
    assert receipt.new_track_id != track.track_id


def test_repair_emotion_requires_curves(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    with pytest.raises(FacialRepairError):
        repair_facial_track(
            receipt_id=FacialRepairReceiptId("frr-bad"),
            track=track, scope=FacialRepairScope.EMOTION,
        )


def test_repair_unknown_scope_fails_closed(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    with pytest.raises(FacialRepairError):
        repair_facial_track(
            receipt_id=FacialRepairReceiptId("frr-bad"),
            track=track, scope="BODY",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Backlog 9 — preview manifest + port facade
# ---------------------------------------------------------------------------
def test_preview_manifest_closeup_before_cycles(phoneme_track, viseme_map):
    track = compile_facial_track(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    manifest = build_preview_manifest(track=track)
    assert manifest["preview"] == "close-up playblast before Cycles final"
    assert manifest["frame_range"] == [SHOT_START, SHOT_END]
    assert manifest["fps"] == FPS
    assert "jaw_open" in manifest["semantic_controls"]
    assert "jaw" not in "".join(manifest["bindings"].split()), \
        "domain manifest must not name data-blocks"


def test_compiler_facade_implements_port(compiler, phoneme_track, viseme_map):
    from windagent_core.contracts.video_production import (
        FacialAnimationCompilerPort,
    )
    assert isinstance(compiler, FacialAnimationCompilerPort)
    request = FacialCompileRequest(
        track_id=FacialTrackId("ft-p18-a"), character_id="char_a",
        shot_id="shot-1", phoneme_track=phoneme_track, viseme_map=viseme_map,
        seed=42, facial_rig_controls=RIG_CONTROLS,
    )
    track = compiler.compile(request)
    receipt = compiler.validate(track, phoneme_track=phoneme_track,
                                facial_rig_controls=RIG_CONTROLS)
    assert receipt.gate_passed
    manifest = compiler.preview_manifest(track)
    assert manifest["shot_id"] == "shot-1"
    # binding table maps semantic -> shape key/bone at the adapter only
    table = compiler.binding_table()
    assert table["jaw_open"]["shape_key"] == "jawOpen"


def test_compiler_facade_rejects_non_request(compiler):
    with pytest.raises(FacialCompileError):
        compiler.compile("not-a-request")  # type: ignore[arg-type]
