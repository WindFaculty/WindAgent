"""
Stage G Lighting System domain (VP3D Phase 14 — Lighting System).

Frozen, engine-neutral DTOs for lighting intent, the versioned preset the
compiler selects, and the typed light rig plan the engine can realize.
No ``bpy``, no provider SDK, no transport object ever appears here: the
compiler layer (`intelligence/windagent_intelligence/video/lighting/`) maps
the Director's `LightingIntent` onto a versioned preset, and the Blender
adapter (tools layer) transcribes the plan. Intent stays neutral so Stage Q
can map the same intent to Unreal/Lumen (stage_g §4 backlog 7).

Semantics (stage_g §4):
- `LightingIntent(mood, time_of_day, style, emphasis, continuity_key)` is
  what the Director means; the compiler selects a versioned `LightingPreset`
  (backlog 1) — the model never places unlimited lights.
- Every preset pins light types, ratios, color policy, world settings,
  shadow/bounce budget and exposure range (backlog 2).
- Adjustments are bounded and live inside a typed `LightOverride` (backlog
  3): exposure shift ±2 EV, key multiplier [0.5, 2.0], CCT shift ±1500 K.
  Out-of-bounds overrides fail closed with
  `LightingOverrideOutOfBoundsError`.
- Resource cost is estimated and enforced against the preset's render
  policy (backlog 4) — a rig that exceeds max lights/samples/bounces fails
  closed with a POLICY_EXCEEDED finding.
- Validation (backlog 5) is fail-closed: missing key light, clipped
  exposure, inconsistent color temperature, and continuity drift between
  shots sharing a continuity key are blocking; noise risk is advisory.
- The contact sheet / histogram manifest (backlog 6) is a deterministic,
  engine-neutral proxy for the reviewer; real renders stay in the
  renderer/tools layer and keep human review at low confidence (stage_g §6).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    LightRole,
    LightingColorPolicy,
    LightingEmphasis,
    LightingMood,
    LightingStyle,
    TimeOfDay,
)
from windagent_core.domain.video_production.ids import (
    LightOverrideId,
    LightRigPlanId,
    LightingFindingId,
    LightingIntentId,
    SceneId,
    ShotId,
)

LIGHTING_COMPILER_VERSION = "1.0.0"
LIGHTING_RIG_SCHEMA_VERSION = "1.0.0"

# Proxy validation thresholds (stage_g §4 backlog 4/5). Raw measurements are
# surfaced in findings so evidence shows the numbers, not just pass/fail.
MIN_EXPOSURE_EV = -8.0
MAX_EXPOSURE_EV = 8.0
# CCT spread tolerance per color policy (kelvin).
COLOR_POLICY_TOLERANCE_K = {
    LightingColorPolicy.UNIFORM_CCT: 800,
    LightingColorPolicy.WARM_COOL_SPLIT: 4000,
    LightingColorPolicy.COOL_MOONLIGHT: 1500,
    LightingColorPolicy.WARM_FIRELIGHT: 1500,
    LightingColorPolicy.MULTICOLOR: 6000,
}
MIN_SAMPLES_LOW_NOISE = 64
MIN_BOUNCES_LOW_NOISE = 2
# Continuity drift tolerance between adjacent shots sharing a continuity key.
CONTINUITY_EV_TOLERANCE = 1.0
CONTINUITY_RATIO_TOLERANCE = 0.25
CONTINUITY_CCT_TOLERANCE_K = 1500
# Bounded override limits (backlog 3).
MAX_EXPOSURE_SHIFT_EV = 2.0
MIN_KEY_MULTIPLIER = 0.5
MAX_KEY_MULTIPLIER = 2.0
MAX_CCT_SHIFT_K = 1500


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Preset building blocks
# ---------------------------------------------------------------------------
class LightSpec(BaseModel):
    """One typed light in a rig: role, color, ratio, shadow, placement hint.

    `position_hint` is an engine-neutral description (e.g. "camera_left_45")
    — the adapter decides exact coordinates; nothing engine-specific leaks
    into the intent (stage_g §4 backlog 7).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: LightRole
    color_kelvin: int = Field(ge=1000, le=20000)
    intensity_ratio: float = Field(gt=0.0, le=10.0)
    casts_shadow: bool = True
    position_hint: str = ""
    cost_units: int = Field(default=10, ge=0)


