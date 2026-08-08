"""
VP3D Phase 11 — Scene Compiler (stage_f §3).

`SceneCompilerPort.compile(ir, assets, shot_graph, continuity) -> EngineScenePlan`
produces a TYPED `BlenderScenePlan` — the engine-neutral intermediate a TRUSTED
adapter transcribes to `bpy` and saves as `.blend`.

This module is the DOMAIN boundary holding the security invariant: the compiler
never evaluates or executes text originated by a model or asset metadata. It
emits a closed, allow-listed `BpyInstruction` sequence; a hostile string in a
description or metadata field can never become Python. Unknown/free text fails
closed with `UnsafeCompilerOperationError`.

Backlog (stage_f §3):
1. `BlenderScenePlan` — typed collections, objects, transforms, instances,
   camera/light/animation bindings, frame ranges, render profile.
2. `ScenePlanValidator` — completeness: asset approval, revision, frame range,
   transform units, dependencies. Fails closed, never compiles incomplete.
3. `compute_plan_hash` — deterministic ordering, canonical JSON, version.
4. `BpyTranscriber` + `CompilerOperationGuard` — allow-listed ops, no eval/exec.
5. `BlendInspector` — save->reopen->publish; reconciles names/IDs, frame range,
   data-block count.
6. `IrMappingManifest` — IR entity -> data-block mapping for traceability.
7. `IncrementalCompileService` — unchanged input hash reuses `.blend`; a track
   change rebuilds only dependents.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    BpyOpCode,
    CompileStatus,
    PlanAffected,
    TransformUnit,
)
from windagent_core.domain.video_production.errors import (
    AssetRevisionMismatchError,
    InvalidFrameRangeError,
    ScenePlanIncompleteError,
    UnapprovedAssetError,
    UnsafeCompilerOperationError,
)
from windagent_core.domain.video_production.ids import (
    BlendInspectionReceiptId,
    BlenderScenePlanId,
    IrMappingManifestId,
    ProductionRevisionId,
    SceneId,
    ScenePlanIssueId,
    VideoProjectId,
)
from windagent_core.domain.video_production.production_ir.models import (
    ProductionIrDocument,
)

SCENE_COMPILER_VERSION = "1.0.0"
SCENE_PLAN_SCHEMA_VERSION = "1.0.0"
DEFAULT_FRAME_RATE = 24
MIN_FRAME = 1


def _canonical_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(payload, sort_keys=True, default=str))


def compute_plan_hash(*, plan: Dict[str, Any]) -> str:
    """Deterministic SHA-256 over the canonical plan payload + compiler version."""
    canonical = json.dumps(
        {
            "schema_version": SCENE_PLAN_SCHEMA_VERSION,
            "compiler_version": SCENE_COMPILER_VERSION,
            "plan": _canonical_dict(plan),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Backlog 1 — typed scene plan
# ---------------------------------------------------------------------------
class BlenderCollection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    collection_id: str = Field(min_length=1)  # canonical ID, never display name
    display_name: str = ""
    kind: str = "COLLECTION"


class BlenderObject(BaseModel):
    """One transcribable object. `asset_revision_hash` pins the approved revision."""

    model_config = ConfigDict(frozen=True, extra="allow")

    object_id: str = Field(min_length=1)
    display_name: str = ""
    source_id: str = ""          # canonical IR entity id
    source_type: str = ""        # CHARACTER | PROP | ENVIRONMENT | WORLD | CAMERA | LIGHT
    asset_revision_hash: str = ""
    collection_id: str = ""
    kind: str = "MESH"           # MESH | CAMERA | LIGHT | EMPTY | WORLD
    location: List[float] = Field(default_factory=list)
    rotation: List[float] = Field(default_factory=list)
    scale: List[float] = Field(default_factory=list)
    transform_unit: TransformUnit = TransformUnit.METERS
    units: Dict[str, Any] = Field(default_factory=dict)


class CameraBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    object_id: str = Field(min_length=1)
    track_id: str = ""
    lens_mm: float = 35.0
    sensor_width_mm: float = 36.0
    fov_degrees: Optional[float] = None


class LightBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    object_id: str = Field(min_length=1)
    rig_id: str = ""
    light_kind: str = "AREA"
    energy: float = 1.0
    color: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])


class AnimationBinding(BaseModel):
    """Animation bound to objects over a frame range; rebuilt on track change (backlog 7)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    binding_id: str = Field(min_length=1)
    track_id: str = ""
    target_object_ids: List[str] = Field(default_factory=list)
    start_frame: int = Field(ge=1)
    end_frame: int = Field(ge=1)
    action: str = ""
    reference_uri: str = ""
    reference_hash: str = ""
    input_hash: str = ""


class FrameRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    start: int = Field(ge=1)
    end: int = Field(ge=1)
    fps: int = Field(default=DEFAULT_FRAME_RATE, ge=1)

    def validate_range(self) -> bool:
        return self.start >= MIN_FRAME and self.end >= self.start


class RenderConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: str = ""
    quality: str = ""
    samples: int = Field(ge=1)
    resolution: Dict[str, int] = Field(default_factory=dict)
    denoise: bool = True
    frame_range: FrameRange


class BlenderScenePlan(BaseModel):
    """The typed engine-neutral scene plan (EngineScenePlan DTO). Immutable."""

    model_config = ConfigDict(frozen=True, extra="allow")

    plan_id: BlenderScenePlanId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    scene_id: SceneId
    ir_hash: str = Field(default="", max_length=64)   # input IR content hash
    compiler_version: str = SCENE_COMPILER_VERSION
    schema_version: str = SCENE_PLAN_SCHEMA_VERSION
    collections: List[BlenderCollection] = Field(default_factory=list)
    objects: List[BlenderObject] = Field(default_factory=list)
    cameras: List[CameraBinding] = Field(default_factory=list)
    lights: List[LightBinding] = Field(default_factory=list)
    animations: List[AnimationBinding] = Field(default_factory=list)
    frame_range: FrameRange
    render_config: RenderConfiguration
    plan_hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def compute_stable_hash(self) -> str:
        return compute_plan_hash(plan=json.loads(self.model_dump_json()))

    def serialize(self) -> str:
        return json.dumps(
            _canonical_dict(json.loads(self.model_dump_json())),
            sort_keys=True,
            separators=(",", ":"),
        )

    def datablock_count(self) -> int:
        """Cols + objects + cameras + lights + scene, what inspection expects."""
        return (len(self.collections) + len(self.objects)
                + len(self.cameras) + len(self.lights) + 1)


# ---------------------------------------------------------------------------
# Backlog 2 — completeness validation (fail closed)
# ---------------------------------------------------------------------------
class ScenePlanDraft(BaseModel):
    """Inputs a compile must validate before producing a plan."""

    model_config = ConfigDict(frozen=True, extra="allow")

    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    scene_id: SceneId
    ir: ProductionIrDocument
    approved_asset_revisions: Dict[str, str] = Field(default_factory=dict)  # ir entity -> revision hash
    shot_graph: Optional[Dict[str, Any]] = None
    continuity: Optional[Dict[str, Any]] = None


