"""
Versioned lighting presets (VP3D Phase 14, stage_g §4 backlog 1/2).

The first seven presets: CARTOON_DAY, CARTOON_NIGHT, INTERIOR_SOFT,
MAGIC_FOREST, SUNSET, DRAMATIC, COMEDY_BRIGHT. Each pins light types,
ratios, color policy, world settings, shadow/bounce budget, exposure range
and render policy. Selection is deterministic: exact (style, time-of-day)
match first, style-only fallback second, unknown style fails closed with
`LightingCompileError` — the model never places unlimited lights.

`CHILDREN_3D` (the road_map.md Phase 14 example style) aliases onto the
CARTOON family, so `mood=HAPPY, time=DAY, style=CHILDREN_3D` resolves to
CARTOON_DAY. The registry version participates in the rig manifest hash.
"""

from __future__ import annotations

from typing import List

from windagent_core.domain.video_production.enums import (
    LightRole,
    LightingColorPolicy,
    LightingEmphasis,
    LightingMood,
    LightingStyle,
    TimeOfDay,
)
from windagent_core.domain.video_production.errors import LightingCompileError
from windagent_core.domain.video_production.lighting import (
    ExposureRange,
    LightSpec,
    LightingPreset,
    RenderPolicy,
    ShadowBounceBudget,
    WorldSettings,
)

PRESET_REGISTRY_VERSION = "1.0.0"

# road_map.md Phase 14: Director may say style=CHILDREN_3D; it is the
# canonical alias of the CARTOON family.
_STYLE_ALIASES = {
    LightingStyle.CHILDREN_3D: LightingStyle.CARTOON,
}

_PRESET_ORDER: List[str] = [
    "CARTOON_DAY",
    "CARTOON_NIGHT",
    "INTERIOR_SOFT",
    "MAGIC_FOREST",
    "SUNSET",
    "DRAMATIC",
    "COMEDY_BRIGHT",
]

