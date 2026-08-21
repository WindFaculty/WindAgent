"""
Lighting compiler (VP3D Phase 14, stage_g §4) — orchestrator.

Maps the Director's `LightingIntent` onto a deterministic, versioned
`LightRigPlan`:

- preset selection (backlog 1/2) via `select_preset` — the model never
  places unlimited lights; every preset pins types, ratios, color policy,
  world settings, shadow/bounce budget, exposure range and render policy;
- bounded adjustments (backlog 3) via a typed `LightOverride` — exposure
  shift ±2 EV, key multiplier [0.5, 2.0], CCT shift ±1500 K; out-of-bounds
  or preset-mismatched overrides fail closed with
  `LightingOverrideOutOfBoundsError`;
- resource estimate + render policy enforcement (backlog 4) — a rig that
  exceeds max lights/samples/bounces fails closed (POLICY_EXCEEDED);
- validation (backlog 5) — missing key light, clipped exposure,
  inconsistent color temperature, continuity drift between shots sharing a
  continuity key are blocking; noise risk is advisory;
- contact sheet / histogram (backlog 6) via `ContactSheetBuilder` for the
  reviewer before Cycles;
- the intent/rig stay engine-neutral (backlog 7) so Stage Q can map the
  same intent to Unreal/Lumen.

Invalidation (§5): a changed light rig invalidates ONLY the owning shot's
dependent preview/render — never assets, rigs or audio.
"""

from __future__ import annotations

import hashlib
import json
from typing import List, Optional