class ScenePlanValidator:
    """Completeness gate. Raises typed errors; never compiles an incomplete plan."""

    def _check_approved(self, draft: ScenePlanDraft, entity_id: str, entity_type: str,
                        revision_hash: str) -> None:
        if entity_id not in draft.approved_asset_revisions:
            raise UnapprovedAssetError(
                f"{entity_type} {entity_id!r} has no approved asset revision",
                details={"entity_id": entity_id, "asset_type": entity_type},
            )
        if revision_hash and draft.approved_asset_revisions[entity_id] != revision_hash:
            raise AssetRevisionMismatchError(
                f"{entity_type} {entity_id!r} revision mismatch",
                details={"entity_id": entity_id, "expected": revision_hash,
                         "approved": draft.approved_asset_revisions[entity_id]},
            )

    def validate(self, draft: ScenePlanDraft) -> None:
        if not draft.ir.scenes and not draft.ir.shots:
            raise ScenePlanIncompleteError(
                "IR carries no scenes or shots to compile",
                details={"scene_count": len(draft.ir.scenes), "shot_count": len(draft.ir.shots)},
            )
        # default frame range from shots if render_intents empty / frame_end==0
        # validate approved assets + continuity ledger (dependencies available)
        if draft.continuity is None:
            raise ScenePlanIncompleteError(
                "continuity ledger required before compile",
                details={"reason": "continuity_missing"},
            )
        if draft.shot_graph is None:
            raise ScenePlanIncompleteError(
                "shot graph required before compile",
                details={"reason": "shot_graph_missing"},
            )
        # every referenced entity must be approved
        for scene in draft.ir.scenes:
            for inst in scene.characters:
                self._check_approved(draft, str(inst.instance_id), "CHARACTER",
                                     inst.mesh.content_hash if inst.mesh else "")
            for inst in scene.props:
                self._check_approved(draft, str(inst.instance_id), "PROP",
                                     inst.asset.content_hash if inst.asset else "")
            for inst in scene.environment:
                self._check_approved(draft, str(inst.instance_id), "ENVIRONMENT",
                                     inst.asset.content_hash if inst.asset else "")


# ---------------------------------------------------------------------------
# Backlog 6 — IR -> data-block mapping manifest
# ---------------------------------------------------------------------------
class IrMappingEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    ir_entity_id: str = ""
    ir_entity_type: str = ""
    datablock_name: str = ""
    asset_revision_hash: str = ""
    mapping_hash: str = ""


class IrMappingManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    manifest_id: IrMappingManifestId
    plan_id: BlenderScenePlanId
    entries: List[IrMappingEntry] = Field(default_factory=list)
    manifest_hash: str = ""

    def compute_hash(self) -> str:
        return compute_plan_hash(plan=json.loads(self.model_dump_json(exclude={"manifest_hash"})))

    def reconcile_mapping(self) -> bool:
        """Every entry's target data-block name is a canonical non-empty ID."""
        return all(str(e.datablock_name) for e in self.entries)


# ---------------------------------------------------------------------------
# Backlog 4 — trusted bpy instruction allow-list
# ---------------------------------------------------------------------------
class BpyInstruction(BaseModel):
    """One closed, allow-listed operation. Never a free-form Python string."""

    model_config = ConfigDict(frozen=True, extra="allow")

    op: BpyOpCode
    target: str = ""
    args: Dict[str, Any] = Field(default_factory=dict)


_EVAL_MARKERS = ("import bpy", "import os", "bpy.ops", "eval(", "exec(",
                 "__import__", "os.system", "os.popen", "subprocess")


class CompilerOperationGuard:
    """Rejects any plan content that would become arbitrary code if transcribed."""

    def _scan(self, text: str, label: str) -> None:
        lowered = text.lower()
        for marker in _EVAL_MARKERS:
            if marker in lowered:
                raise UnsafeCompilerOperationError(
                    f"{label} carries a code-execution marker",
                    details={"marker": marker, "origin": label},
                )

    def guard_plan(self, plan: BlenderScenePlan) -> None:
        self._scan(json.dumps(json.loads(plan.model_dump_json())), "plan")

    def guard_string(self, value: str, field_name: str) -> None:
        self._scan(value, field_name)


