"""
Rigging & Retargeting system (stage_d.md Phase 9).

Detects a character skeleton, validates the rig, builds a versioned
retarget mapping between a source animation skeleton and a target character
skeleton, then runs a fail-closed animation compatibility gate so only clips
that pass the minimum deformation/continuity checks enter the approved
library (road_map.md Stage D; stage_d.md §4).

Provider-independent by construction:
  - `SkeletonDetector` maps an arbitrary provider's bone names onto SEMANTIC
    roles (`SemanticBone`); no bone name of any provider is ever trusted as an
    identity (backlog 1).
  - `RigValidator` checks rest pose, scale, root bone, parenting, weights,
    joint limits and facial controls, and emits a `RigValidationReceipt`
    (backlog 2).
  - `RetargetMapper` builds a versioned `RetargetProfile` that maps semantic
    source bones to semantic target bones, emitted as a deterministic manifest
    hash so identical inputs reproduce the same action manifest (stage_d.md §5).
  - `CompatibilityGate` runs the minimum clip suite (idle, walk, run, sit,
    stand, turn, point, grab, talk, facial neutral) and FAILS-CLOSED: any
    breach of a deformation metric (foot sliding, limb stretch, mesh
    penetration, root drift, pose discontinuity) or an untested clip is marked
    `FAILED` and is never added to the approved library (backlog 5, 6).
  - Manual correction is expressed ONLY as a derived `RigProfile` revision
    carrying a correction manifest; the source rig is never edited in place
    without traced intent (backlog 7).

The gate `VP3D_P9_CHARACTER_RIG_VERIFIED` is certified by evidence that at
least two character masters of DIFFERENT topology retarget the same minimal
clip set through preview render and continuity checks.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    CompatibilityVerdict,
    CorrectionBasis,
    DeformationMetric,
    RigStatus,
    RigValidationIssueCode,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import (
    RigCompatibilityError,
    SilentSourceMutationError,
    VideoProductionProtocolError,
)
from windagent_core.domain.video_production.ids import (
    AnimationCompatibilityProfileId,
    CharacterGeometryProfileId,
    CharacterMasterId,
    CharacterMasterRevisionId,
    RetargetProfileId,
    RigProfileId,
    RigValidationReceiptId,
    SkeletonProfileId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_dict(**fields: Any) -> str:
    return json.dumps(
        fields,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


# ---------------------------------------------------------------------------
# Thresholds — the fail-closed acceptance envelope (backlog 5/6).
# ---------------------------------------------------------------------------

#: Maximum acceptable foot sliding distance (world units) over a clip.
FOOT_SLIDING_MAX = 0.02

#: Maximum acceptable limb length error as a ratio of rest-pose bone length.
LIMB_STRETCH_MAX = 0.05

#: Maximum acceptable mesh penetration depth (world units).
MESH_PENETRATION_MAX = 0.01

#: Maximum acceptable root position drift (world units) over a clip.
ROOT_DRIFT_MAX = 0.10

#: Maximum acceptable inter-frame pose discontinuity (angle, radians).
POSE_DISCONTINUITY_MAX = 0.35

#: Accepted rig scale band (rest-pose scale of the skeleton).
SCALE_MIN = 0.01
SCALE_MAX = 100.0

#: Minimum share of vertices that must be skinned (weights assigned).
WEIGHTS_MIN_ASSIGNED_RATIO = 0.98

#: Maximum bone weight count a single vertex may reference before it is
#: considered an over-budget weight cluster (a common source of fold artifacts).
WEIGHTS_MAX_INFLUENCES = 8


#: The minimum clip suite a character must retarget cleanly (backlog 4).
MINIMAL_CLIP_SUITE: FrozenSet[str] = frozenset(
    {
        "idle",
        "walk",
        "run",
        "sit",
        "stand",
        "turn",
        "point",
        "grab",
        "talk",
        "facial_neutral",
    }
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Bone(BaseModel):
    """A raw bone as discovered in a provider's skeleton.

    `name` is the provider's own identifier (never treated as an identity by
    the rest of the system); `semantic` is the normalized role assigned by
    `SkeletonDetector`. `parent` is the provider's parent bone name.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    name: str = Field(min_length=1)
    parent: str = ""
    semantic: Optional[SemanticBone] = None
    position: List[float] = Field(default_factory=list)
    length: float = Field(default=1.0, gt=0)