class WorldSettings(BaseModel):
    """World/exposure settings pinned by a preset (backlog 2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exposure_ev: float
    environment_strength: float = Field(ge=0.0)
    ambient_color_kelvin: int = Field(ge=1000, le=20000)


class ExposureRange(BaseModel):
    """Valid exposure band for a preset; exposure outside it clips (backlog 5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_ev: float = Field(ge=MIN_EXPOSURE_EV)
    max_ev: float = Field(le=MAX_EXPOSURE_EV)

    def contains(self, ev: float) -> bool:
        return self.min_ev - 1e-9 <= ev <= self.max_ev + 1e-9


class ShadowBounceBudget(BaseModel):
    """How many shadow-casting / bounce lights the renderer may afford."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shadow_light_count: int = Field(ge=0)
    bounce_light_count: int = Field(ge=0)


class RenderPolicy(BaseModel):
    """Hard render budget: no light/sample/bounce may exceed it (backlog 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_lights: int = Field(ge=1)
    max_samples: int = Field(ge=1)
    max_bounces: int = Field(ge=0)


class LightingPreset(BaseModel):
    """A versioned, approved lighting preset (stage_g §4 backlog 1/2).

    Everything the rig needs is pinned here: light types and ratios, color
    policy, world settings, shadow/bounce budget, exposure range and render
    policy. The preset id + version participate in the rig hash so a changed
    preset deterministically changes every dependent rig manifest.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    preset_id: str = Field(min_length=1)
    version: str = LIGHTING_COMPILER_VERSION
    style: LightingStyle
    time_of_day: TimeOfDay
    default_mood: LightingMood
    color_policy: LightingColorPolicy
    lights: List[LightSpec] = Field(min_length=1)
    key_fill_ratio: float = Field(gt=0.0)
    world: WorldSettings
    exposure_range: ExposureRange
    shadow_bounce_budget: ShadowBounceBudget
    render_policy: RenderPolicy
    description: str = ""

    def preset_hash(self) -> str:
        payload = json.loads(
            self.model_dump_json(exclude={"description"}))
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def key_light(self) -> Optional[LightSpec]:
        for light in self.lights:
            if light.role == LightRole.KEY:
                return light
        return None


# ---------------------------------------------------------------------------
# Intent / override / compiled rig plan
# ---------------------------------------------------------------------------
class LightingIntent(BaseModel):
    """What the Director means for one shot's light (stage_g §4 contract).

    The compiler selects the versioned preset from style + time-of-day;
    mood/emphasis are director flavor recorded on the intent, and
    `continuity_key` ties adjacent shots so their rigs cannot drift.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    intent_id: LightingIntentId
    shot_id: ShotId
    scene_id: SceneId
    mood: LightingMood = LightingMood.NEUTRAL
    time_of_day: TimeOfDay = TimeOfDay.DAY
    style: LightingStyle = LightingStyle.CARTOON
    emphasis: LightingEmphasis = LightingEmphasis.BALANCED
    continuity_key: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LightOverride(BaseModel):
    """Bounded adjustment on top of a preset (stage_g §4 backlog 3).

    All values are clamped to typed bounds; the compiler refuses anything
    outside them with `LightingOverrideOutOfBoundsError`. `preset_id` must
    match the selected preset so an override can never be applied to the
    wrong rig family.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    override_id: LightOverrideId
    shot_id: ShotId
    preset_id: str = Field(min_length=1)
    exposure_ev_shift: float = Field(default=0.0)
    key_multiplier: float = Field(default=1.0)
    cct_shift_kelvin: int = Field(default=0)
    emphasis: Optional[LightingEmphasis] = None
    active: bool = True


class ResourceEstimate(BaseModel):
    """Estimated render contribution/cost of a rig (backlog 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    light_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    bounce_count: int = Field(ge=0)
    shadow_light_count: int = Field(ge=0)
    bounce_light_count: int = Field(ge=0)
    total_cost_units: int = Field(ge=0)
    within_policy: bool = False


class LightRigPlan(BaseModel):
    """The deterministic, versioned light rig the adapter can realize.

    = preset + bounded overrides + resource estimate. The rig hash is
    canonical: same preset/seed/compiler version -> same hash (§5).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    rig_id: LightRigPlanId
    shot_id: ShotId
    scene_id: SceneId
    preset_id: str
    preset_version: str
    preset_hash: str
    color_policy: LightingColorPolicy
    lights: List[LightSpec]
    key_fill_ratio: float
    world: WorldSettings
    exposure_range: ExposureRange
    shadow_bounce_budget: ShadowBounceBudget
    render_policy: RenderPolicy
    resource: ResourceEstimate
    emphasis: LightingEmphasis
    continuity_key: str = ""
    compiler_version: str = LIGHTING_COMPILER_VERSION
    schema_version: str = LIGHTING_RIG_SCHEMA_VERSION
    intent_hash: str = ""
    override_id: str = ""       # set when a bounded override was applied
    rig_hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def compute_stable_hash(self) -> str:
        # intent_hash/metadata are provenance, not rig content: the same
        # preset + overrides + compiler produce the same rig manifest even
        # when the Director's mood flavor changes (§5 determinism).
        payload = json.loads(
            self.model_dump_json(exclude={"rig_hash", "intent_hash",
                                          "metadata"}))
        canonical = json.dumps(
            {"schema_version": self.schema_version,
             "compiler_version": self.compiler_version,
             "plan": json.loads(json.dumps(payload, sort_keys=True,
                                           default=str))},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def key_light(self) -> Optional[LightSpec]:
        for light in self.lights:
            if light.role == LightRole.KEY:
                return light
        return None


# ---------------------------------------------------------------------------
# Findings + validation (fail-closed)
# ---------------------------------------------------------------------------
class LightingFindingKind:
    """Typed lighting finding kinds (stage_g §4 backlog 5 / §5 test matrix)."""

    MISSING_KEY_LIGHT = "MISSING_KEY_LIGHT"
    EXPOSURE_CLIPPED = "EXPOSURE_CLIPPED"
    INCONSISTENT_COLOR_TEMP = "INCONSISTENT_COLOR_TEMP"
    NOISE_RISK = "NOISE_RISK"                 # advisory, never blocking
    POLICY_EXCEEDED = "POLICY_EXCEEDED"
    CONTINUITY_DRIFT = "CONTINUITY_DRIFT"


class LightingFinding(BaseModel):
    """One typed lighting finding (blocking or advisory)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: LightingFindingId
    kind: str
    shot_id: ShotId = ""
    detail: str = ""
    blocking: bool = False
    measured: Dict[str, Any] = Field(default_factory=dict)


class LightingValidationReport(BaseModel):
    """Aggregate result of lighting validation over one rig plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool = False
    findings: List[LightingFinding] = Field(default_factory=list)
    checked_entity_count: int = Field(default=0, ge=0)

    @property
    def blocking_findings(self) -> List[LightingFinding]:
        return [f for f in self.findings if f.blocking]

    @property
    def blocking_kinds(self) -> List[str]:
        return sorted({f.kind for f in self.blocking_findings})


class LightingValidator:
    """Fail-closed lighting validation (stage_g §4 backlog 5).

    Pure math on presets/plans; never touches bpy or any engine.
    """

    def validate(
        self,
        *,
        intent: LightingIntent,
        preset: LightingPreset,
        rig_plan: LightRigPlan,
        previous_plan: Optional[LightRigPlan] = None,
        finding_prefix: str = "lt",
    ) -> LightingValidationReport:
        findings: List[LightingFinding] = []

        # missing key light — a rig with no KEY cannot be a lighting rig
        if rig_plan.key_light() is None:
            findings.append(self._finding(
                finding_prefix, LightingFindingKind.MISSING_KEY_LIGHT, intent,
                "no KEY light in rig plan", blocking=True,
                measured={"roles": sorted({light.role.value for light in rig_plan.lights})}))

        # clipped exposure: world EV must sit inside the preset's exposure range
        ev = rig_plan.world.exposure_ev
        if not rig_plan.exposure_range.contains(ev):
            findings.append(self._finding(
                finding_prefix, LightingFindingKind.EXPOSURE_CLIPPED, intent,
                f"exposure {ev:+.2f}EV outside preset range "
                f"[{rig_plan.exposure_range.min_ev:+.2f}, "
                f"{rig_plan.exposure_range.max_ev:+.2f}]EV",
                blocking=True,
                measured={"exposure_ev": ev,
                          "range": [rig_plan.exposure_range.min_ev,
                                    rig_plan.exposure_range.max_ev]}))
        elif not (MIN_EXPOSURE_EV <= ev <= MAX_EXPOSURE_EV):
            findings.append(self._finding(
                finding_prefix, LightingFindingKind.EXPOSURE_CLIPPED, intent,
                f"exposure {ev:+.2f}EV outside global "
                f"[{MIN_EXPOSURE_EV:+.1f}, {MAX_EXPOSURE_EV:+.1f}]EV band",
                blocking=True, measured={"exposure_ev": ev}))

        # inconsistent color temperature vs the preset's color policy
        cct_spread = self._cct_spread(rig_plan.lights)
        tolerance = COLOR_POLICY_TOLERANCE_K.get(
            rig_plan.color_policy, COLOR_POLICY_TOLERANCE_K[
                LightingColorPolicy.UNIFORM_CCT])
        if cct_spread > tolerance:
            findings.append(self._finding(
                finding_prefix, LightingFindingKind.INCONSISTENT_COLOR_TEMP,
                intent,
                f"CCT spread {cct_spread}K exceeds {tolerance}K tolerance "
                f"for {rig_plan.color_policy.value} policy",
                blocking=True,
                measured={"cct_spread_k": cct_spread, "tolerance_k": tolerance,
                          "policy": rig_plan.color_policy.value}))

        # excessive noise risk — advisory: technically correct but risky
        if (rig_plan.resource.sample_count < MIN_SAMPLES_LOW_NOISE
                or rig_plan.resource.bounce_count < MIN_BOUNCES_LOW_NOISE):
            findings.append(self._finding(
                finding_prefix, LightingFindingKind.NOISE_RISK, intent,
                f"samples {rig_plan.resource.sample_count} < "
                f"{MIN_SAMPLES_LOW_NOISE} or bounces "
                f"{rig_plan.resource.bounce_count} < {MIN_BOUNCES_LOW_NOISE}",
                blocking=False,
                measured={"sample_count": rig_plan.resource.sample_count,
                          "bounce_count": rig_plan.resource.bounce_count}))

        # render policy: no light/sample/bounce over budget (backlog 4)
        if not rig_plan.resource.within_policy:
            findings.append(self._finding(
                finding_prefix, LightingFindingKind.POLICY_EXCEEDED, intent,
                f"resource {rig_plan.resource.model_dump()} exceeds render "
                f"policy {rig_plan.render_policy.model_dump()}",
                blocking=True,
                measured={"resource": rig_plan.resource.model_dump(),
                          "policy": rig_plan.render_policy.model_dump()}))

        # continuity: adjacent shots sharing a continuity key must not drift
        if previous_plan is not None and rig_plan.continuity_key and (
                rig_plan.continuity_key == previous_plan.continuity_key):
            drift = self._continuity_drift(rig_plan, previous_plan)
            if drift is not None:
                findings.append(self._finding(
                    finding_prefix, LightingFindingKind.CONTINUITY_DRIFT,
                    intent,
                    f"continuity drift vs previous shot: {drift['detail']}",
                    blocking=True, measured=drift["measured"]))

        return LightingValidationReport(
            ok=not findings, findings=findings,
            checked_entity_count=len(rig_plan.lights))

    # ------------------------------------------------------------------
    @staticmethod
    def _cct_spread(lights: List[LightSpec]) -> int:
        if not lights:
            return 0
        kelvins = [light.color_kelvin for light in lights]
        return max(kelvins) - min(kelvins)

    @staticmethod
    def _continuity_drift(current: LightRigPlan,
                          previous: LightRigPlan) -> Optional[dict]:
        """Measured drift vs the previous shot's rig (same continuity key)."""
        measured = {}
        ev_delta = abs(current.world.exposure_ev - previous.world.exposure_ev)
        measured["exposure_ev_delta"] = ev_delta
        ratio_delta = abs(current.key_fill_ratio - previous.key_fill_ratio)
        measured["key_fill_ratio_delta"] = ratio_delta
        cct_a = current.key_light().color_kelvin if current.key_light() else 0
        cct_b = previous.key_light().color_kelvin if previous.key_light() else 0
        cct_delta = abs(cct_a - cct_b)
        measured["key_cct_delta_k"] = cct_delta
        if (ev_delta <= CONTINUITY_EV_TOLERANCE
                and ratio_delta <= CONTINUITY_RATIO_TOLERANCE
                and cct_delta <= CONTINUITY_CCT_TOLERANCE_K):
            return None
        return {
            "detail": (f"ΔEV {ev_delta:.2f} > {CONTINUITY_EV_TOLERANCE} or "
                       f"Δkey/fill {ratio_delta:.2f} > "
                       f"{CONTINUITY_RATIO_TOLERANCE} or ΔCCT {cct_delta}K > "
                       f"{CONTINUITY_CCT_TOLERANCE_K}K"),
            "measured": measured,
        }

    @staticmethod
    def _finding(prefix: str, kind: str, intent: LightingIntent,
                 detail: str, *, blocking: bool,
                 measured: Dict[str, Any]) -> LightingFinding:
        return LightingFinding(
            finding_id=LightingFindingId(f"{prefix}:{kind}"),
            kind=kind, shot_id=intent.shot_id, detail=detail,
            blocking=blocking, measured=measured)


__all__ = [
    "LIGHTING_COMPILER_VERSION",
    "LIGHTING_RIG_SCHEMA_VERSION",
    "MIN_EXPOSURE_EV",
    "MAX_EXPOSURE_EV",
    "COLOR_POLICY_TOLERANCE_K",
    "MIN_SAMPLES_LOW_NOISE",
    "MIN_BOUNCES_LOW_NOISE",
    "CONTINUITY_EV_TOLERANCE",
    "CONTINUITY_RATIO_TOLERANCE",
    "CONTINUITY_CCT_TOLERANCE_K",
    "MAX_EXPOSURE_SHIFT_EV",
    "MIN_KEY_MULTIPLIER",
    "MAX_KEY_MULTIPLIER",
    "MAX_CCT_SHIFT_K",
    "LightSpec",
    "WorldSettings",
    "ExposureRange",
    "ShadowBounceBudget",
    "RenderPolicy",
    "LightingPreset",
    "LightingIntent",
    "LightOverride",
    "ResourceEstimate",
    "LightRigPlan",
    "LightingFindingKind",
    "LightingFinding",
    "LightingValidationReport",
    "LightingValidator",
]
