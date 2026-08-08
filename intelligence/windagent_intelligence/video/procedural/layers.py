"""
Procedural layer registry (VP3D Phase 16, stage_h §4 backlog 1/2).

The ten procedural layers — look-at, head/eye tracking, hand/foot IK, path
following, object grab, sitting alignment, turning, idle variation — each
declare their bone ownership (from core LAYER_OWNERSHIP), default priority
and input constraint schema. A layer never overwrites keyframes outside its
ownership; the compiler rejects out-of-ownership or conflicting specs before
any bake starts.
"""

from __future__ import annotations

from typing import Any, Dict, List

from windagent_core.domain.video_production.enums import (
    ProceduralLayerKind,
    SemanticBone,
)
from windagent_core.domain.video_production.procedural import (
    ANCHOR_REQUIRED_KINDS,
    LAYER_DEFAULT_PRIORITY,
    LAYER_OWNERSHIP,
)

PROCEDURAL_LAYER_REGISTRY_VERSION = "1.0.0"

# Input constraint schema per layer kind: allowed keys + defaults. Unknown
# keys are tolerated (extra metadata), missing keys fall back to defaults.
LAYER_INPUT_SCHEMA: Dict[ProceduralLayerKind, Dict[str, Any]] = {
    ProceduralLayerKind.LOOK_AT: {
        "target_dx": 0.0, "target_dz": 1.0, "max_turn_degrees": 75.0},
    ProceduralLayerKind.HEAD_TRACKING: {
        "target_dx": 0.0, "target_dz": 1.0, "max_turn_degrees": 60.0},
    ProceduralLayerKind.EYE_TRACKING: {
        "target_dx": 0.0, "target_dz": 1.0, "max_offset_mm": 15.0},
    ProceduralLayerKind.HAND_IK: {
        "target_distance_m": 0.0, "arm_span_m": 0.7,
        "max_bend_degrees": 150.0},
    ProceduralLayerKind.FOOT_IK: {
        "path_length_m": 0.0, "step_height_m": 0.15},
    ProceduralLayerKind.PATH_FOLLOW: {
        "path_length_m": 0.0, "obstacle_count": 0, "obstacle_hits": 0},
    ProceduralLayerKind.OBJECT_GRAB: {
        "anchor_id": "", "target_distance_m": 0.0, "max_reach_m": 0.6},
    ProceduralLayerKind.SITTING_ALIGNMENT: {
        "anchor_id": "", "seat_height_m": 0.45, "hip_height_m": 0.9},
    ProceduralLayerKind.TURNING: {"turn_degrees": 0.0},
    ProceduralLayerKind.IDLE_VARIATION: {"variation_samples": 4},
}


def ownership(kind: ProceduralLayerKind) -> List[SemanticBone]:
    """Bones a layer kind may touch (empty = unknown kind)."""
    return list(LAYER_OWNERSHIP.get(kind, []))


def default_priority(kind: ProceduralLayerKind) -> int:
    return LAYER_DEFAULT_PRIORITY.get(kind, 0)


def input_defaults(kind: ProceduralLayerKind) -> Dict[str, Any]:
    return dict(LAYER_INPUT_SCHEMA.get(kind, {}))


def requires_anchor(kind: ProceduralLayerKind) -> bool:
    return kind in ANCHOR_REQUIRED_KINDS


def supported_layer_kinds() -> List[str]:
    return [k.value for k in ProceduralLayerKind]


__all__ = [
    "PROCEDURAL_LAYER_REGISTRY_VERSION",
    "LAYER_INPUT_SCHEMA",
    "ownership",
    "default_priority",
    "input_defaults",
    "requires_anchor",
    "supported_layer_kinds",
]