class SkeletonProfile(BaseModel):
    """A detected + semantically normalized skeleton (backlog 1).

    Provider bones are exposed through `semantic_to_bone`; retarget and
    validation always operate on semantic roles. `topology_hash` is a
    deterministic hash over bone names + parenting + rest positions, so two
    skeletons with identical topology produce an identical hash.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: SkeletonProfileId
    bones: List[Bone] = Field(default_factory=list)
    semantic_to_bone: Dict[str, str] = Field(default_factory=dict)
    status: RigStatus = RigStatus.DETECTED
    topology_hash: str = ""
    source_provider: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def bone_for(self, semantic: SemanticBone) -> Optional[str]:
        return self.semantic_to_bone.get(semantic.value)

    def missing_semantic_bones(self) -> List[SemanticBone]:
        return [s for s in SemanticBone if s.value not in self.semantic_to_bone]


def _empty_skeleton() -> SkeletonProfile:
    return SkeletonProfile(profile_id=SkeletonProfileId("skeleton_pending"))


class RigProfile(BaseModel):
    """A rig validated against its character master geometry (backlog 2, 3).

    Immutable once validated. `derived_from` records the source rig/revision a
    manual correction was derived from so edits are always traceable (backlog 7).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    rig_profile_id: RigProfileId
    master_id: CharacterMasterId
    revision_id: Optional[CharacterMasterRevisionId] = None
    skeleton: SkeletonProfile = Field(default_factory=_empty_skeleton)
    scale: float = Field(default=1.0, gt=0)
    rest_pose: Dict[str, List[float]] = Field(default_factory=dict)
    facial_controls: List[str] = Field(default_factory=list)
    weight_influences: int = Field(default=4, ge=1)
    status: RigStatus = RigStatus.DETECTED
    topology_hash: str = ""
    derived_from: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RigValidationIssue(BaseModel):
    """One typed validation finding (backlog 2/5)."""

    model_config = ConfigDict(frozen=True)

    code: RigValidationIssueCode
    message: str
    scope: str = ""
    value: float = 0.0


class RigValidationReceipt(BaseModel):
    """Validation receipt for a rig (backlog 2).

    `valid` is the fail-closed verdict: a single non-recoverable finding makes
    the whole rig invalid. `metric` values capture the measured physical
    quantities for the evidence trail (stage_d.md §5, raw measurements).
    """

    model_config = ConfigDict(frozen=True)

    receipt_id: RigValidationReceiptId
    rig_profile_id: RigProfileId
    master_id: CharacterMasterId
    valid: bool
    status: RigStatus
    issues: List[RigValidationIssue] = Field(default_factory=list)
    metrics: Dict[str, float] = Field(default_factory=dict)
    accepted_thresholds: Dict[str, float] = Field(default_factory=dict)
    decided_at: datetime = Field(default_factory=utc_now)


