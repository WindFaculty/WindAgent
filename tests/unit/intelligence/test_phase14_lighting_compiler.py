"""VP3D Phase 14 — Lighting System unit tests (stage_g §4/§5).

Covers the §5 lighting matrix:

- all 7 presets compile to clean, versioned rig plans; preset selection is
  deterministic (exact style+time-of-day, style fallback, CHILDREN_3D alias)
  and unknown styles fail closed;
- same preset/seed/compiler version -> identical rig manifest hash
  (determinism);
- bounded overrides: in-bounds exposure/key/CCT adjustments apply; anything
  outside the bounds or aimed at a different preset fails closed;
- changing the light invalidates ONLY the shot's dependent preview/render,
  never assets/rigs/audio (invalidation scope);
- missing key light, clipped exposure, inconsistent color temperature,
  policy-exceeded and continuity drift are DETECTED and blocking; noise
  risk is advisory and does not block;
- contact sheet / histogram manifest is deterministic (16 bins, sums to 1).
"""

from __future__ import annotations

import hashlib

import pytest
from windagent_core.domain.video_production.enums import (
    LightRole,
    LightingColorPolicy,
    LightingEmphasis,
    LightingMood,
    LightingStyle,
    TimeOfDay,
)
from windagent_core.domain.video_production.errors import (
    LightingCompileError,
    LightingOverrideOutOfBoundsError,
)
from windagent_core.domain.video_production.ids import (
    LightOverrideId,
    LightingIntentId,
    SceneId,
    ShotId,
)
from windagent_core.domain.video_production.lighting import (
    LightOverride,
    LightRigPlan,
    LightSpec,
    LightingFindingKind,
    LightingIntent,
    LightingValidator,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.lighting import (
    LIGHTING_COMPILER_LAYER_VERSION,
    LightingCompiler,
    all_presets,
    select_preset,
    supported_preset_ids,
)


def _h(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _intent(
    shot: str = "sh-1",
    style: LightingStyle = LightingStyle.CARTOON,
    time_of_day: TimeOfDay = TimeOfDay.DAY,
    mood: LightingMood = LightingMood.HAPPY,
    continuity_key: str = "",
) -> LightingIntent:
    return LightingIntent(
        intent_id=LightingIntentId(f"li-{shot}"),
        shot_id=ShotId(shot),
        scene_id=SceneId("sc-1"),
        mood=mood,
        time_of_day=time_of_day,
        style=style,
        emphasis=LightingEmphasis.SUBJECT,
        continuity_key=continuity_key,
    )


def _override(shot: str = "sh-1", preset_id: str = "CARTOON_DAY",
              **kw) -> LightOverride:
    return LightOverride(
        override_id=LightOverrideId(f"lo-{shot}"),
        shot_id=ShotId(shot), preset_id=preset_id, **kw)


COMPILER = LightingCompiler()


# ---------------------------------------------------------------------------
# Preset registry + selection
# ---------------------------------------------------------------------------
def test_all_seven_presets_are_registered_and_versioned():
    ids = supported_preset_ids()
    assert ids == [
        "CARTOON_DAY", "CARTOON_NIGHT", "INTERIOR_SOFT", "MAGIC_FOREST",
        "SUNSET", "DRAMATIC", "COMEDY_BRIGHT",
    ]
    for preset in all_presets():
        assert preset.version
        assert preset.preset_hash()
        assert preset.key_light() is not None


def test_selection_exact_style_time_of_day():
    assert select_preset(LightingStyle.CARTOON,
                         TimeOfDay.DAY).preset_id == "CARTOON_DAY"
    assert select_preset(LightingStyle.CARTOON,
                         TimeOfDay.NIGHT).preset_id == "CARTOON_NIGHT"
    assert select_preset(LightingStyle.INTERIOR,
                         TimeOfDay.INTERIOR).preset_id == "INTERIOR_SOFT"
    assert select_preset(LightingStyle.SUNSET,
                         TimeOfDay.DUSK).preset_id == "SUNSET"


def test_selection_style_fallback_is_deterministic():
    # styles with a single preset fall back to it for any time-of-day
    assert select_preset(LightingStyle.DRAMATIC,
                         TimeOfDay.DAY).preset_id == "DRAMATIC"
    assert select_preset(LightingStyle.MAGIC_FOREST,
                         TimeOfDay.DAY).preset_id == "MAGIC_FOREST"
    assert select_preset(LightingStyle.COMEDY,
                         TimeOfDay.NIGHT).preset_id == "COMEDY_BRIGHT"


def test_children_3d_aliases_to_cartoon_family():
    # road_map.md Phase 14 example: mood=HAPPY, time=DAY, style=CHILDREN_3D
    preset = select_preset(LightingStyle.CHILDREN_3D, TimeOfDay.DAY)
    assert preset.preset_id == "CARTOON_DAY"


def test_unknown_style_fails_closed():
    with pytest.raises(LightingCompileError):
        select_preset("NEON", TimeOfDay.NIGHT)


# ---------------------------------------------------------------------------
# Compile + determinism
# ---------------------------------------------------------------------------
def test_every_preset_compiles_clean():
    for preset in all_presets():
        intent = _intent(shot=f"sh-{preset.preset_id.lower()}",
                         style=preset.style, time_of_day=preset.time_of_day)
        receipt = COMPILER.compile(intent=intent)
        assert receipt.cleaned_ok, receipt.blocking_kinds
        assert receipt.plan.preset_id == preset.preset_id
        assert receipt.plan.resource.within_policy


def test_same_input_same_rig_hash():
    a = COMPILER.compile(intent=_intent())
    b = COMPILER.compile(intent=_intent())
    assert a.plan.rig_hash == b.plan.rig_hash
    assert a.plan.preset_hash == b.plan.preset_hash


def test_mood_change_keeps_rig_but_changes_intent_hash():
    base = COMPILER.compile(intent=_intent(mood=LightingMood.HAPPY))
    tense = COMPILER.compile(intent=_intent(mood=LightingMood.TENSE))
    assert base.plan.rig_hash == tense.plan.rig_hash
    assert base.plan.intent_hash != tense.plan.intent_hash


def test_style_change_changes_preset_and_hash():
    base = COMPILER.compile(intent=_intent())
    dramatic = COMPILER.compile(
        intent=_intent(style=LightingStyle.DRAMATIC,
                       time_of_day=TimeOfDay.NIGHT))
    assert dramatic.plan.preset_id == "DRAMATIC"
    assert dramatic.plan.rig_hash != base.plan.rig_hash


def test_override_changes_rig_hash():
    base = COMPILER.compile(intent=_intent())
    overridden = COMPILER.compile(
        intent=_intent(),
        override=_override(exposure_ev_shift=1.0, key_multiplier=1.2))
    assert overridden.plan.override_id == "lo-sh-1"
    assert overridden.plan.rig_hash != base.plan.rig_hash


def test_invalidation_scoped_to_preview_render_only():
    intent = _intent()
    first = COMPILER.compile(intent=intent)
    # fresh compile -> nothing stale
    assert first.invalidated_artifacts == []
    # unchanged rig -> reuse, nothing invalidated
    same = COMPILER.compile(intent=intent,
                            prior_rig_hash=first.plan.rig_hash)
    assert same.invalidated_artifacts == []
    # changed light -> only the shot's dependent preview/render
    changed = COMPILER.compile(intent=intent,
                               override=_override(key_multiplier=1.5),
                               prior_rig_hash=first.plan.rig_hash)
    assert changed.invalidated_artifacts == ["preview/render:sh-1"]


# ---------------------------------------------------------------------------
# Bounded overrides (backlog 3)
# ---------------------------------------------------------------------------
def test_override_bounds_are_enforced():
    with pytest.raises(LightingOverrideOutOfBoundsError):
        COMPILER.compile(intent=_intent(),
                         override=_override(exposure_ev_shift=3.0))
    with pytest.raises(LightingOverrideOutOfBoundsError):
        COMPILER.compile(intent=_intent(),
                         override=_override(key_multiplier=0.1))
    with pytest.raises(LightingOverrideOutOfBoundsError):
        COMPILER.compile(intent=_intent(),
                         override=_override(cct_shift_kelvin=2000))
    with pytest.raises(LightingOverrideOutOfBoundsError):
        COMPILER.compile(intent=_intent(style=LightingStyle.DRAMATIC,
                                        time_of_day=TimeOfDay.NIGHT),
                         override=_override(preset_id="CARTOON_DAY",
                                            key_multiplier=1.1))


def test_override_applies_bounded_adjustments():
    receipt = COMPILER.compile(
        intent=_intent(),
        override=_override(exposure_ev_shift=1.0, key_multiplier=2.0,
                           cct_shift_kelvin=500,
                           emphasis=LightingEmphasis.ENVIRONMENT))
    assert receipt.plan.world.exposure_ev == pytest.approx(2.0)  # 1.0 + 1.0
    assert receipt.plan.emphasis == LightingEmphasis.ENVIRONMENT
    key = receipt.plan.key_light()
    assert key is not None and key.intensity_ratio == pytest.approx(2.0)
    assert all(l.color_kelvin >= 1000 for l in receipt.plan.lights)
    assert receipt.plan.lights[0].color_kelvin == 5600 + 500


# ---------------------------------------------------------------------------
# Validation: negative checks must be DETECTED (§5)
# ---------------------------------------------------------------------------
def _valid_plan() -> LightRigPlan:
    return COMPILER.compile(intent=_intent()).plan


def _validator_report(plan: LightRigPlan, **kw):
    intent = kw.pop("intent", _intent())
    preset = kw.pop("preset", select_preset(intent.style, intent.time_of_day))
    return LightingValidator().validate(intent=intent, preset=preset,
                                        rig_plan=plan, **kw)


def test_missing_key_light_detected():
    plan = _valid_plan().model_copy(update={
        "lights": [l for l in _valid_plan().lights
                   if l.role != LightRole.KEY]})
    report = _validator_report(plan)
    assert LightingFindingKind.MISSING_KEY_LIGHT in report.blocking_kinds


def test_clipped_exposure_detected():
    # DRAMATIC preset range is [-4, 0]EV; +2 shift pushes -1.5 -> +0.5
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(
            intent=_intent(style=LightingStyle.DRAMATIC,
                           time_of_day=TimeOfDay.NIGHT),
            override=_override(preset_id="DRAMATIC", exposure_ev_shift=2.0))
    assert "EXPOSURE_CLIPPED" in exc.value.details["kinds"]


def test_inconsistent_color_temperature_detected():
    lights = list(_valid_plan().lights)
    lights[0] = lights[0].model_copy(update={"color_kelvin": 9000})
    plan = _valid_plan().model_copy(update={"lights": lights})
    report = _validator_report(plan)
    assert LightingFindingKind.INCONSISTENT_COLOR_TEMP in report.blocking_kinds
    assert report.findings[0].measured["cct_spread_k"] > 800


def test_color_policy_tolerance_allows_intentional_splits():
    # SUNSET uses WARM_COOL_SPLIT: 2500K..6000K spread is intentional
    sunset = COMPILER.compile(
        intent=_intent(style=LightingStyle.SUNSET,
                       time_of_day=TimeOfDay.DUSK)).plan
    assert _validator_report(sunset,
                             intent=_intent(style=LightingStyle.SUNSET,
                                            time_of_day=TimeOfDay.DUSK),
                             preset=select_preset(LightingStyle.SUNSET,
                                                  TimeOfDay.DUSK)).blocking_kinds == []


def test_noise_risk_is_advisory_not_blocking():
    # COMEDY_BRIGHT pins 48 samples < 64 floor -> advisory finding only
    receipt = COMPILER.compile(
        intent=_intent(style=LightingStyle.COMEDY,
                       time_of_day=TimeOfDay.DAY))
    kinds = {f.kind for f in receipt.validation.findings}
    assert LightingFindingKind.NOISE_RISK in kinds
    assert receipt.cleaned_ok


def test_policy_exceeded_detected():
    plan = _valid_plan()
    lights = list(plan.lights)
    for i in range(6):
        lights.append(LightSpec(role=LightRole.FILL, color_kelvin=5600,
                                intensity_ratio=0.1, casts_shadow=False,
                                position_hint="extra"))
    plan = plan.model_copy(update={
        "lights": lights,
        "resource": plan.resource.model_copy(update={
            "light_count": len(lights), "within_policy": False})})
    report = _validator_report(plan)
    assert LightingFindingKind.POLICY_EXCEEDED in report.blocking_kinds


def test_continuity_drift_detected_between_adjacent_shots():
    key = "sc1-ct"
    a = COMPILER.compile(intent=_intent(shot="sh-a", continuity_key=key))
    # +1.5 EV drift with the same continuity key -> blocking
    with pytest.raises(ValidationFailureError) as exc:
        COMPILER.compile(
            intent=_intent(shot="sh-b", continuity_key=key),
            override=_override(shot="sh-b", exposure_ev_shift=1.5),
            previous_plan=a.plan)
    assert "CONTINUITY_DRIFT" in exc.value.details["kinds"]
    # identical rig, same key -> clean
    b = COMPILER.compile(intent=_intent(shot="sh-b", continuity_key=key),
                         previous_plan=a.plan)
    assert b.cleaned_ok
    # different key -> no continuity check
    c = COMPILER.compile(
        intent=_intent(shot="sh-c", continuity_key="other"),
        override=_override(shot="sh-c", exposure_ev_shift=1.5),
        previous_plan=a.plan)
    assert c.cleaned_ok


# ---------------------------------------------------------------------------
# Contact sheet / histogram (backlog 6)
# ---------------------------------------------------------------------------
def test_contact_sheet_deterministic_and_normalized():
    plan = COMPILER.compile(intent=_intent()).plan
    a = COMPILER.build_contact_sheet(plan)
    b = COMPILER.build_contact_sheet(plan)
    assert a.manifest_hash == b.manifest_hash
    assert len(a.histogram) == 16
    assert sum(a.histogram) == pytest.approx(1.0, abs=1e-3)
    assert a.preset_id == "CARTOON_DAY"
    assert a.confidence == "LOW"
    assert len(a.entries) == len(plan.lights)


def test_compiler_layer_version_is_pinned():
    assert LIGHTING_COMPILER_LAYER_VERSION == "1.0.0"
