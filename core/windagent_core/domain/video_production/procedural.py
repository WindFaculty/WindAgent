"""
Stage H Procedural Animation domain (VP3D Phase 16 — Procedural Animation).

Frozen, engine-neutral DTOs for procedural layers, the layer recipe and the
baked derived action. No ``bpy``, no provider SDK: the compiler layer
(`intelligence/windagent_intelligence/video/procedural/`) builds recipes,
bakes deterministic derived actions and scopes repairs per layer.

Semantics (stage_h §4):
- Procedural layers (backlog 1): look-at, head/eye tracking, hand/foot IK,
  path following, object grab, sitting alignment, turning, idle variation.
- Every layer declares input constraints, priority and affected bones
  (backlog 2) and never overwrites keyframes outside its ownership: a spec
  naming bones outside its kind's LAYER_OWNERSHIP fails closed with
  OUTSIDE_OWNERSHIP; two layers fighting over the same bones at the same
  priority fail closed with LAYER_CONFLICT.
- Deterministic seed for variation and path sampling (backlog 3): the same
  recipe + seed + track always bake the identical derived action.
- Validation (backlog 4) is fail-closed: foot sliding, hand reach, joint
  limit, collision, balance and transition continuity are blocking.
- Bake (backlog 5) records the recipe + compiler version so the derived
  action can be rebuilt; the bake hash is deterministic.
- Repair (backlog 6) is layer-scoped: a changed layer invalidates only its
  own baked contribution, never a whole-scene re-bake.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    ProceduralLayerKind,
    SemanticBone,
)
from windagent_core.domain.video_production.ids import (
    AnimationTrackId,
    BakedActionId,
    ProceduralFindingId,
    ProceduralLayerId,
    ProceduralRecipeId,
)

PROCEDURAL_COMPILER_VERSION = "1.0.0"
PROCEDURAL_RECIPE_SCHEMA_VERSION = "1.0.0"
PROCEDURAL_BAKE_SCHEMA_VERSION = "1.0.0"

# Validation thresholds (stage_h §4 backlog 4). Raw measurements are surfaced
# in findings so evidence shows the numbers, not just pass/fail.
FOOT_SLIDING_MAX_M = 0.10
HAND_REACH_TOLERANCE_M = 0.05
MAX_BALANCE_OFFSET_M = 0.10
MAX_JOINT_VIOLATIONS = 0
MAX_COLLISIONS = 0
MAX_TRANSITION_DRIFT_FRAMES = 0

# Bone ownership per layer kind (backlog 2): a layer may only touch these
# semantic bones. Priority: higher wins when layers share bones.
LAYER_OWNERSHIP: Dict[ProceduralLayerKind, List[SemanticBone]] = {
    ProceduralLayerKind.LOOK_AT: [SemanticBone.HEAD, SemanticBone.NECK],
    ProceduralLayerKind.HEAD_TRACKING: [SemanticBone.HEAD],
    ProceduralLayerKind.EYE_TRACKING: [SemanticBone.EYE_L, SemanticBone.EYE_R],
    ProceduralLayerKind.HAND_IK: [
        SemanticBone.ARM_UPPER_L, SemanticBone.ARM_UPPER_R,
        SemanticBone.ARM_LOWER_L, SemanticBone.ARM_LOWER_R,
        SemanticBone.HAND_L, SemanticBone.HAND_R],
    ProceduralLayerKind.FOOT_IK: [
        SemanticBone.THIGH_L, SemanticBone.THIGH_R,
        SemanticBone.SHIN_L, SemanticBone.SHIN_R,
        SemanticBone.FOOT_L, SemanticBone.FOOT_R,
        SemanticBone.TOE_L, SemanticBone.TOE_R],
    ProceduralLayerKind.PATH_FOLLOW: [SemanticBone.ROOT, SemanticBone.PELVIS],
    ProceduralLayerKind.OBJECT_GRAB: [
        SemanticBone.HAND_L, SemanticBone.HAND_R,
        SemanticBone.ARM_LOWER_L, SemanticBone.ARM_LOWER_R],
    ProceduralLayerKind.SITTING_ALIGNMENT: [
        SemanticBone.ROOT, SemanticBone.PELVIS,
        SemanticBone.THIGH_L, SemanticBone.THIGH_R],
    ProceduralLayerKind.TURNING: [SemanticBone.ROOT, SemanticBone.PELVIS],
    ProceduralLayerKind.IDLE_VARIATION: [
        SemanticBone.SPINE, SemanticBone.HEAD,
        SemanticBone.SHOULDER_L, SemanticBone.SHOULDER_R],
}

# Default priority per layer kind (higher wins).
LAYER_DEFAULT_PRIORITY: Dict[ProceduralLayerKind, int] = {
    ProceduralLayerKind.LOOK_AT: 60,
    ProceduralLayerKind.HEAD_TRACKING: 55,
    ProceduralLayerKind.EYE_TRACKING: 50,
    ProceduralLayerKind.HAND_IK: 70,
    ProceduralLayerKind.FOOT_IK: 80,
    ProceduralLayerKind.PATH_FOLLOW: 40,
    ProceduralLayerKind.OBJECT_GRAB: 75,
    ProceduralLayerKind.SITTING_ALIGNMENT: 65,
    ProceduralLayerKind.TURNING: 45,
    ProceduralLayerKind.IDLE_VARIATION: 10,
}

# Layer kinds that must anchor to a scene anchor (backlog 1: grab/sit).
ANCHOR_REQUIRED_KINDS = {
    ProceduralLayerKind.OBJECT_GRAB,
    ProceduralLayerKind.SITTING_ALIGNMENT,
}


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Recipe: typed layer specs + the ordered layer recipe
# ---------------------------------------------------------------------------
class ProceduralLayerSpec(BaseModel):
    """One procedural layer on top of an animation track (backlog 1/2).

    `input` holds the layer's typed constraints (target offsets, max reach,
    obstacle data, anchor id...). `affected_bones` must stay inside the
    kind's LAYER_OWNERSHIP — a layer never touches bones it does not own.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    layer_id: ProceduralLayerId
    kind: ProceduralLayerKind
    priority: int = Field(default=0, ge=0)
    affected_bones: List[SemanticBone] = Field(default_factory=list)
    input: Dict[str, Any] = Field(default_factory=dict)
    seed: int = Field(default=0, ge=0)
    enabled: bool = True