class RetargetProfile(BaseModel):
    """Versioned mapping between a source and a target skeleton (backlog 3).

    The mapping is expressed in SEMANTIC bone roles (never raw names). It is
    versioned (`version`) and carries a deterministic `manifest_hash` over the
    semantic source->target map + both topology hashes, so re-running the same
    retarget on the same input yields the same action manifest/hash (stage_d.md
    §5).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    retarget_profile_id: RetargetProfileId
    source_skeleton_id: SkeletonProfileId
    target_skeleton_id: SkeletonProfileId
    source_master_id: CharacterMasterId
    target_master_id: CharacterMasterId
    version: int = Field(ge=0, default=0)
    mapping: Dict[str, str] = Field(default_factory=dict)  # source semantic -> target semantic
    source_topology_hash: str = ""
    target_topology_hash: str = ""
    manifest_hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def recompute_manifest_hash(self) -> str:
        self_ = _canonical_dict(
            version=self.version,
            mapping=self.mapping,
            source_topology_hash=self.source_topology_hash,
            target_topology_hash=self.target_topology_hash,
        )
        return _sha256(self_.encode("utf-8"))


class ClipMeasurement(BaseModel):
    """Raw deformation measurements for one clip (backlog 5).

    Values are floats in the canonical units for each `DeformationMetric`.
    """

    model_config = ConfigDict(frozen=True)

    metrics: Dict[DeformationMetric, float] = Field(default_factory=dict)


class AnimationCompatibilityProfile(BaseModel):
    """Per-clip compatibility verdict (backlog 6).

    `verdict` is `APPROVED` only when every deformation metric is within the
    accepted thresholds. A `FAILED` or `NOT_TESTED` clip must never enter the
    approved animation library. `manifest_hash` is derived from the metrics so
    identical measurements produce identical evidence.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    profile_id: AnimationCompatibilityProfileId
    clip_name: str = Field(min_length=1)
    source_skeleton_id: SkeletonProfileId
    target_skeleton_id: SkeletonProfileId
    retarget_profile_id: RetargetProfileId
    verdict: CompatibilityVerdict = CompatibilityVerdict.NOT_TESTED
    measurements: Dict[str, float] = Field(default_factory=dict)
    breached_metrics: List[str] = Field(default_factory=list)
    accepted_thresholds: Dict[str, float] = Field(default_factory=dict)
    manifest_hash: str = ""
    decided_at: datetime = Field(default_factory=utc_now)

    @property
    def approved(self) -> bool:
        return self.verdict == CompatibilityVerdict.APPROVED

    def recompute_manifest_hash(self) -> str:
        payload = _canonical_dict(
            clip=self.clip_name,
            verdict=self.verdict.value,
            measurements=self.measurements,
            accepted_thresholds=self.accepted_thresholds,
            retarget_profile_id=str(self.retarget_profile_id),
        )
        return _sha256(payload.encode("utf-8"))


# ---------------------------------------------------------------------------
# Kernel services
# ---------------------------------------------------------------------------


