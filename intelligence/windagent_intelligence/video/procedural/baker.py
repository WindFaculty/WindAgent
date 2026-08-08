"""
Deterministic procedural baker (VP3D Phase 16, stage_h §4 backlog 3/5).

Bakes a recipe into a derived action: every enabled layer contributes a
typed metric computed from its input constraints + the track's motion data +
the deterministic seed (backlog 3). The same recipe + seed + track always
produce the identical bake hash (backlog 5: the recipe + compiler version
are recorded so the derived action can be rebuilt).

Anchor-bound layers (grab, sitting) fail closed with
`ProceduralCompileError` (ANCHOR_MISMATCH) when their anchor_id is missing
or not in the anchors map — a wrong anchor is never silently used
(stage_h §6: sit/grab với anchor sai).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.enums import ProceduralLayerKind
from windagent_core.domain.video_production.errors import ProceduralCompileError
from windagent_core.domain.video_production.ids import (
    AnimationTrackId,
    BakedActionId,
    ProceduralRecipeId,
)
from windagent_core.domain.video_production.procedural import (
    ANCHOR_REQUIRED_KINDS,
    BakedAction,
    LayerBakeResult,
    ProceduralLayerSpec,
    ProceduralRecipe,
)
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.procedural.layers import (
    input_defaults,
    ownership,
)


class BakeService:
    """Deterministic recipe -> derived-action baker (backlog 3/5)."""

    def __init__(self, id_factory: Optional[StableIdFactory] = None) -> None:
        self.id_factory = id_factory or StableIdFactory()

    def bake(
        self,
        *,
        recipe: ProceduralRecipe,
        track,
        anchors: Optional[Dict[str, Any]] = None,
    ) -> BakedAction:
        anchors = anchors or {}
        results: List[LayerBakeResult] = []
        for spec in recipe.ordered_layers():
            if not spec.enabled:
                continue
            inputs = {**input_defaults(spec.kind), **spec.input}
            self._check_anchor(spec, inputs, anchors)
            effective_seed = spec.seed if spec.seed else recipe.seed
            metric = self._compute_metric(spec, inputs, track, effective_seed)
            result = LayerBakeResult(
                layer_id=spec.layer_id,
                layer_kind=spec.kind,
                priority=spec.priority,
                owned_bones=list(ownership(spec.kind)),
                seed=effective_seed,
                metric=metric,
            )
            result = result.model_copy(update={
                "layer_hash": result.compute_stable_hash()})
            results.append(result)

        motion_metrics = self._aggregate(results)
        bake = BakedAction(
            bake_id=BakedActionId(self.id_factory.baked_action_id(
                track.track_id)),
            track_id=AnimationTrackId(str(track.track_id)),
            recipe_id=ProceduralRecipeId(str(recipe.recipe_id)),
            recipe_hash=recipe.recipe_hash,
            layers=results,
            frame_count=track.frame_count,
            fps=track.fps,
            motion_metrics=motion_metrics,
            compiler_version=recipe.compiler_version,
        )
        return bake.model_copy(update={"bake_hash": bake.compute_stable_hash()})

    # ------------------------------------------------------------------
    @staticmethod
    def _check_anchor(spec: ProceduralLayerSpec, inputs: Dict[str, Any],
                      anchors: Dict[str, Any]) -> None:
        if spec.kind not in ANCHOR_REQUIRED_KINDS:
            return
        anchor_id = inputs.get("anchor_id")
        if not anchor_id or anchor_id not in anchors:
            raise ProceduralCompileError(
                f"{spec.kind.value} layer anchor missing or mismatched",
                details={
                    "kind": "ANCHOR_MISMATCH",
                    "layer_id": str(spec.layer_id),
                    "anchor_id": anchor_id or "",
                    "known_anchors": sorted(anchors),
                })

    @staticmethod
    def _compute_metric(spec: ProceduralLayerSpec, inputs: Dict[str, Any],
                        track, seed: int) -> Dict[str, Any]:
        """Deterministic per-layer metric from inputs + track + seed."""
        kind = spec.kind
        dx = float(inputs.get("target_dx", 0.0))
        dz = float(inputs.get("target_dz", 1.0))
        if kind == ProceduralLayerKind.LOOK_AT:
            turn = math.degrees(math.atan2(abs(dx), max(abs(dz), 1e-6)))
            return {
                "turn_degrees": round(turn, 3),
                "joint_limit_violations": (
                    1 if turn > float(inputs.get("max_turn_degrees", 75.0))
                    else 0),
            }
        if kind == ProceduralLayerKind.HEAD_TRACKING:
            turn = math.degrees(math.atan2(abs(dx), max(abs(dz), 1e-6))) / 2
            return {
                "head_turn_degrees": round(turn, 3),
                "joint_limit_violations": (
                    1 if turn > float(inputs.get("max_turn_degrees", 60.0))
                    else 0),
            }
        if kind == ProceduralLayerKind.EYE_TRACKING:
            offset_mm = abs(dx) * 10.0
            return {
                "eye_offset_mm": round(offset_mm, 3),
                "joint_limit_violations": (
                    1 if offset_mm > float(inputs.get("max_offset_mm", 15.0))
                    else 0),
            }
        if kind == ProceduralLayerKind.HAND_IK:
            distance = float(inputs.get("target_distance_m", 0.0))
            span = float(inputs.get("arm_span_m", 0.7))
            return {
                "reach_meters": round(max(0.0, distance - span), 3),
                "joint_limit_violations": 1 if distance > span else 0,
            }
        if kind == ProceduralLayerKind.FOOT_IK:
            slide = max(0.0, float(inputs.get("path_length_m", 0.0))
                        - float(track.root_motion_meters))
            return {
                "foot_slide_meters": round(slide, 3),
                "step_height_m": float(inputs.get("step_height_m", 0.15)),
            }
        if kind == ProceduralLayerKind.PATH_FOLLOW:
            path = float(inputs.get("path_length_m", 0.0))
            slide = max(0.0, path - float(track.root_motion_meters))
            return {
                "path_length_m": round(path, 3),
                "foot_slide_meters": round(slide, 3),
                "collision_count": int(inputs.get("obstacle_hits", 0)),
                "obstacle_count": int(inputs.get("obstacle_count", 0)),
            }
        if kind == ProceduralLayerKind.OBJECT_GRAB:
            distance = float(inputs.get("target_distance_m", 0.0))
            max_reach = float(inputs.get("max_reach_m", 0.6))
            reach = max(0.0, distance - max_reach)
            return {
                "reach_meters": round(reach, 3),
                "grab_ok": reach <= 0.0,
                "anchor_id": inputs.get("anchor_id", ""),
            }
        if kind == ProceduralLayerKind.SITTING_ALIGNMENT:
            offset = abs(float(inputs.get("seat_height_m", 0.45))
                         - float(inputs.get("hip_height_m", 0.9)))
            return {
                "seat_offset_m": round(offset, 3),
                "anchor_id": inputs.get("anchor_id", ""),
            }
        if kind == ProceduralLayerKind.TURNING:
            return {"turn_degrees": round(
                abs(float(inputs.get("turn_degrees", 0.0))), 3)}
        if kind == ProceduralLayerKind.IDLE_VARIATION:
            # deterministic variation from the effective seed (backlog 3):
            # same seed -> same offsets, same balance
            balance = ((seed % 1000) / 1000.0 - 0.5) * 0.3
            return {
                "variation_samples": int(
                    inputs.get("variation_samples", 4)),
                "balance_offset_m": round(balance, 4),
            }
        return {}

    @staticmethod
    def _aggregate(results: List[LayerBakeResult]) -> Dict[str, Any]:
        def _max(key: str, default: float = 0.0) -> float:
            values = [float(m.get(key, default) or default)
                      for m in (r.metric for r in results)]
            return max(values, default=default)

        def _sum(key: str) -> int:
            return sum(int(m.get(key, 0) or 0)
                       for m in (r.metric for r in results))

        return {
            "foot_slide_meters": _max("foot_slide_meters"),
            "reach_meters": _max("reach_meters"),
            "joint_limit_violations": _sum("joint_limit_violations"),
            "collision_count": _sum("collision_count"),
            "balance_offset_m": _max("balance_offset_m"),
            "boundary_drift_frames": 0,  # bake always covers the track exactly
        }


__all__ = ["BakeService"]