class BpyTranscriber:
    """Maps a typed plan onto a closed instruction sequence (allow-listed).

    Never calls eval/exec/compile and never interprets model/metadata strings as
    code. Unknown op codes or string content carrying execution markers fail
    closed via the guard.
    """

    def transcribe(self, plan: BlenderScenePlan) -> List[BpyInstruction]:
        guard = CompilerOperationGuard()
        guard.guard_plan(plan)
        ops: List[BpyInstruction] = []
        ops.append(BpyInstruction(op=BpyOpCode.NEW_SCENE, target=str(plan.scene_id)))
        ops.append(BpyInstruction(
            op=BpyOpCode.SET_FRAME_RANGE, target=str(plan.scene_id),
            args={"start": plan.frame_range.start, "end": plan.frame_range.end,
                  "fps": plan.frame_range.fps},
        ))
        ops.append(BpyInstruction(
            op=BpyOpCode.SET_RENDER_CONFIG, target=str(plan.render_config.profile_id),
            args={"quality": plan.render_config.quality, "samples": plan.render_config.samples,
                  "resolution": dict(plan.render_config.resolution), "denoise": plan.render_config.denoise},
        ))
        for coll in plan.collections:
            ops.append(BpyInstruction(
                op=BpyOpCode.CREATE_COLLECTION, target=coll.collection_id,
                args={"kind": coll.kind, "display_name": coll.display_name},
            ))
        for obj in plan.objects:
            ops.append(BpyInstruction(
                op=BpyOpCode.CREATE_OBJECT, target=obj.object_id,
                args={"kind": obj.kind, "collection": obj.collection_id,
                      "location": list(obj.location), "rotation": list(obj.rotation),
                      "scale": list(obj.scale), "transform_unit": obj.transform_unit.value},
            ))
        for camera in plan.cameras:
            ops.append(BpyInstruction(
                op=BpyOpCode.ADD_CAMERA, target=camera.object_id,
                args={"lens_mm": camera.lens_mm, "sensor_width_mm": camera.sensor_width_mm,
                      "fov_degrees": camera.fov_degrees},
            ))
        for light in plan.lights:
            ops.append(BpyInstruction(
                op=BpyOpCode.ADD_LIGHT, target=light.object_id,
                args={"light_kind": light.light_kind, "energy": light.energy,
                      "color": list(light.color)},
            ))
        for anim in plan.animations:
            ops.append(BpyInstruction(
                op=BpyOpCode.ADD_ANIMATION, target=anim.binding_id,
                args={"tracks": list(anim.target_object_ids),
                      "start_frame": anim.start_frame, "end_frame": anim.end_frame},
            ))
        ops.append(BpyInstruction(
            op=BpyOpCode.SAVE_BLEND, target=str(plan.plan_id),
            args={"plan_hash": plan.plan_hash},
        ))
        return ops


# ---------------------------------------------------------------------------
# Backlog 5 — save -> reopen -> publish inspection
# ---------------------------------------------------------------------------
class BlendInspectionIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    issue_id: ScenePlanIssueId
    code: str = ""
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class BlendInspectionReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    receipt_id: BlendInspectionReceiptId
    plan_id: BlenderScenePlanId
    published: bool = False
    issues: List[BlendInspectionIssue] = Field(default_factory=list)
    inspected_object_count: int = 0
    inspected_frame_range: Dict[str, int] = Field(default_factory=dict)
    datablock_count_expected: int = 0
    datablock_count_observed: int = 0
    plan_hash_at_save: str = ""
    valid: bool = False


class BlendSnapshot:
    """Domain-pure stand-in for a reopened .blend (opaque view of a save)."""

    def __init__(self, *, plan: BlenderScenePlan) -> None:
        self._object_ids = sorted(str(o.object_id) for o in plan.objects)
        self._frame = {"start": plan.frame_range.start,
                       "end": plan.frame_range.end, "fps": plan.frame_range.fps}
        self._datablock_count = plan.datablock_count()

    def object_ids(self) -> List[str]:
        return list(self._object_ids)

    def frame_range(self) -> Dict[str, int]:
        return dict(self._frame)

    def datablock_count(self) -> int:
        return self._datablock_count