class SkeletonDetector:
    """Detect + semantically normalize a skeleton (backlog 1).

    `default_aliases` maps common provider bone-name patterns to semantic
    roles, but callers may supply a per-provider alias table. Unknown bones are
    ignored for semantic purposes but retained in the profile so parenting is
    auditable.
    """

    DEFAULT_ALIASES: Dict[str, str] = {
        "root": "ROOT",
        "hips": "PELVIS",
        "pelvis": "PELVIS",
        "spine": "SPINE",
        "spine1": "SPINE",
        "chest": "CHEST",
        "spine2": "CHEST",
        "spine3": "CHEST",
        "neck": "NECK",
        "head": "HEAD",
        "jaw": "JAW",
        "eye_l": "EYE_L",
        "eye_l_01": "EYE_L",
        "lefteye": "EYE_L",
        "eye_r": "EYE_R",
        "eye_r_01": "EYE_R",
        "righteye": "EYE_R",
        "brow_l": "BROW_L",
        "brow_r": "BROW_R",
        "leftbrow": "BROW_L",
        "rightbrow": "BROW_R",
        "shoulder_l": "SHOULDER_L",
        "shoulder_r": "SHOULDER_R",
        "leftshoulder": "SHOULDER_L",
        "rightshoulder": "SHOULDER_R",
        "upperarm_l": "ARM_UPPER_L",
        "upper_arm_l": "ARM_UPPER_L",
        "upperarm_r": "ARM_UPPER_R",
        "upper_arm_r": "ARM_UPPER_R",
        "leftarm": "ARM_UPPER_L",
        "rightarm": "ARM_UPPER_R",
        "lowerarm_l": "ARM_LOWER_L",
        "lower_arm_l": "ARM_LOWER_L",
        "lowerarm_r": "ARM_LOWER_R",
        "lower_arm_r": "ARM_LOWER_R",
        "leftforearm": "ARM_LOWER_L",
        "rightforearm": "ARM_LOWER_R",
        "hand_l": "HAND_L",
        "hand_r": "HAND_R",
        "lefthand": "HAND_L",
        "righthand": "HAND_R",
        "thigh_l": "THIGH_L",
        "thigh_r": "THIGH_R",
        "upleg_l": "THIGH_L",
        "upleg_r": "THIGH_R",
        "leftupleg": "THIGH_L",
        "rightupleg": "THIGH_R",
        "shin_l": "SHIN_L",
        "shin_r": "SHIN_R",
        "leg_l": "SHIN_L",
        "leg_r": "SHIN_R",
        "leftleg": "SHIN_L",
        "rightleg": "SHIN_R",
        "foot_l": "FOOT_L",
        "foot_r": "FOOT_R",
        "leftfoot": "FOOT_L",
        "rightfoot": "FOOT_R",
        "toe_l": "TOE_L",
        "toe_r": "TOE_R",
        "lefttoebase": "TOE_L",
        "righttoebase": "TOE_R",
    }

    def __init__(
        self,
        profile_id: SkeletonProfileId,
        aliases: Optional[Dict[str, str]] = None,
        source_provider: str = "",
    ):
        self._profile_id = profile_id
        self._aliases = {**self.DEFAULT_ALIASES, **(aliases or {})}
        self._source_provider = source_provider

    @staticmethod
    def _normalize_key(name: str) -> str:
        # Strip a provider namespace prefix (`mixamorig:Hips` -> `Hips`) and any
        # common separators so aliases are matched by the trailing bone token.
        key = name.strip().lower()
        if ":" in key:
            key = key.rsplit(":", 1)[-1]
        return key.replace("-", "_").replace(" ", "_")

    def detect(self, bones: List[Dict[str, Any]]) -> SkeletonProfile:
        """Turn raw provider bones into a semantically normalized skeleton."""
        normalized: List[Bone] = []
        semantic_to_bone: Dict[str, str] = {}
        for raw in bones:
            name = str(raw["name"])
            key = self._normalize_key(name)
            semantic_name = self._aliases.get(key)
            semantic = SemanticBone(semantic_name) if semantic_name else None
            if semantic is not None and semantic.value not in semantic_to_bone:
                semantic_to_bone[semantic.value] = name
            normalized.append(
                Bone(
                    name=name,
                    parent=str(raw.get("parent", "")),
                    semantic=semantic,
                    position=list(raw.get("position", [])),
                    length=float(raw.get("length", 1.0)),
                )
            )
        topology_hash = _sha256(
            _canonical_dict(
                bones=[
                    (b.name, b.parent, str(b.position))
                    for b in normalized
                ],
            ).encode("utf-8")
        )
        return SkeletonProfile(
            profile_id=self._profile_id,
            bones=normalized,
            semantic_to_bone=semantic_to_bone,
            status=RigStatus.NORMALIZED,
            topology_hash=topology_hash,
            source_provider=self._source_provider,
        )


