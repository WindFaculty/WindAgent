"""
Procedural animation compiler (VP3D Phase 16, stage_h §4) — orchestrator.

Builds layer recipes on top of an `AnimationTrack` and bakes deterministic
derived actions:

- recipe build (backlog 2): every layer spec is checked against its kind's
  bone ownership (OUTSIDE_OWNERSHIP) and against same-priority bone
  conflicts (LAYER_CONFLICT); violations fail closed with
  `ProceduralCompileError` — no layer ever overwrites keyframes outside its
  ownership;
- bake (backlog 3/5): `BakeService` computes per-layer metrics from inputs +
  track + deterministic seed; the derived action records recipe + compiler
  version so it can be rebuilt;
- validation (backlog 4): foot sliding, hand reach, joint limit, collision,
  balance and transition continuity are blocking — a bake with any blocking
  finding is never published (all-or-nothing);
- repair scoping (backlog 6): `repair_scope` diffs two recipes per layer, so
  only the broken layer's baked contribution is invalidated — never a
  whole-scene re-bake;
- invalidation (§6): a changed bake invalidates ONLY its derived
  action/render — never assets, rigs, audio or the body clip.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.procedural import (
    ProceduralLayerSpec,
    ProceduralRecipe,
    ProceduralValidationReport,
    ProceduralValidator,
)
from windagent_core.domain.video_production.errors import ProceduralCompileError
from windagent_core.domain.video_production.ids import (
    AnimationTrackId,
    ProceduralRecipeId,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.procedural.baker import BakeService
from windagent_intelligence.video.procedural.layers import (
    PROCEDURAL_LAYER_REGISTRY_VERSION,
    default_priority,
)

PROCEDURAL_COMPILER_LAYER_VERSION = "1.0.0"


class ProceduralBakeReceipt:
    """Result of one bake: derived action + validation + invalidation scope."""

    def __init__(
        self,
        *,
        baked_action,
        validation: ProceduralValidationReport,
        invalidated_artifacts: Optional[List[str]] = None,
        cleaned_ok: bool = True,
    ) -> None:
        self.baked_action = baked_action
        self.validation = validation
        self.invalidated_artifacts = invalidated_artifacts or []
        self.cleaned_ok = cleaned_ok

    @property
    def bake_hash(self) -> str:
        return self.baked_action.bake_hash

    @property
    def blocking_kinds(self) -> List[str]:
        return self.validation.blocking_kinds


class ProceduralCompiler:
    """Deterministic procedural recipe builder + baker (stage_h §4)."""

    compiler_version = PROCEDURAL_COMPILER_LAYER_VERSION
    registry_version = PROCEDURAL_LAYER_REGISTRY_VERSION

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        validator: Optional[ProceduralValidator] = None,
        baker: Optional[BakeService] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.validator = validator or ProceduralValidator()
        self.baker = baker or BakeService(id_factory=self.id_factory)

    # ------------------------------------------------------------------
    def build_recipe(
        self,
        *,
        track,
        layer_specs: List[ProceduralLayerSpec],
        seed: int = 1,
    ) -> ProceduralRecipe:
        """Backlog 2: validate ownership/conflicts, then build the recipe."""
        seen = set()
        for spec in layer_specs:
            key = str(spec.layer_id)
            if key in seen:
                raise ProceduralCompileError(
                    "duplicate procedural layer id",
                    details={"layer_id": key})
            seen.add(key)

        specs = [
            spec if spec.priority else spec.model_copy(update={
                "priority": default_priority(spec.kind)})
            for spec in layer_specs
        ]
        recipe = ProceduralRecipe(
            recipe_id=ProceduralRecipeId(
                self.id_factory.procedural_recipe_id(track.track_id)),
            track_id=AnimationTrackId(str(track.track_id)),
            layers=specs,
            seed=seed,
            compiler_version=self.compiler_version,
        )
        report = self.validator.validate_recipe(recipe)
        if report.blocking_findings:
            raise ProceduralCompileError(
                "procedural recipe failed validation; nothing is baked.",
                details={
                    "track_id": str(track.track_id),
                    "blocking_count": len(report.blocking_findings),
                    "kinds": report.blocking_kinds,
                })
        return recipe.model_copy(update={
            "recipe_hash": recipe.compute_stable_hash()})

    # ------------------------------------------------------------------
    def bake(
        self,
        *,
        recipe: ProceduralRecipe,
        track,
        anchors: Optional[Dict[str, Any]] = None,
        prior_bake_hash: Optional[str] = None,
        require_clean: bool = True,
    ) -> ProceduralBakeReceipt:
        """Backlog 3/5: bake deterministically; blocking findings never publish."""
        baked_action = self.baker.bake(
            recipe=recipe, track=track, anchors=anchors)
        report = self.validator.validate_bake(baked_action, track)
        if require_clean and report.blocking_findings:
            raise ValidationFailureError(
                "Procedural bake failed validation; no derived action is "
                "published.",
                details={
                    "track_id": str(track.track_id),
                    "blocking_count": len(report.blocking_findings),
                    "kinds": report.blocking_kinds,
                })
        return ProceduralBakeReceipt(
            baked_action=baked_action,
            validation=report,
            invalidated_artifacts=self._invalidation_scope(
                prior_bake_hash, baked_action.bake_hash, track.track_id),
            cleaned_ok=not report.blocking_findings,
        )

    # ------------------------------------------------------------------
    def repair_scope(self, old_recipe: ProceduralRecipe,
                     new_recipe: ProceduralRecipe) -> List[str]:
        """Backlog 6: only layers whose spec changed are re-baked.

        A changed recipe seed feeds every layer's variation, so it widens
        the scope to all layers; otherwise only the diffed layer ids are
        invalidated — unchanged layers keep their baked contribution.
        """
        if old_recipe.seed != new_recipe.seed:
            return sorted({f"procedural/layer:{s.layer_id}"
                           for s in new_recipe.layers})
        old_map = {str(s.layer_id): s for s in old_recipe.layers}
        new_map = {str(s.layer_id): s for s in new_recipe.layers}
        changed = []
        for layer_id in sorted(set(old_map) | set(new_map)):
            if old_map.get(layer_id) != new_map.get(layer_id):
                changed.append(f"procedural/layer:{layer_id}")
        return changed

    # ------------------------------------------------------------------
    @staticmethod
    def _invalidation_scope(prior_hash: Optional[str], current_hash: str,
                            track_id) -> List[str]:
        """Unchanged bake -> nothing invalidated; changed -> derived action only."""
        if prior_hash is None:
            return []
        if prior_hash == current_hash:
            return []
        return [f"procedural/bake:{track_id}"]


__all__ = [
    "PROCEDURAL_COMPILER_LAYER_VERSION",
    "ProceduralBakeReceipt",
    "ProceduralCompiler",
]