class ProceduralRecipe(BaseModel):
    """The ordered layer recipe for one track (backlog 2/5).

    Layers are ordered by priority (higher first, ties by layer id) so the
    bake is deterministic. `recipe_hash` covers every layer; a layer change
    deterministically changes the hash (repair scoping, backlog 6).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    recipe_id: ProceduralRecipeId
    track_id: AnimationTrackId
    layers: List[ProceduralLayerSpec] = Field(default_factory=list)
    seed: int = Field(default=1, ge=0)
    compiler_version: str = PROCEDURAL_COMPILER_VERSION
    schema_version: str = PROCEDURAL_RECIPE_SCHEMA_VERSION
    recipe_hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def ordered_layers(self) -> List[ProceduralLayerSpec]:
        """Priority-descending, id-stable layer order (deterministic bake)."""
        return sorted(self.layers, key=lambda l: (-l.priority, str(l.layer_id)))

    def compute_stable_hash(self) -> str:
        payload = json.loads(
            self.model_dump_json(exclude={"recipe_hash", "metadata"}))
        canonical = json.dumps(
            {"schema_version": self.schema_version,
             "compiler_version": self.compiler_version,
             "recipe": json.loads(json.dumps(payload, sort_keys=True,
                                             default=str))},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Baked derived action (backlog 5)
# ---------------------------------------------------------------------------
class LayerBakeResult(BaseModel):
    """Deterministic bake result of one layer (recipe + seed + metric)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    layer_id: ProceduralLayerId
    layer_kind: ProceduralLayerKind
    priority: int = Field(ge=0)
    owned_bones: List[SemanticBone] = Field(default_factory=list)
    seed: int = Field(ge=0)
    metric: Dict[str, Any] = Field(default_factory=dict)
    layer_hash: str = ""

    def compute_stable_hash(self) -> str:
        payload = json.loads(
            self.model_dump_json(exclude={"layer_hash"}))
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class BakedAction(BaseModel):
    """A derived action baked for render; rebuildable from recipe (backlog 5).

    `motion_metrics` aggregates the per-layer metrics (foot sliding, reach,
    joint violations, collisions, balance, boundary drift) so the validator
    and the reviewer see raw measurements. The bake hash is deterministic:
    same recipe + seed + track -> same derived action.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    bake_id: BakedActionId
    track_id: AnimationTrackId
    recipe_id: ProceduralRecipeId
    recipe_hash: str = Field(min_length=1)
    layers: List[LayerBakeResult] = Field(default_factory=list)
    frame_count: int = Field(ge=0)
    fps: int = Field(ge=1)
    motion_metrics: Dict[str, Any] = Field(default_factory=dict)
    compiler_version: str = PROCEDURAL_COMPILER_VERSION
    schema_version: str = PROCEDURAL_BAKE_SCHEMA_VERSION
    bake_hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def compute_stable_hash(self) -> str:
        payload = json.loads(
            self.model_dump_json(exclude={"bake_hash", "metadata"}))
        canonical = json.dumps(
            {"schema_version": self.schema_version,
             "compiler_version": self.compiler_version,
             "bake": json.loads(json.dumps(payload, sort_keys=True,
                                           default=str))},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Findings + validation (fail-closed)
# ---------------------------------------------------------------------------
class ProceduralFindingKind:
    """Typed procedural finding kinds (stage_h §4 backlog 4 / §6 matrix)."""

    OUTSIDE_OWNERSHIP = "OUTSIDE_OWNERSHIP"
    LAYER_CONFLICT = "LAYER_CONFLICT"
    ANCHOR_MISMATCH = "ANCHOR_MISMATCH"
    FOOT_SLIDING = "FOOT_SLIDING"
    HAND_REACH_OUT_OF_BOUNDS = "HAND_REACH_OUT_OF_BOUNDS"
    JOINT_LIMIT_VIOLATED = "JOINT_LIMIT_VIOLATED"
    COLLISION = "COLLISION"
    BALANCE_VIOLATED = "BALANCE_VIOLATED"
    TRANSITION_CONTINUITY_BROKEN = "TRANSITION_CONTINUITY_BROKEN"


class ProceduralFinding(BaseModel):
    """One typed procedural finding (blocking or advisory)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: ProceduralFindingId
    kind: str
    layer_id: str = ""
    detail: str = ""
    blocking: bool = False
    measured: Dict[str, Any] = Field(default_factory=dict)