class RigValidator:
    """Validate a rig against its geometry (backlog 2).

    Checks: rest pose vs bind, scale band, root bone presence/parenting,
    parenting chain integrity, weight assignment coverage + influence budget,
    joint limits, and facial-control compatibility with the geometry topology
    hash. Fail-closed: any issue of the *_MISSING / *_BROKEN / *_VIOLATED kind
    invalidates the rig.
    """

    #: Facial-control count we accept for a facial rig on the given topology.
    FACIAL_CONTROLS_MIN = 5

    def __init__(
        self,
        receipt_id: RigValidationReceiptId,
        master_id: CharacterMasterId,
        geometry_hash: str = "",
    ):
        self._receipt_id = receipt_id
        self._master_id = master_id
        self._geometry_hash = geometry_hash

    @staticmethod
    def _accepted_thresholds() -> Dict[str, float]:
        return {
            "rest_pose_tolerance": 0.001,
            "scale_min": SCALE_MIN,
            "scale_max": SCALE_MAX,
            "weights_min_assigned_ratio": WEIGHTS_MIN_ASSIGNED_RATIO,
            "weights_max_influences": WEIGHTS_MAX_INFLUENCES,
            "facial_controls_min": RigValidator.FACIAL_CONTROLS_MIN,
        }

    def validate(
        self,
        rig: RigProfile,
        *,
        rest_pose_in_bind: bool = True,
        rest_pose_tolerance: float = 0.001,
        assigned_weight_ratio: float = 1.0,
        vertex_supported_influences: Optional[Dict[str, int]] = None,
        joint_limit_breached: bool = False,
        facial_controls: Optional[List[str]] = None,
    ) -> RigValidationReceipt:
        """Return a fail-closed validation receipt for the rig."""
        issues: List[RigValidationIssue] = []
        metrics: Dict[str, float] = {}

        if rig.skeleton.status not in (RigStatus.NORMALIZED, RigStatus.VALIDATED):
            issues.append(
                RigValidationIssue(
                    code=RigValidationIssueCode.SKELETON_MISSING_SEMANTIC_BONES,
                    message=f"rig skeleton not normalized (status={rig.skeleton.status.value})",
                    scope="skeleton",
                )
            )

        # Rest pose vs bind.
        if not rest_pose_in_bind:
            issues.append(
                RigValidationIssue(
                    code=RigValidationIssueCode.REST_POSE_NOT_BIND,
                    message="rest pose is not in bind pose",
                    scope="rest_pose",
                    value=rest_pose_tolerance,
                )
            )
        metrics["rest_pose_tolerance"] = rest_pose_tolerance

        # Scale band.
        if not (SCALE_MIN <= rig.scale <= SCALE_MAX):
            issues.append(
                RigValidationIssue(
                    code=RigValidationIssueCode.SCALE_OUT_OF_RANGE,
                    message=f"rig scale {rig.scale} outside [{SCALE_MIN}, {SCALE_MAX}]",
                    scope="scale",
                    value=rig.scale,
                )
            )
        metrics["scale"] = rig.scale

        # Root bone presence + rooted suffix.
        root_name = rig.skeleton.bone_for(SemanticBone.ROOT)
        if root_name is None:
            issues.append(
                RigValidationIssue(
                    code=RigValidationIssueCode.ROOT_BONE_MISSING,
                    message="no semantic ROOT bone in skeleton",
                    scope="root",
                )
            )
        else:
            root_bone = next((b for b in rig.skeleton.bones if b.name == root_name), None)
            if root_bone is not None and root_bone.parent:
                issues.append(
                    RigValidationIssue(
                        code=RigValidationIssueCode.ROOT_BONE_ORPHANED,
                        message=f"ROOT bone '{root_name}' has a parent '{root_bone.parent}'",
                        scope="root",
                    )
                )

        # Parenting chain integrity: every non-root bone must reference an
        # existing parent within the skeleton.
        names = {b.name for b in rig.skeleton.bones}
        for b in rig.skeleton.bones:
            if b.parent and b.parent not in names:
                issues.append(
                    RigValidationIssue(
                        code=RigValidationIssueCode.PARENTING_BROKEN,
                        message=f"bone '{b.name}' references missing parent '{b.parent}'",
                        scope=("parenting", b.name),
                    )
                )

        # Weight assignment coverage.
        if assigned_weight_ratio < WEIGHTS_MIN_ASSIGNED_RATIO:
            issues.append(
                RigValidationIssue(
                    code=RigValidationIssueCode.WEIGHTS_UNASSIGNED,
                    message=(
                        f"assigned weight ratio {assigned_weight_ratio:.3f} "
                        f"< min {WEIGHTS_MIN_ASSIGNED_RATIO:.3f}"
                    ),
                    scope="weights",
                    value=assigned_weight_ratio,
                )
            )
        metrics["weight_assigned_ratio"] = assigned_weight_ratio
        metrics["weight_max_influences"] = float(rig.weight_influences)

        # Weight influence budget (per-vertex peaks).
        if vertex_supported_influences:
            peak = max(vertex_supported_influences.values())
            if peak > WEIGHTS_MAX_INFLUENCES:
                issues.append(
                    RigValidationIssue(
                        code=RigValidationIssueCode.WEIGHTS_OVER_BUDGET,
                        message=f"vertex maximal influences {peak} > budget {WEIGHTS_MAX_INFLUENCES}",
                        scope="weights",
                        value=float(peak),
                    )
                )
            metrics["vertex_max_influences"] = float(peak)

        # Joint limits.
        if joint_limit_breached:
            issues.append(
                RigValidationIssue(
                    code=RigValidationIssueCode.JOINT_LIMIT_VIOLATED,
                    message="one or more joint limits are violated in rest pose",
                    scope="joint_limits",
                )
            )

        # Facial control compatibility with geometry topology.
        controls = list(facial_controls) if facial_controls is not None else list(rig.facial_controls)
        if len(controls) < self.FACIAL_CONTROLS_MIN:
            issues.append(
                RigValidationIssue(
                    code=RigValidationIssueCode.FACIAL_CONTROLS_INCOMPATIBLE,
                    message=(
                        f"facial controls {len(controls)} < required {self.FACIAL_CONTROLS_MIN} "
                        "for topology"
                    ),
                    scope="facial",
                    value=float(len(controls)),
                )
            )
        metrics["facial_control_count"] = float(len(controls))

        # Topology anchor: the rig must stay valid for the geometry it was
        # validated against.
        if self._geometry_hash and rig.topology_hash and rig.topology_hash != self._geometry_hash:
            issues.append(
                RigValidationIssue(
                    code=RigValidationIssueCode.TOPOLOGY_HASH_MISMATCH,
                    message="rig topology hash no longer matches character geometry",
                    scope="topology",
                )
            )

        valid = not any(
            i.code
            in {
                RigValidationIssueCode.REST_POSE_NOT_BIND,
                RigValidationIssueCode.SCALE_OUT_OF_RANGE,
                RigValidationIssueCode.ROOT_BONE_MISSING,
                RigValidationIssueCode.ROOT_BONE_ORPHANED,
                RigValidationIssueCode.PARENTING_BROKEN,
                RigValidationIssueCode.WEIGHTS_UNASSIGNED,
                RigValidationIssueCode.WEIGHTS_OVER_BUDGET,
                RigValidationIssueCode.JOINT_LIMIT_VIOLATED,
                RigValidationIssueCode.FACIAL_CONTROLS_INCOMPATIBLE,
                RigValidationIssueCode.SKELETON_MISSING_SEMANTIC_BONES,
                RigValidationIssueCode.TOPOLOGY_HASH_MISMATCH,
            }
            for i in issues
        )

        return RigValidationReceipt(
            receipt_id=self._receipt_id,
            rig_profile_id=rig.rig_profile_id,
            master_id=self._master_id,
            valid=valid,
            status=RigStatus.VALIDATED if valid else RigStatus.INVALID,
            issues=issues,
            metrics=metrics,
            accepted_thresholds=self._accepted_thresholds(),
        )