_PRESETS: List[LightingPreset] = [
    LightingPreset(
        preset_id="CARTOON_DAY",
        style=LightingStyle.CARTOON,
        time_of_day=TimeOfDay.DAY,
        default_mood=LightingMood.HAPPY,
        color_policy=LightingColorPolicy.UNIFORM_CCT,
        lights=[
            LightSpec(role=LightRole.KEY, color_kelvin=5600, intensity_ratio=1.0,
                      position_hint="camera_left_45_above"),
            LightSpec(role=LightRole.FILL, color_kelvin=6000, intensity_ratio=0.35,
                      casts_shadow=False, position_hint="camera_right_30"),
            LightSpec(role=LightRole.RIM, color_kelvin=5600, intensity_ratio=0.30,
                      casts_shadow=False, position_hint="behind_subject_high"),
            LightSpec(role=LightRole.AMBIENT, color_kelvin=6200, intensity_ratio=0.20,
                      casts_shadow=False, position_hint="world_sky"),
        ],
        key_fill_ratio=1.0 / 0.35,
        world=WorldSettings(exposure_ev=1.0, environment_strength=1.0,
                            ambient_color_kelvin=6200),
        exposure_range=ExposureRange(min_ev=-1.0, max_ev=3.0),
        shadow_bounce_budget=ShadowBounceBudget(shadow_light_count=1,
                                                bounce_light_count=1),
        render_policy=RenderPolicy(max_lights=6, max_samples=128, max_bounces=4),
        description="Bright, even cartoon daylight; warm-friendly uniform CCT.",
    ),
    LightingPreset(
        preset_id="CARTOON_NIGHT",
        style=LightingStyle.CARTOON,
        time_of_day=TimeOfDay.NIGHT,
        default_mood=LightingMood.MYSTERIOUS,
        color_policy=LightingColorPolicy.WARM_COOL_SPLIT,
        lights=[
            LightSpec(role=LightRole.KEY, color_kelvin=6500, intensity_ratio=1.0,
                      position_hint="camera_left_45_above"),
            LightSpec(role=LightRole.FILL, color_kelvin=7000, intensity_ratio=0.40,
                      casts_shadow=False, position_hint="camera_right_30"),
            LightSpec(role=LightRole.RIM, color_kelvin=4500, intensity_ratio=0.20,
                      casts_shadow=False, position_hint="behind_subject_low"),
            LightSpec(role=LightRole.PRACTICAL, color_kelvin=3400, intensity_ratio=0.30,
                      casts_shadow=False, position_hint="window_off_frame"),
            LightSpec(role=LightRole.AMBIENT, color_kelvin=7200, intensity_ratio=0.15,
                      casts_shadow=False, position_hint="world_moon"),
        ],
        key_fill_ratio=1.0 / 0.40,
        world=WorldSettings(exposure_ev=-2.0, environment_strength=0.35,
                            ambient_color_kelvin=7200),
        exposure_range=ExposureRange(min_ev=-4.0, max_ev=0.0),
        shadow_bounce_budget=ShadowBounceBudget(shadow_light_count=1,
                                                bounce_light_count=1),
        render_policy=RenderPolicy(max_lights=6, max_samples=256, max_bounces=4),
        description="Cool moonlight cartoon night with one warm practical accent.",
    ),
    LightingPreset(
        preset_id="INTERIOR_SOFT",
        style=LightingStyle.INTERIOR,
        time_of_day=TimeOfDay.INTERIOR,
        default_mood=LightingMood.ROMANTIC,
        color_policy=LightingColorPolicy.UNIFORM_CCT,
        lights=[
            LightSpec(role=LightRole.KEY, color_kelvin=3200, intensity_ratio=1.0,
                      position_hint="camera_left_45_above"),
            LightSpec(role=LightRole.FILL, color_kelvin=3400, intensity_ratio=0.70,
                      casts_shadow=False, position_hint="camera_right_30"),
            LightSpec(role=LightRole.RIM, color_kelvin=3000, intensity_ratio=0.30,
                      casts_shadow=False, position_hint="behind_subject_high"),
            LightSpec(role=LightRole.BOUNCE, color_kelvin=3200, intensity_ratio=0.40,
                      casts_shadow=False, position_hint="ceiling_bounce"),
            LightSpec(role=LightRole.PRACTICAL, color_kelvin=2800, intensity_ratio=0.50,
                      casts_shadow=False, position_hint="table_lamp"),
            LightSpec(role=LightRole.AMBIENT, color_kelvin=3500, intensity_ratio=0.30,
                      casts_shadow=False, position_hint="world_interior"),
        ],
        key_fill_ratio=1.0 / 0.70,
        world=WorldSettings(exposure_ev=-1.0, environment_strength=0.6,
                            ambient_color_kelvin=3500),
        exposure_range=ExposureRange(min_ev=-3.0, max_ev=1.0),
        shadow_bounce_budget=ShadowBounceBudget(shadow_light_count=2,
                                                bounce_light_count=2),
        render_policy=RenderPolicy(max_lights=8, max_samples=256, max_bounces=6),
        description="Warm, soft interior with generous bounce; gentle ratios.",
    ),
    LightingPreset(
        preset_id="MAGIC_FOREST",
        style=LightingStyle.MAGIC_FOREST,
        time_of_day=TimeOfDay.NIGHT,
        default_mood=LightingMood.MYSTERIOUS,
        color_policy=LightingColorPolicy.MULTICOLOR,
        lights=[
            LightSpec(role=LightRole.KEY, color_kelvin=5000, intensity_ratio=1.0,
                      position_hint="canopy_shaft_above"),
            LightSpec(role=LightRole.FILL, color_kelvin=5600, intensity_ratio=0.40,
                      casts_shadow=False, position_hint="camera_right_30"),
            LightSpec(role=LightRole.RIM, color_kelvin=4000, intensity_ratio=0.50,
                      casts_shadow=False, position_hint="firefly_field_behind"),
            LightSpec(role=LightRole.PRACTICAL, color_kelvin=2500, intensity_ratio=0.60,
                      casts_shadow=False, position_hint="lanterns_on_path"),
            LightSpec(role=LightRole.BOUNCE, color_kelvin=7000, intensity_ratio=0.30,
                      casts_shadow=False, position_hint="glowing_moss_floor"),
            LightSpec(role=LightRole.AMBIENT, color_kelvin=6800, intensity_ratio=0.25,
                      casts_shadow=False, position_hint="world_moon_through_leaves"),
        ],
        key_fill_ratio=1.0 / 0.40,
        world=WorldSettings(exposure_ev=-1.5, environment_strength=0.4,
                            ambient_color_kelvin=6800),
        exposure_range=ExposureRange(min_ev=-4.0, max_ev=1.0),
        shadow_bounce_budget=ShadowBounceBudget(shadow_light_count=2,
                                                bounce_light_count=2),
        render_policy=RenderPolicy(max_lights=8, max_samples=256, max_bounces=6),
        description="Intentional multicolor fantasy: cool shafts, warm fireflies.",
    ),
    LightingPreset(
        preset_id="SUNSET",
        style=LightingStyle.SUNSET,
        time_of_day=TimeOfDay.DUSK,
        default_mood=LightingMood.ROMANTIC,
        color_policy=LightingColorPolicy.WARM_COOL_SPLIT,
        lights=[
            LightSpec(role=LightRole.KEY, color_kelvin=3200, intensity_ratio=1.0,
                      position_hint="low_sun_behind_subject"),
            LightSpec(role=LightRole.FILL, color_kelvin=6000, intensity_ratio=0.50,
                      casts_shadow=False, position_hint="sky_reflection_front"),
            LightSpec(role=LightRole.RIM, color_kelvin=2500, intensity_ratio=0.80,
                      casts_shadow=False, position_hint="behind_subject_high"),
            LightSpec(role=LightRole.AMBIENT, color_kelvin=5500, intensity_ratio=0.30,
                      casts_shadow=False, position_hint="world_sky"),
        ],
        key_fill_ratio=1.0 / 0.50,
        world=WorldSettings(exposure_ev=0.0, environment_strength=0.8,
                            ambient_color_kelvin=5500),
        exposure_range=ExposureRange(min_ev=-2.0, max_ev=2.0),
        shadow_bounce_budget=ShadowBounceBudget(shadow_light_count=1,
                                                bounce_light_count=1),
        render_policy=RenderPolicy(max_lights=6, max_samples=128, max_bounces=4),
        description="Warm sun / cool sky split; classic golden-hour contrast.",
    ),
    LightingPreset(
        preset_id="DRAMATIC",
        style=LightingStyle.DRAMATIC,
        time_of_day=TimeOfDay.NIGHT,
        default_mood=LightingMood.TENSE,
        color_policy=LightingColorPolicy.WARM_COOL_SPLIT,
        lights=[
            LightSpec(role=LightRole.KEY, color_kelvin=4000, intensity_ratio=1.0,
                      position_hint="hard_side_light"),
            LightSpec(role=LightRole.FILL, color_kelvin=6500, intensity_ratio=0.15,
                      casts_shadow=False, position_hint="fill_very_low"),
            LightSpec(role=LightRole.RIM, color_kelvin=3000, intensity_ratio=0.60,
                      casts_shadow=False, position_hint="behind_subject_high"),
            LightSpec(role=LightRole.AMBIENT, color_kelvin=5000, intensity_ratio=0.10,
                      casts_shadow=False, position_hint="world_black"),
        ],
        key_fill_ratio=1.0 / 0.15,
        world=WorldSettings(exposure_ev=-1.5, environment_strength=0.15,
                            ambient_color_kelvin=5000),
        exposure_range=ExposureRange(min_ev=-4.0, max_ev=0.0),
        shadow_bounce_budget=ShadowBounceBudget(shadow_light_count=1,
                                                bounce_light_count=0),
        render_policy=RenderPolicy(max_lights=6, max_samples=256, max_bounces=2),
        description="High-contrast noir: hard key, crushed fill, deep shadows.",
    ),
    LightingPreset(
        preset_id="COMEDY_BRIGHT",
        style=LightingStyle.COMEDY,
        time_of_day=TimeOfDay.DAY,
        default_mood=LightingMood.HAPPY,
        color_policy=LightingColorPolicy.UNIFORM_CCT,
        lights=[
            LightSpec(role=LightRole.KEY, color_kelvin=5500, intensity_ratio=1.0,
                      position_hint="camera_left_45_above"),
            LightSpec(role=LightRole.FILL, color_kelvin=5200, intensity_ratio=0.60,
                      casts_shadow=False, position_hint="camera_right_30"),
            LightSpec(role=LightRole.RIM, color_kelvin=5600, intensity_ratio=0.40,
                      casts_shadow=False, position_hint="behind_subject_high"),
            LightSpec(role=LightRole.AMBIENT, color_kelvin=5400, intensity_ratio=0.35,
                      casts_shadow=False, position_hint="world_softbox"),
        ],
        key_fill_ratio=1.0 / 0.60,
        world=WorldSettings(exposure_ev=1.0, environment_strength=1.2,
                            ambient_color_kelvin=5400),
        exposure_range=ExposureRange(min_ev=0.0, max_ev=3.0),
        shadow_bounce_budget=ShadowBounceBudget(shadow_light_count=2,
                                                bounce_light_count=1),
        render_policy=RenderPolicy(max_lights=6, max_samples=48, max_bounces=2),
        description="Flat, even, overbright comedy lighting; low sample budget.",
    ),
]