class ProceduralValidationReport(BaseModel):
    """Aggregate result of procedural validation over recipe/bake."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool = False
    findings: List[ProceduralFinding] = Field(default_factory=list)
    checked_entity_count: int = Field(default=0, ge=0)

    @property
    def blocking_findings(self) -> List[ProceduralFinding]:
        return [f for f in self.findings if f.blocking]

    @property
    def blocking_kinds(self) -> List[str]:
        return sorted({f.kind for f in self.blocking_findings})


class ProceduralValidator:
    """Fail-closed procedural validation (stage_h §4 backlog 2/4).

    Pure math on recipes/bakes; never touches bpy or any engine. The
    compiler always produces valid recipes/bakes; this validator catches
    hand-built/edited ones (defense in depth).
    """

    def validate_recipe(
        self,
        recipe: ProceduralRecipe,
        finding_prefix: str = "pr",
    ) -> ProceduralValidationReport:
        findings: List[ProceduralFinding] = []
        for spec in recipe.layers:
            allowed = set(LAYER_OWNERSHIP.get(spec.kind, []))
            outside = [b for b in spec.affected_bones if b not in allowed]
            if outside:
                findings.append(self._finding(
                    finding_prefix, ProceduralFindingKind.OUTSIDE_OWNERSHIP,
                    spec,
                    f"layer {spec.kind.value} touches bones outside its "
                    f"ownership: {[b.value for b in outside]}",
                    blocking=True,
                    measured={"outside_bones": [b.value for b in outside],
                              "owned": sorted(b.value for b in allowed)}))
            if spec.kind in ANCHOR_REQUIRED_KINDS and not spec.input.get(
                    "anchor_id"):
                findings.append(self._finding(
                    finding_prefix, ProceduralFindingKind.ANCHOR_MISMATCH,
                    spec,
                    f"{spec.kind.value} requires an anchor_id input",
                    blocking=True,
                    measured={"kind": spec.kind.value}))

        # same priority + overlapping bones = two layers fight over the same
        # keyframes; the winner would be arbitrary, so it fails closed.
        # Effective bones = declared affected_bones or the kind's ownership.
        ordered = recipe.ordered_layers()
        for i, a in enumerate(ordered):
            bones_a = (set(a.affected_bones)
                       or set(LAYER_OWNERSHIP.get(a.kind, [])))
            for b in ordered[i + 1:]:
                if a.priority != b.priority:
                    break  # priorities descend; no further ties
                bones_b = (set(b.affected_bones)
                           or set(LAYER_OWNERSHIP.get(b.kind, [])))
                shared = bones_a & bones_b
                if shared:
                    findings.append(self._finding(
                        finding_prefix, ProceduralFindingKind.LAYER_CONFLICT,
                        a,
                        f"layers {a.layer_id} and {b.layer_id} share bones "
                        f"{sorted(b.value for b in shared)} at priority "
                        f"{a.priority}",
                        blocking=True,
                        measured={"other_layer": str(b.layer_id),
                                  "shared_bones": sorted(
                                      b.value for b in shared),
                                  "priority": a.priority}))
        return ProceduralValidationReport(
            ok=not findings, findings=findings,
            checked_entity_count=len(recipe.layers))

    def validate_bake(
        self,
        bake: BakedAction,
        track=None,
        finding_prefix: str = "pr",
    ) -> ProceduralValidationReport:
        findings: List[ProceduralFinding] = []
        for result in bake.layers:
            m = result.metric
            slide = float(m.get("foot_slide_meters", 0.0) or 0.0)
            if slide > FOOT_SLIDING_MAX_M:
                findings.append(self._finding(
                    finding_prefix, ProceduralFindingKind.FOOT_SLIDING,
                    result,
                    f"foot slide {slide:.3f}m > {FOOT_SLIDING_MAX_M:.2f}m",
                    blocking=True,
                    measured={"foot_slide_meters": slide,
                              "max_m": FOOT_SLIDING_MAX_M}))
            reach = float(m.get("reach_meters", 0.0) or 0.0)
            if reach > HAND_REACH_TOLERANCE_M:
                findings.append(self._finding(
                    finding_prefix,
                    ProceduralFindingKind.HAND_REACH_OUT_OF_BOUNDS, result,
                    f"hand reach {reach:.3f}m beyond tolerance "
                    f"{HAND_REACH_TOLERANCE_M:.2f}m",
                    blocking=True,
                    measured={"reach_meters": reach,
                              "tolerance_m": HAND_REACH_TOLERANCE_M}))
            violations = int(m.get("joint_limit_violations", 0) or 0)
            if violations > MAX_JOINT_VIOLATIONS:
                findings.append(self._finding(
                    finding_prefix, ProceduralFindingKind.JOINT_LIMIT_VIOLATED,
                    result,
                    f"{violations} joint limit violations",
                    blocking=True,
                    measured={"joint_limit_violations": violations}))
            collisions = int(m.get("collision_count", 0) or 0)
            if collisions > MAX_COLLISIONS:
                findings.append(self._finding(
                    finding_prefix, ProceduralFindingKind.COLLISION, result,
                    f"{collisions} collisions",
                    blocking=True,
                    measured={"collision_count": collisions}))
            balance = abs(float(m.get("balance_offset_m", 0.0) or 0.0))
            if balance > MAX_BALANCE_OFFSET_M:
                findings.append(self._finding(
                    finding_prefix, ProceduralFindingKind.BALANCE_VIOLATED,
                    result,
                    f"balance offset {balance:.3f}m > "
                    f"{MAX_BALANCE_OFFSET_M:.2f}m",
                    blocking=True,
                    measured={"balance_offset_m": balance,
                              "max_m": MAX_BALANCE_OFFSET_M}))

        drift = int(bake.motion_metrics.get("boundary_drift_frames", 0) or 0)
        if drift > MAX_TRANSITION_DRIFT_FRAMES:
            findings.append(self._finding(
                finding_prefix,
                ProceduralFindingKind.TRANSITION_CONTINUITY_BROKEN, None,
                f"bake boundary drift {drift} frames > "
                f"{MAX_TRANSITION_DRIFT_FRAMES}",
                blocking=True,
                measured={"boundary_drift_frames": drift}))

        return ProceduralValidationReport(
            ok=not findings, findings=findings,
            checked_entity_count=len(bake.layers))

    @staticmethod
    def _finding(prefix: str, kind: str, layer, detail: str, *,
                 blocking: bool, measured: Dict[str, Any]) -> ProceduralFinding:
        return ProceduralFinding(
            finding_id=ProceduralFindingId(f"{prefix}:{kind}"),
            kind=kind,
            layer_id=str(layer.layer_id) if layer is not None else "",
            detail=detail, blocking=blocking, measured=measured)


__all__ = [
    "PROCEDURAL_COMPILER_VERSION",
    "PROCEDURAL_RECIPE_SCHEMA_VERSION",
    "PROCEDURAL_BAKE_SCHEMA_VERSION",
    "FOOT_SLIDING_MAX_M",
    "HAND_REACH_TOLERANCE_M",
    "MAX_BALANCE_OFFSET_M",
    "MAX_JOINT_VIOLATIONS",
    "MAX_COLLISIONS",
    "MAX_TRANSITION_DRIFT_FRAMES",
    "LAYER_OWNERSHIP",
    "LAYER_DEFAULT_PRIORITY",
    "ANCHOR_REQUIRED_KINDS",
    "ProceduralLayerSpec",
    "ProceduralRecipe",
    "LayerBakeResult",
    "BakedAction",
    "ProceduralFindingKind",
    "ProceduralFinding",
    "ProceduralValidationReport",
    "ProceduralValidator",
]