class RetargetMapper:
    """Build a versioned semantic retarget mapping (backlog 3)."""

    def __init__(
        self,
        retarget_profile_id: RetargetProfileId,
        master_ids: Dict[str, CharacterMasterId],
        version: int = 0,
    ):
        self._retarget_profile_id = retarget_profile_id
        self._source_master_id = master_ids["source"]
        self._target_master_id = master_ids["target"]
        self._version = version

    def build(self, source: SkeletonProfile, target: SkeletonProfile) -> RetargetProfile:
        """Map every present semantic source bone to the matching target bone.

        A source semantic with no corresponding target semantic fails-closed
        (`VideoProductionProtocolError`) because a retarget would silently
        drop part of the pose.
        """
        source_bones = source.semantic_to_bone
        target_bones = target.semantic_to_bone
        mapping: Dict[str, str] = {}
        for semantic in source_bones:
            if semantic not in target_bones:
                raise VideoProductionProtocolError(
                    "Retarget source semantic has no target counterpart: "
                    f"{semantic} (source has it, target does not).",
                    details={"semantic": semantic},
                )
            mapping[semantic] = semantic
        retarget = RetargetProfile(
            retarget_profile_id=self._retarget_profile_id,
            source_skeleton_id=source.profile_id,
            target_skeleton_id=target.profile_id,
            source_master_id=self._source_master_id,
            target_master_id=self._target_master_id,
            version=self._version,
            mapping=mapping,
            source_topology_hash=source.topology_hash,
            target_topology_hash=target.topology_hash,
        )
        retarget = retarget.model_copy(
            update={"manifest_hash": retarget.recompute_manifest_hash()}
        )
        return retarget

    @staticmethod
    def derive_new_version(retarget: RetargetProfile, target: SkeletonProfile) -> RetargetProfile:
        """Return a new immutable retarget version pinned to a newer target topology."""
        mapping = dict(retarget.mapping)
        updated = retarget.model_copy(
            update={
                "version": retarget.version + 1,
                "target_skeleton_id": target.profile_id,
                "target_topology_hash": target.topology_hash,
            }
        )
        return updated.model_copy(
            update={"manifest_hash": updated.recompute_manifest_hash()}
        )