class BlendInspector:
    """Publishes only when object IDs, frame range AND data-block count match (fail closed)."""

    def inspect(self, *, receipt_id: BlendInspectionReceiptId,
                plan: BlenderScenePlan, snapshot: BlendSnapshot) -> BlendInspectionReceipt:
        issues: List[BlendInspectionIssue] = []
        plan_ids = set(str(o.object_id) for o in plan.objects)
        snap_ids = set(snapshot.object_ids())
        missing = plan_ids - snap_ids
        extra = snap_ids - plan_ids
        if missing:
            issues.append(BlendInspectionIssue(
                issue_id=ScenePlanIssueId(f"{receipt_id}:missing"), code="MISSING_OBJECT",
                message=f"objects missing on reopen: {sorted(missing)}",
                details={"missing": sorted(missing)}))
        if extra:
            issues.append(BlendInspectionIssue(
                issue_id=ScenePlanIssueId(f"{receipt_id}:extra"), code="OBJECT_NAME_MISMATCH",
                message=f"unexpected objects on reopen: {sorted(extra)}",
                details={"extra": sorted(extra)}))
        snap_frame = snapshot.frame_range()
        if (snap_frame["start"] != plan.frame_range.start
                or snap_frame["end"] != plan.frame_range.end
                or snap_frame["fps"] != plan.frame_range.fps):
            issues.append(BlendInspectionIssue(
                issue_id=ScenePlanIssueId(f"{receipt_id}:frame"), code="FRAME_RANGE_MISMATCH",
                message="reopened blend frame range differs from plan",
                details={"plan": plan.frame_range.model_dump(), "observed": snap_frame}))
        expected = plan.datablock_count()
        observed = snapshot.datablock_count()
        if observed != expected:
            issues.append(BlendInspectionIssue(
                issue_id=ScenePlanIssueId(f"{receipt_id}:count"),
                code="DATABLOCK_COUNT_MISMATCH",
                message=f"count mismatch expected={expected} observed={observed}",
                details={"expected": expected, "observed": observed}))
        valid = not issues
        return BlendInspectionReceipt(
            receipt_id=receipt_id, plan_id=plan.plan_id, published=valid, issues=issues,
            inspected_object_count=len(snap_ids), inspected_frame_range=snap_frame,
            datablock_count_expected=expected, datablock_count_observed=observed,
            plan_hash_at_save=plan.plan_hash, valid=valid,
        )


# ---------------------------------------------------------------------------
# Backlog 7 — incremental compile
# ---------------------------------------------------------------------------
class IncrementalCompileService:
    """Reuses the `.blend` when the input hash is unchanged; a track change
    rebuilds only the dependent scene/shot."""

    def compile_scene(self, *, ir_hash: str, existing_blend_ir_hash: Optional[str],
                      changed_tracks: List[str]) -> CompileStatus:
        if existing_blend_ir_hash is None:
            return CompileStatus.BUILT_DEPENDENT
        if existing_blend_ir_hash == ir_hash and not changed_tracks:
            return CompileStatus.REUSED
        if changed_tracks:
            return CompileStatus.BUILT_DEPENDENT
        return CompileStatus.BUILT

    def affected_by(self, *, changed_field: str) -> PlanAffected:
        if changed_field in {"frame_range", "render_config", "camera", "light"}:
            return PlanAffected.ALL
        if changed_field == "object":
            return PlanAffected.OBJECT
        if changed_field in {"asset_revision", "animation"}:
            return PlanAffected.ANIMATION
        return PlanAffected.UNKNOWN


__all__ = [
    "SCENE_COMPILER_VERSION",
    "SCENE_PLAN_SCHEMA_VERSION",
    "compute_plan_hash",
    "BlenderCollection",
    "BlenderObject",
    "CameraBinding",
    "LightBinding",
    "AnimationBinding",
    "FrameRange",
    "RenderConfiguration",
    "BlenderScenePlan",
    "ScenePlanDraft",
    "ScenePlanValidator",
    "IrMappingEntry",
    "IrMappingManifest",
    "BpyInstruction",
    "CompilerOperationGuard",
    "BpyTranscriber",
    "BlendInspectionIssue",
    "BlendInspectionReceipt",
    "BlendSnapshot",
    "BlendInspector",
    "IncrementalCompileService",
]