from windagent_core.domain.video_production.enums import LightRole
from windagent_core.domain.video_production.errors import (
    LightingOverrideOutOfBoundsError,
)
from windagent_core.domain.video_production.ids import LightRigPlanId, ShotId
from windagent_core.domain.video_production.lighting import (
    MAX_CCT_SHIFT_K,
    MAX_EXPOSURE_SHIFT_EV,
    MAX_KEY_MULTIPLIER,
    MIN_KEY_MULTIPLIER,
    LightOverride,
    LightRigPlan,
    LightSpec,
    LightingIntent,
    LightingPreset,
    LightingValidationReport,
    LightingValidator,
    ResourceEstimate,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.lighting.contact_sheet import (
    ContactSheetBuilder,
    LightingContactSheetManifest,
)
from windagent_intelligence.video.lighting.presets import (
    PRESET_REGISTRY_VERSION,
    select_preset,
)

LIGHTING_COMPILER_LAYER_VERSION = "1.0.0"

# cost model (backlog 4): a shadow light costs more than a fill light;
# samples and bounces dominate the render budget.
COST_PER_LIGHT = 10
COST_PER_SHADOW_LIGHT = 5
COST_PER_SAMPLE = 1
COST_PER_BOUNCE = 8


class LightingCompileReceipt:
    """Result of one lighting compile: plan + validation + invalidation scope."""

    def __init__(
        self,
        *,
        plan: LightRigPlan,
        validation: LightingValidationReport,
        invalidated_artifacts: Optional[List[str]] = None,
        cleaned_ok: bool = True,
    ) -> None:
        self.plan = plan
        self.validation = validation
        self.invalidated_artifacts = invalidated_artifacts or []
        self.cleaned_ok = cleaned_ok

    @property
    def rig_hash(self) -> str:
        return self.plan.rig_hash

    @property
    def blocking_kinds(self) -> List[str]:
        return self.validation.blocking_kinds


class LightingCompiler:
    """Deterministic lighting-intent -> light-rig-plan compiler (stage_g §4)."""

    compiler_version = LIGHTING_COMPILER_LAYER_VERSION
    presets_version = PRESET_REGISTRY_VERSION

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        validator: Optional[LightingValidator] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.validator = validator or LightingValidator()

    # ------------------------------------------------------------------
    def compile(
        self,
        *,
        intent: LightingIntent,
        override: Optional[LightOverride] = None,
        previous_plan: Optional[LightRigPlan] = None,
        require_clean: bool = True,
        prior_rig_hash: Optional[str] = None,
    ) -> LightingCompileReceipt:
        """Compile one shot's lighting intent into a typed light rig plan.

        ``previous_plan`` is the adjacent shot's rig; when both share a
        continuity key, drift beyond tolerance fails closed (backlog 5).
        ``prior_rig_hash`` enables invalidation scoping (§5).
        """
        preset = select_preset(intent.style, intent.time_of_day)
        override_id = ""
        if override is not None and override.active:
            self._check_override(override, preset)
            override_id = str(override.override_id)

        lights = self._apply_override_lights(preset, override)
        world = preset.world
        emphasis = (
            override.emphasis if override is not None and override.emphasis
            else intent.emphasis)
        if override is not None and override.active:
            world = world.model_copy(update={
                "exposure_ev": world.exposure_ev + override.exposure_ev_shift})

        resource = self._estimate_resource(preset, lights)
        plan = LightRigPlan(
            rig_id=LightRigPlanId(
                self.id_factory.light_rig_plan_id(intent.shot_id)),
            shot_id=intent.shot_id,
            scene_id=intent.scene_id,
            preset_id=preset.preset_id,
            preset_version=preset.version,
            preset_hash=preset.preset_hash(),
            color_policy=preset.color_policy,
            lights=lights,
            key_fill_ratio=preset.key_fill_ratio,
            world=world,
            exposure_range=preset.exposure_range,
            shadow_bounce_budget=preset.shadow_bounce_budget,
            render_policy=preset.render_policy,
            resource=resource,
            emphasis=emphasis,
            continuity_key=intent.continuity_key,
            intent_hash=self._intent_hash(intent),
            override_id=override_id,
        )
        plan = plan.model_copy(update={"rig_hash": plan.compute_stable_hash()})

        report = self.validator.validate(
            intent=intent, preset=preset, rig_plan=plan,
            previous_plan=previous_plan,
            finding_prefix=self.id_factory.lighting_finding_id(
                intent.shot_id))

        if require_clean and report.blocking_findings:
            raise ValidationFailureError(
                "Lighting rig failed validation; no rig plan is published.",
                details={
                    "shot_id": str(intent.shot_id),
                    "blocking_count": len(report.blocking_findings),
                    "kinds": report.blocking_kinds,
                },
            )

        return LightingCompileReceipt(
            plan=plan,
            validation=report,
            invalidated_artifacts=self._invalidation_scope(
                plan.rig_hash, prior_rig_hash, intent.shot_id),
            cleaned_ok=not report.blocking_findings,
        )

    # ------------------------------------------------------------------
    def build_contact_sheet(
        self, plan: LightRigPlan, builder: Optional[ContactSheetBuilder] = None
    ) -> LightingContactSheetManifest:
        """Backlog 6: deterministic contact sheet/histogram for the reviewer."""
        builder = builder or ContactSheetBuilder()
        return builder.build(
            plan=plan,
            sheet_id=self.id_factory.lighting_contact_sheet_id(plan.shot_id))

    # ------------------------------------------------------------------
    def _check_override(self, override: LightOverride,
                        preset: LightingPreset) -> None:
        """Backlog 3: overrides are bounded and preset-matched (fail closed)."""
        if override.preset_id != preset.preset_id:
            raise LightingOverrideOutOfBoundsError(
                "lighting override targets a different preset",
                details={
                    "shot_id": str(override.shot_id),
                    "override_preset": override.preset_id,
                    "selected_preset": preset.preset_id,
                })
        problems = {}
        if abs(override.exposure_ev_shift) > MAX_EXPOSURE_SHIFT_EV:
            problems["exposure_ev_shift"] = override.exposure_ev_shift
        if not (MIN_KEY_MULTIPLIER <= override.key_multiplier
                <= MAX_KEY_MULTIPLIER):
            problems["key_multiplier"] = override.key_multiplier
        if abs(override.cct_shift_kelvin) > MAX_CCT_SHIFT_K:
            problems["cct_shift_kelvin"] = override.cct_shift_kelvin
        if problems:
            raise LightingOverrideOutOfBoundsError(
                "lighting override exceeds bounded adjustment",
                details={"shot_id": str(override.shot_id),
                         "violations": problems})

    @staticmethod
    def _apply_override_lights(
        preset: LightingPreset, override: Optional[LightOverride]
    ) -> List[LightSpec]:
        """Backlog 3: key multiplier + uniform CCT shift, bounded by checks."""
        if override is None or not override.active:
            return list(preset.lights)
        return [
            LightSpec(
                role=light.role,
                color_kelvin=max(
                    1000, min(20000,
                              light.color_kelvin + override.cct_shift_kelvin)),
                intensity_ratio=(
                    light.intensity_ratio * override.key_multiplier
                    if light.role == LightRole.KEY else light.intensity_ratio),
                casts_shadow=light.casts_shadow,
                position_hint=light.position_hint,
                cost_units=light.cost_units,
            )
            for light in preset.lights
        ]

    @staticmethod
    def _estimate_resource(preset: LightingPreset,
                           lights: List[LightSpec]) -> ResourceEstimate:
        """Backlog 4: contribution/cost estimate vs the preset's policy."""
        shadow_count = sum(1 for light in lights if light.casts_shadow)
        bounce_count = sum(
            1 for light in lights if light.role == LightRole.BOUNCE)
        total_cost = (
            len(lights) * COST_PER_LIGHT
            + shadow_count * COST_PER_SHADOW_LIGHT
            + preset.render_policy.max_samples * COST_PER_SAMPLE
            + preset.render_policy.max_bounces * COST_PER_BOUNCE)
        within = (
            len(lights) <= preset.render_policy.max_lights
            and shadow_count
            <= preset.shadow_bounce_budget.shadow_light_count
            and bounce_count
            <= preset.shadow_bounce_budget.bounce_light_count)
        return ResourceEstimate(
            light_count=len(lights),
            sample_count=preset.render_policy.max_samples,
            bounce_count=preset.render_policy.max_bounces,
            shadow_light_count=shadow_count,
            bounce_light_count=bounce_count,
            total_cost_units=total_cost,
            within_policy=within,
        )

    @staticmethod
    def _intent_hash(intent: LightingIntent) -> str:
        payload = json.loads(intent.model_dump_json())
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _invalidation_scope(current_hash: str, prior_hash: Optional[str],
                            shot_id: ShotId) -> List[str]:
        """Unchanged rig -> nothing invalidated; changed -> preview/render only.

        §5: changing the light invalidates ONLY the owning shot's dependent
        preview/render — never assets, rigs or audio (they carry their own
        revision hashes).
        """
        if prior_hash is None:
            return []
        if prior_hash == current_hash:
            return []
        return [f"preview/render:{shot_id}"]


__all__ = [
    "LIGHTING_COMPILER_LAYER_VERSION",
    "COST_PER_LIGHT",
    "COST_PER_SHADOW_LIGHT",
    "COST_PER_SAMPLE",
    "COST_PER_BOUNCE",
    "LightingCompileReceipt",
    "LightingCompiler",
]