_REGISTRY: dict = {p.preset_id: p for p in _PRESETS}


def _resolve_style(style: LightingStyle) -> LightingStyle:
    return _STYLE_ALIASES.get(style, style)


def select_preset(style: LightingStyle, time_of_day: TimeOfDay) -> LightingPreset:
    """Deterministically select the versioned preset for style + time-of-day.

    Exact (style, time-of-day) match first; style-only fallback second
    (presets registered without a time-of-day constraint, or the style's
    first registered preset); unknown style fails closed.
    """
    resolved = _resolve_style(style)
    candidates = [p for p in _PRESETS if p.style == resolved]
    if not candidates:
        raise LightingCompileError(
            f"no lighting preset registered for style {getattr(style, 'value', style)!r}",
            details={"style": getattr(style, "value", str(style)),
                     "time_of_day": getattr(time_of_day, "value", str(time_of_day))})
    for preset in candidates:
        if preset.time_of_day == time_of_day:
            return preset
    # style-only fallback: prefer a preset matching the mood-free intent;
    # otherwise the style's first registered preset (registry order is
    # canonical and deterministic).
    return candidates[0]


def get_preset(preset_id: str) -> LightingPreset:
    """Fetch a preset by id; unknown ids fail closed."""
    preset = _REGISTRY.get(preset_id)
    if preset is None:
        raise LightingCompileError(
            f"unknown lighting preset {preset_id!r}",
            details={"preset_id": preset_id})
    return preset


def all_presets() -> List[LightingPreset]:
    return list(_PRESETS)


def supported_preset_ids() -> List[str]:
    return list(_PRESET_ORDER)


__all__ = [
    "PRESET_REGISTRY_VERSION",
    "LightingPreset",
    "select_preset",
    "get_preset",
    "all_presets",
    "supported_preset_ids",
]