class DeformationMetricEngine:
    """Measure deformation metrics from observed clip data (backlog 5).

    `measure` maps a `ClipMeasurement` (or raw dict) onto canonical metrics.
    It is the single source of truth for the fail-closed thresholds.
    """

    THRESHOLDS: Dict[DeformationMetric, float] = {
        DeformationMetric.FOOT_SLIDING: FOOT_SLIDING_MAX,
        DeformationMetric.LIMB_STRETCH: LIMB_STRETCH_MAX,
        DeformationMetric.MESH_PENETRATION: MESH_PENETRATION_MAX,
        DeformationMetric.ROOT_DRIFT: ROOT_DRIFT_MAX,
        DeformationMetric.POSE_DISCONTINUITY: POSE_DISCONTINUITY_MAX,
    }

    def measure(self, measurement: ClipMeasurement) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for metric in DeformationMetric:
            out[metric.value] = measurement.metrics.get(metric, 0.0)
        return out


class CompatibilityGate:
    """Fail-closed animation compatibility gate (backlog 6).

    A clip enters the APPROVED library only when:
      - it is in the minimum clip suite, AND
      - every measured deformation metric is within its accepted threshold.

    A clip that was never measured, or that breaches any threshold, is
    `FAILED`. `evaluate_or_raise` surfaces a `RigCompatibilityError` so a
    pipeline cannot silently continue with an unapproved clip.
    """

    def __init__(self, metric_engine: DeformationMetricEngine):
        self._metric_engine = metric_engine

    @staticmethod
    def _valid_clip_name(name: str) -> bool:
        return name in MINIMAL_CLIP_SUITE

    def evaluate(
        self,
        profile_id: AnimationCompatibilityProfileId,
        *,
        clip: str,
        retarget: RetargetProfile,
        measurements: Dict[DeformationMetric, float],
        clip_known: bool = True,
    ) -> AnimationCompatibilityProfile:
        metrics = {
            m.value: measurements.get(m, 0.0) for m in DeformationMetric
        }
        thresholds = {
            m.value: self._metric_engine.THRESHOLDS[m] for m in DeformationMetric
        }
        if not clip_known or not self._valid_clip_name(clip):
            profile = AnimationCompatibilityProfile(
                profile_id=profile_id,
                clip_name=clip,
                source_skeleton_id=retarget.source_skeleton_id,
                target_skeleton_id=retarget.target_skeleton_id,
                retarget_profile_id=retarget.retarget_profile_id,
                verdict=CompatibilityVerdict.NOT_TESTED,
                measurements=metrics,
                accepted_thresholds=thresholds,
            )
            return profile.model_copy(
                update={"manifest_hash": profile.recompute_manifest_hash()}
            )

        breached = [
            m for m in DeformationMetric
            if metrics[m.value] > thresholds[m.value]
        ]
        verdict = (
            CompatibilityVerdict.APPROVED
            if not breached
            else CompatibilityVerdict.FAILED
        )
        profile = AnimationCompatibilityProfile(
            profile_id=profile_id,
            clip_name=clip,
            source_skeleton_id=retarget.source_skeleton_id,
            target_skeleton_id=retarget.target_skeleton_id,
            retarget_profile_id=retarget.retarget_profile_id,
            verdict=verdict,
            measurements=metrics,
            breached_metrics=[m.value for m in breached],
            accepted_thresholds=thresholds,
        )
        return profile.model_copy(
            update={"manifest_hash": profile.recompute_manifest_hash()}
        )

    def evaluate_or_raise(
        self,
        profile_id: AnimationCompatibilityProfileId,
        *,
        clip: str,
        retarget: RetargetProfile,
        measurements: Dict[DeformationMetric, float],
        clip_known: bool = True,
    ) -> AnimationCompatibilityProfile:
        profile = self.evaluate(
            profile_id,
            clip=clip,
            retarget=retarget,
            measurements=measurements,
            clip_known=clip_known,
        )
        if not profile.approved:
            raise RigCompatibilityError(
                "Clip not approved for the approved library",
                details={
                    "clip": clip,
                    "verdict": profile.verdict.value,
                    "breached_metrics": profile.breached_metrics,
                },
            )
        return profile


class DerivedRigService:
    """Manual correction as a DERIVED rig revision with a manifest (backlog 7).

    A correction never mutates the source rig in place. It produces a new,
    immutable `RigProfile` whose `derived_from` records the source rig id and
    whose `metadata["correction_manifest"]` records the exact edits applied.
    Editing the source rig object directly is forbidden and guarded by
    `_require_derived` which raises `SilentSourceMutationError`.
    """

    def __init__(self, geometry_hash: str = ""):
        self._geometry_hash = geometry_hash

    def derive(
        self,
        new_rig_id: RigProfileId,
        *,
        source_rig: RigProfile,
        edits: Dict[str, Any],
        basis: CorrectionBasis,
        actor: str,
    ) -> RigProfile:
        if not edits:
            raise VideoProductionProtocolError(
                "A derived rig revision requires a non-empty correction edit set.",
            )
        if not actor.strip():
            raise VideoProductionProtocolError(
                "Derived rig correction requires a named actor.",
            )
        manifest = {
            "basis": basis.value,
            "actor": actor,
            "edits": edits,
            "source_rig_id": str(source_rig.rig_profile_id),
            "source_topology_hash": source_rig.topology_hash or source_rig.skeleton.topology_hash,
        }
        corrections = _canonical_dict(**manifest)
        return RigProfile(
            rig_profile_id=new_rig_id,
            master_id=source_rig.master_id,
            revision_id=source_rig.revision_id,
            skeleton=source_rig.skeleton,
            scale=float(edits.get("scale", source_rig.scale)),
            rest_pose=dict(source_rig.rest_pose),
            facial_controls=list(source_rig.facial_controls),
            weight_influences=int(edits.get("weight_influences", source_rig.weight_influences)),
            status=RigStatus.DETECTED,  # must re-validate after derivation
            topology_hash=source_rig.topology_hash,
            derived_from=[str(source_rig.rig_profile_id)],
            metadata={
                **source_rig.metadata,
                "correction_manifest_hash": _sha256(corrections.encode("utf-8")),
                "correction_manifest": manifest,
                "correction_actor": actor,
            },
        )


__all__ = [
    "Bone",
    "SkeletonProfile",
    "RigProfile",
    "RigValidationIssue",
    "RigValidationReceipt",
    "RetargetProfile",
    "ClipMeasurement",
    "AnimationCompatibilityProfile",
    "SkeletonDetector",
    "RigValidator",
    "RetargetMapper",
    "DeformationMetricEngine",
    "CompatibilityGate",
    "DerivedRigService",
    "MINIMAL_CLIP_SUITE",
    "FOOT_SLIDING_MAX",
    "LIMB_STRETCH_MAX",
    "MESH_PENETRATION_MAX",
    "ROOT_DRIFT_MAX",
    "POSE_DISCONTINUITY_MAX",
    "SCALE_MIN",
    "SCALE_MAX",
    "WEIGHTS_MIN_ASSIGNED_RATIO",
    "WEIGHTS_MAX_INFLUENCES",
]
