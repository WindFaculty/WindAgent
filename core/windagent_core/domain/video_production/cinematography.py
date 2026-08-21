"""
Stage G Cinematography domain (VP3D Phase 13 — Blender Camera Compiler).

Frozen, engine-neutral DTOs for camera intent and the compiled camera rig
plan. No ``bpy``, no provider SDK, no transport object ever appears here: the
compiler layer (`intelligence/windagent_intelligence/video/camera/`) maps the
Director's shot intent onto these typed objects, and the Blender adapter (tools
layer) transcribes them. Core stays tools/intelligence-neutral.

Semantics (stage_g §3):
- `CameraIntent` is what the Director/shots mean; `CameraRigPlan` is the
  deterministic, versioned rig the engine can realize (lens, sensor, DOF,
  focus target, look-at, path/easing, safe framing, frame range).
- Movement (`CameraMovement`) maps onto versioned rig primitives resolved by
  the adapter registry — this module stays primitive-agnostic.
- Validation is fail-closed and proxy-based: the 180-degree rule, head/look
  room, subject visibility, lens bounds, path continuity and motion speed are
  checked here with pinhole projection + AABB proxies; exact mesh occlusion is
  sampled by the occlusion preflight (intelligence layer).
- `CameraOverride` pins a track revision so a manual camera placement at
  Stage N is respected by the compiler and never silently overridden by a
  drifted track.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    CameraAngle,
    CameraMovement,
    CameraSide,
    EasingKind,
    ScreenDirection,
)
from windagent_core.domain.video_production.ids import (
    CameraFindingId,
    CameraIntentId,
    CameraOverrideId,
    CameraPathManifestId,  # noqa: F401  # re-exported via domain package
    CameraRigPlanId,
    DialogueLineId,
    SceneId,
    ShotId,
)
from windagent_core.domain.video_production.set_dressing import (
    Aabb,
    ForbiddenVolume,
    Vec3,
)

CAMERA_COMPILER_VERSION = "1.0.0"
CAMERA_RIG_SCHEMA_VERSION = "1.0.0"

# Proxy validation thresholds (stage_g §4). Raw measurements are surfaced in
# receipts so evidence shows the numbers, not just pass/fail.
LENS_FOCAL_MIN_MM = 8.0
LENS_FOCAL_MAX_MM = 200.0
LENS_SENSOR_MIN_MM = 1.0
LENS_SENSOR_MAX_MM = 100.0
MAX_PATH_JUMP_M = 5.0          # max displacement between consecutive keyframes
MAX_MOTION_SPEED_MPS = 10.0    # path length / shot duration
MIN_SHOT_DURATION_S = 0.25     # shorter than this = "camera movement quá ngắn"
DEFAULT_UP = Vec3(x=0.0, y=0.0, z=1.0)


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def segment_hits_aabb(start: Vec3, end: Vec3, volume: Aabb) -> bool:
    """Liang-Barsky clip: does the segment camera->subject cross the AABB?

    Cheap proxy for occlusion/collision preflight (stage_g §3 backlog 5).
    Exact mesh intersection is deferred to the blender compiler/inspector.
    """
    dx = end.x - start.x
    dy = end.y - start.y
    dz = end.z - start.z
    p = [-dx, dx, -dy, dy, -dz, dz]
    q = [
        start.x - volume.min.x, volume.max.x - start.x,
        start.y - volume.min.y, volume.max.y - start.y,
        start.z - volume.min.z, volume.max.z - start.z,
    ]
    tmin, tmax = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0.0:
                return False
            continue
        t = qi / pi
        if pi < 0.0:
            if t > tmax:
                return False
            tmin = max(tmin, t)
        else:
            if t < tmin:
                return False
            tmax = min(tmax, t)
    return tmin <= tmax


# ---------------------------------------------------------------------------
# Lens / focus / framing / path
# ---------------------------------------------------------------------------
class LensProfile(BaseModel):
    """Physical lens + sensor configuration (pinhole model)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    focal_mm: float = Field(ge=1.0)
    sensor_width_mm: float = Field(default=36.0, ge=1.0)
    aspect_ratio: float = Field(default=16.0 / 9.0, gt=0.1)
    aperture_fstop: float = Field(default=2.8, gt=0.0)

    def horizontal_fov_rad(self) -> float:
        return 2.0 * math.atan(self.sensor_width_mm / (2.0 * self.focal_mm))

    def vertical_fov_rad(self) -> float:
        return 2.0 * math.atan(
            math.tan(self.horizontal_fov_rad() / 2.0) / self.aspect_ratio
        )


class FocusPlan(BaseModel):
    """Focus target + depth-of-field band (stage_g §3: DOF, focus target)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    focus_target: str = ""      # subject id, or "distance" for a pure distance
    focus_distance_m: float = Field(ge=0.0)
    dof_near_m: float = Field(ge=0.0)
    dof_far_m: float = Field(ge=0.0)

    def valid(self) -> bool:
        return (
            self.focus_distance_m > 0.0
            and self.dof_near_m <= self.focus_distance_m <= self.dof_far_m
        )


class FramingConstraint(BaseModel):
    """Safe framing + room ratios (stage_g §3: safe framing)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    head_room_ratio: float = Field(default=0.12, ge=0.0, lt=0.5)
    look_room_ratio: float = Field(default=0.20, ge=0.0, lt=0.5)
    safe_margin: float = Field(default=0.05, ge=0.0, lt=0.25)
    subject_height_m: float = Field(default=1.6, ge=0.05)


class DialogueTiming(BaseModel):
    """A dialogue line's second range; must fit inside the shot (backlog 3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    line_id: DialogueLineId
    start_second: float = Field(ge=0.0)
    end_second: float = Field(gt=0.0)


class CameraKeyframe(BaseModel):
    """One path keyframe: camera pose + easing to the next keyframe."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame: int = Field(ge=0)
    position: Vec3
    look_at: Vec3 = Field(default_factory=Vec3)
    easing: EasingKind = EasingKind.LINEAR


class CameraPath(BaseModel):
    """Ordered camera path with easing (stage_g §3: camera path)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    keyframes: List[CameraKeyframe] = Field(default_factory=list)

    def sorted_keyframes(self) -> List[CameraKeyframe]:
        return sorted(self.keyframes, key=lambda k: k.frame)

    def length_m(self) -> float:
        keys = self.sorted_keyframes()
        if len(keys) < 2:
            return 0.0
        total = 0.0
        for a, b in zip(keys, keys[1:]):
            total += math.dist(
                a.position.as_tuple(), b.position.as_tuple()
            )
        return total

    def max_jump_m(self) -> float:
        keys = self.sorted_keyframes()
        if len(keys) < 2:
            return 0.0
        return max(
            math.dist(a.position.as_tuple(), b.position.as_tuple())
            for a, b in zip(keys, keys[1:])
        )

    def sample(self, t01: float) -> "CameraPose":
        """Linear interpolation along the path at t in [0,1]."""
        keys = self.sorted_keyframes()
        if not keys:
            return CameraPose(position=Vec3(), look_at=Vec3())
        if len(keys) == 1:
            k = keys[0]
            return CameraPose(position=k.position, look_at=k.look_at)
        t01 = max(0.0, min(1.0, t01))
        seg_total = self.length_m()
        if seg_total <= 0.0:
            return CameraPose(position=keys[0].position, look_at=keys[0].look_at)
        target = t01 * seg_total
        acc = 0.0
        for a, b in zip(keys, keys[1:]):
            seg_len = math.dist(a.position.as_tuple(), b.position.as_tuple())
            if acc + seg_len >= target or seg_len <= 0.0:
                if seg_len <= 0.0:
                    return CameraPose(position=b.position, look_at=b.look_at)
                u = (target - acc) / seg_len
                return CameraPose(
                    position=Vec3(
                        x=a.position.x + (b.position.x - a.position.x) * u,
                        y=a.position.y + (b.position.y - a.position.y) * u,
                        z=a.position.z + (b.position.z - a.position.z) * u,
                    ),
                    look_at=Vec3(
                        x=a.look_at.x + (b.look_at.x - a.look_at.x) * u,
                        y=a.look_at.y + (b.look_at.y - a.look_at.y) * u,
                        z=a.look_at.z + (b.look_at.z - a.look_at.z) * u,
                    ),
                )
            acc += seg_len
        last = keys[-1]
        return CameraPose(position=last.position, look_at=last.look_at)


class CameraPose(BaseModel):
    """Resolved camera position + look-at at one moment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: Vec3
    look_at: Vec3 = Field(default_factory=Vec3)


class ScreenProjection(BaseModel):
    """Normalized pinhole projection of a point: x,y in [-1,1], depth > 0."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: float
    y: float
    depth: float
    visible: bool


def project_to_screen(
    point: Vec3,
    pose: CameraPose,
    lens: LensProfile,
    up: Vec3 = DEFAULT_UP,
) -> ScreenProjection:
    """Project a world point onto the camera's normalized screen plane.

    x/y are normalized to the frame (tan-half-fov units); |x|,|y| < 1 is
    inside the frustum. Shared by the validator (framing checks) and the
    playblast manifest (sampled framing report).
    """
    forward = _normalize(_sub(pose.look_at, pose.position))
    right = _normalize(_cross(forward, up))
    upv = _cross(right, forward)
    v = _sub(point, pose.position)
    depth = _dot(v, forward)
    if depth <= 0.0:
        return ScreenProjection(x=0.0, y=0.0, depth=depth, visible=False)
    x = _dot(v, right) / depth / math.tan(lens.horizontal_fov_rad() / 2.0)
    y = _dot(v, upv) / depth / math.tan(lens.vertical_fov_rad() / 2.0)
    return ScreenProjection(x=x, y=y, depth=depth, visible=abs(x) <= 1.0 and abs(y) <= 1.0)


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(x=a.x - b.x, y=a.y - b.y, z=a.z - b.z)


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        x=a.y * b.z - a.z * b.y,
        y=a.z * b.x - a.x * b.z,
        z=a.x * b.y - a.y * b.x,
    )


def _normalize(v: Vec3) -> Vec3:
    length = math.sqrt(_dot(v, v))
    if length < 1e-12:
        return Vec3(x=0.0, y=1.0, z=0.0)
    return Vec3(x=v.x / length, y=v.y / length, z=v.z / length)


# ---------------------------------------------------------------------------
# Intent / override / compiled rig plan
# ---------------------------------------------------------------------------
class CameraIntent(BaseModel):
    """What the Director means for one shot's camera (stage_g §3 domain mở rộng)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    intent_id: CameraIntentId
    shot_id: ShotId
    scene_id: SceneId
    movement: CameraMovement = CameraMovement.STATIC
    angle: CameraAngle = CameraAngle.EYE_LEVEL
    side: CameraSide = CameraSide.NEUTRAL
    screen_direction: ScreenDirection = ScreenDirection.NEUTRAL
    lens: LensProfile
    focus: FocusPlan
    framing: FramingConstraint = Field(default_factory=FramingConstraint)
    path: CameraPath = Field(default_factory=CameraPath)
    duration_seconds: float = Field(gt=0.0)
    fps: int = Field(default=24, ge=1)
    dialogue_timing: List[DialogueTiming] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CameraOverride(BaseModel):
    """Manual camera override (Stage N) pinning a track revision.

    The compiler respects the pin: when the override is active and the track's
    current revision differs from `pinned_track_revision`, compilation fails
    closed (backlog 7) — a drifted track can never silently override a human
    placement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    override_id: CameraOverrideId
    shot_id: ShotId
    pinned_track_revision: str = Field(min_length=64, max_length=64)
    position: Optional["Vec3"] = None
    look_at: Optional["Vec3"] = None
    active: bool = True


class CameraRigPlan(BaseModel):
    """The deterministic, versioned rig the Blender adapter can realize."""

    model_config = ConfigDict(frozen=True, extra="allow")

    plan_id: CameraRigPlanId
    shot_id: ShotId
    scene_id: SceneId
    movement: CameraMovement
    primitive_id: str = ""
    primitive_version: str = ""
    lens: LensProfile
    focus: FocusPlan
    framing: FramingConstraint = Field(default_factory=FramingConstraint)
    path: CameraPath = Field(default_factory=CameraPath)
    start_frame: int = Field(ge=1)
    end_frame: int = Field(ge=1)
    fps: int = Field(default=24, ge=1)
    compiler_version: str = CAMERA_COMPILER_VERSION
    schema_version: str = CAMERA_RIG_SCHEMA_VERSION
    intent_hash: str = ""
    override_id: str = ""       # set when an override placement was applied
    plan_hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def compute_stable_hash(self) -> str:
        payload = json.loads(self.model_dump_json(exclude={"plan_hash"}))
        payload["path"] = [
            {
                "frame": k.frame,
                "position": k.position.as_tuple(),
                "look_at": k.look_at.as_tuple(),
                "easing": k.easing.value,
            }
            for k in self.path.sorted_keyframes()
        ]
        canonical = json.dumps(
            {"schema_version": self.schema_version,
             "compiler_version": self.compiler_version,
             "plan": json.loads(json.dumps(payload, sort_keys=True, default=str))},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Findings + validation (fail-closed, proxy-based)
# ---------------------------------------------------------------------------
class CameraFindingKind:
    """Typed camera finding kinds (stage_g §4 / §5 test matrix)."""

    SIDE_FLIP = "SIDE_FLIP"                       # 180-degree rule violation
    SCREEN_DIRECTION_FLIP = "SCREEN_DIRECTION_FLIP"
    SUBJECT_OUT_OF_FRAME = "SUBJECT_OUT_OF_FRAME"
    HEAD_ROOM_VIOLATION = "HEAD_ROOM_VIOLATION"
    LOOK_ROOM_VIOLATION = "LOOK_ROOM_VIOLATION"
    CAMERA_COLLISION = "CAMERA_COLLISION"
    LENS_OUT_OF_BOUNDS = "LENS_OUT_OF_BOUNDS"
    PATH_DISCONTINUITY = "PATH_DISCONTINUITY"
    MOTION_TOO_FAST = "MOTION_TOO_FAST"
    FOCUS_INVALID = "FOCUS_INVALID"
    DIALOGUE_TIMING_VIOLATION = "DIALOGUE_TIMING_VIOLATION"
    OCCLUSION = "OCCLUSION"


class CameraFinding(BaseModel):
    """One typed camera finding (blocking or advisory)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: CameraFindingId
    kind: str
    shot_id: ShotId = ""
    detail: str = ""
    blocking: bool = False
    frame: int = 0
    position: Vec3 = Field(default_factory=Vec3)
    measured: Dict[str, Any] = Field(default_factory=dict)


class CameraValidationReport(BaseModel):
    """Aggregate result of camera validation over one intent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool = False
    findings: List[CameraFinding] = Field(default_factory=list)
    checked_entity_count: int = Field(default=0, ge=0)

    @property
    def blocking_findings(self) -> List[CameraFinding]:
        return [f for f in self.findings if f.blocking]

    @property
    def blocking_kinds(self) -> List[str]:
        return sorted({f.kind for f in self.blocking_findings})


class CameraValidator:
    """Fail-closed proxy validation (stage_g §4): framing, collision, motion.

    Pure math on intents + AABB proxies; never touches bpy or any engine.
    """

    def validate(
        self,
        *,
        intent: CameraIntent,
        previous_intent: Optional[CameraIntent] = None,
        subject_bounds: Optional[Aabb] = None,
        subject_facing: Optional[Vec3] = None,
        forbidden_volumes: Optional[List[ForbiddenVolume]] = None,
        finding_prefix: str = "cam",
    ) -> CameraValidationReport:
        findings: List[CameraFinding] = []
        lens = intent.lens
        path = intent.path
        duration = intent.duration_seconds

        # lens bounds (backlog 4)
        if not (LENS_FOCAL_MIN_MM <= lens.focal_mm <= LENS_FOCAL_MAX_MM):
            findings.append(self._finding(
                finding_prefix, CameraFindingKind.LENS_OUT_OF_BOUNDS, intent,
                f"focal {lens.focal_mm}mm outside [{LENS_FOCAL_MIN_MM}, {LENS_FOCAL_MAX_MM}]mm",
                blocking=True, measured={"focal_mm": lens.focal_mm}))
        if not (LENS_SENSOR_MIN_MM <= lens.sensor_width_mm <= LENS_SENSOR_MAX_MM):
            findings.append(self._finding(
                finding_prefix, CameraFindingKind.LENS_OUT_OF_BOUNDS, intent,
                f"sensor {lens.sensor_width_mm}mm outside "
                f"[{LENS_SENSOR_MIN_MM}, {LENS_SENSOR_MAX_MM}]mm",
                blocking=True, measured={"sensor_width_mm": lens.sensor_width_mm}))

        # focus target validity is a blocking check (stage_g §6 risk)
        if not intent.focus.valid():
            findings.append(self._finding(
                finding_prefix, CameraFindingKind.FOCUS_INVALID, intent,
                f"focus {intent.focus.focus_distance_m}m not within DOF "
                f"[{intent.focus.dof_near_m}, {intent.focus.dof_far_m}]m",
                blocking=True,
                measured={"focus_distance_m": intent.focus.focus_distance_m,
                          "dof_near_m": intent.focus.dof_near_m,
                          "dof_far_m": intent.focus.dof_far_m}))

        # path continuity (backlog 4)
        jump = path.max_jump_m()
        if jump > MAX_PATH_JUMP_M:
            findings.append(self._finding(
                finding_prefix, CameraFindingKind.PATH_DISCONTINUITY, intent,
                f"max keyframe jump {jump:.2f}m exceeds {MAX_PATH_JUMP_M}m",
                blocking=True, measured={"max_jump_m": round(jump, 3)}))

        # motion speed: camera movement quá ngắn (stage_g §5)
        speed = path.length_m() / duration if duration > 0 else 0.0
        if duration < MIN_SHOT_DURATION_S or speed > MAX_MOTION_SPEED_MPS:
            findings.append(self._finding(
                finding_prefix, CameraFindingKind.MOTION_TOO_FAST, intent,
                f"speed {speed:.2f}m/s over {duration:.2f}s exceeds "
                f"{MAX_MOTION_SPEED_MPS}m/s (or shot shorter than {MIN_SHOT_DURATION_S}s)",
                blocking=True,
                measured={"speed_mps": round(speed, 3),
                          "duration_seconds": round(duration, 3),
                          "path_length_m": round(path.length_m(), 3)}))

        # 180-degree rule + screen direction vs previous shot (backlog 4)
        if previous_intent is not None:
            prev_side = previous_intent.side
            if (prev_side in (CameraSide.SIDE_A, CameraSide.SIDE_B)
                    and intent.side in (CameraSide.SIDE_A, CameraSide.SIDE_B)
                    and prev_side != intent.side):
                findings.append(self._finding(
                    finding_prefix, CameraFindingKind.SIDE_FLIP, intent,
                    f"camera-side flip {prev_side.value} -> {intent.side.value} "
                    f"across the action line",
                    blocking=True,
                    measured={"previous_side": prev_side.value,
                              "side": intent.side.value}))
            prev_dir = previous_intent.screen_direction
            if (prev_dir in (ScreenDirection.LEFT_TO_RIGHT,
                             ScreenDirection.RIGHT_TO_LEFT)
                    and intent.screen_direction in (ScreenDirection.LEFT_TO_RIGHT,
                                                    ScreenDirection.RIGHT_TO_LEFT)
                    and prev_dir != intent.screen_direction):
                findings.append(self._finding(
                    finding_prefix, CameraFindingKind.SCREEN_DIRECTION_FLIP, intent,
                    f"screen direction flip {prev_dir.value} -> "
                    f"{intent.screen_direction.value}",
                    blocking=True,
                    measured={"previous_direction": prev_dir.value,
                              "direction": intent.screen_direction.value}))

        # subject visibility / head room / look room (pinhole proxy)
        if subject_bounds is not None:
            self._check_framing(
                findings, finding_prefix, intent, lens, subject_bounds,
                subject_facing,
            )

        # camera collision: path positions AND segments vs forbidden volumes
        for vol in (forbidden_volumes or []):
            for pose in self._sample_path(path):
                if vol.bounds.contains_point(pose.position):
                    findings.append(self._finding(
                        finding_prefix, CameraFindingKind.CAMERA_COLLISION, intent,
                        f"camera at {pose.position.as_tuple()} inside volume "
                        f"{vol.name!r}",
                        blocking=True,
                        position=pose.position,
                        measured={"volume": vol.name}))
            keys = path.sorted_keyframes()
            for a, b in zip(keys, keys[1:]):
                if segment_hits_aabb(a.position, b.position, vol.bounds):
                    findings.append(self._finding(
                        finding_prefix, CameraFindingKind.CAMERA_COLLISION, intent,
                        f"camera path segment {a.position.as_tuple()} -> "
                        f"{b.position.as_tuple()} crosses volume {vol.name!r}",
                        blocking=True,
                        position=a.position,
                        measured={"volume": vol.name, "segment": [
                            a.position.as_tuple(), b.position.as_tuple()]}))

        return CameraValidationReport(
            ok=not findings, findings=findings,
            checked_entity_count=len(findings) + 1,
        )

    # ------------------------------------------------------------------
    def _check_framing(self, findings, prefix, intent, lens,
                       subject_bounds: Aabb,
                       subject_facing: Optional[Vec3]) -> None:
        pose = intent.path.sample(0.5)
        center = Vec3(
            x=subject_bounds.center_x, y=subject_bounds.center_y,
            z=subject_bounds.top_z - intent.framing.subject_height_m / 2.0,
        )
        head = Vec3(
            x=subject_bounds.center_x, y=subject_bounds.center_y,
            z=subject_bounds.top_z,
        )
        proj_center = project_to_screen(center, pose, lens)
        proj_head = project_to_screen(head, pose, lens)
        safe = 1.0 - intent.framing.safe_margin
        head_room = 1.0 - intent.framing.head_room_ratio
        look_room = 1.0 - intent.framing.look_room_ratio

        if (not proj_center.visible
                or abs(proj_center.x) > safe or abs(proj_center.y) > safe):
            findings.append(self._finding(
                prefix, CameraFindingKind.SUBJECT_OUT_OF_FRAME, intent,
                f"subject center screen ({proj_center.x:.2f}, {proj_center.y:.2f}) "
                f"outside safe frame ±{safe:.2f}",
                blocking=True,
                measured={"screen_x": round(proj_center.x, 3),
                          "screen_y": round(proj_center.y, 3)}))
            return
        if proj_head.depth > 0 and proj_head.y > head_room:
            findings.append(self._finding(
                prefix, CameraFindingKind.HEAD_ROOM_VIOLATION, intent,
                f"head top at y={proj_head.y:.2f} above head-room limit "
                f"{head_room:.2f}",
                blocking=True,
                measured={"head_screen_y": round(proj_head.y, 3),
                          "head_room_limit": round(head_room, 3)}))
        if subject_facing is not None:
            forward = _normalize(_sub(pose.look_at, pose.position))
            right = _normalize(_cross(forward, DEFAULT_UP))
            facing_right = _dot(subject_facing, right)
            if abs(facing_right) > 1e-6:
                limit = look_room if facing_right > 0 else -look_room
                if (facing_right > 0 and proj_center.x > limit) or (
                        facing_right < 0 and proj_center.x < limit):
                    findings.append(self._finding(
                        prefix, CameraFindingKind.LOOK_ROOM_VIOLATION, intent,
                        f"subject looks toward frame edge (screen x="
                        f"{proj_center.x:.2f}) with insufficient look room",
                        blocking=True,
                        measured={"screen_x": round(proj_center.x, 3),
                                  "look_room_limit": round(limit, 3),
                                  "facing_right": round(facing_right, 3)}))

    @staticmethod
    def _sample_path(path: CameraPath, samples: int = 5) -> List[CameraPose]:
        if not path.keyframes:
            return []
        if len(path.keyframes) == 1:
            return [CameraPose(position=path.keyframes[0].position,
                               look_at=path.keyframes[0].look_at)]
        return [path.sample(i / max(1, samples - 1))
                for i in range(samples)]

    @staticmethod
    def _finding(prefix: str, kind: str, intent: CameraIntent, detail: str,
                 *, blocking: bool, position: Optional[Vec3] = None,
                 frame: int = 0, measured: Optional[Dict[str, Any]] = None
                 ) -> CameraFinding:
        return CameraFinding(
            finding_id=CameraFindingId(
                f"{prefix}:{intent.intent_id}:{kind.lower()}"),
            kind=kind, shot_id=intent.shot_id, detail=detail,
            blocking=blocking,
            position=position or Vec3(), frame=frame,
            measured=measured or {},
        )


__all__ = [
    "CAMERA_COMPILER_VERSION",
    "CAMERA_RIG_SCHEMA_VERSION",
    "LENS_FOCAL_MIN_MM",
    "LENS_FOCAL_MAX_MM",
    "LENS_SENSOR_MIN_MM",
    "LENS_SENSOR_MAX_MM",
    "MAX_PATH_JUMP_M",
    "MAX_MOTION_SPEED_MPS",
    "MIN_SHOT_DURATION_S",
    "segment_hits_aabb",
    "LensProfile",
    "FocusPlan",
    "FramingConstraint",
    "DialogueTiming",
    "CameraKeyframe",
    "CameraPath",
    "CameraPose",
    "ScreenProjection",
    "project_to_screen",
    "CameraIntent",
    "CameraOverride",
    "CameraRigPlan",
    "CameraFindingKind",
    "CameraFinding",
    "CameraValidationReport",
    "CameraValidator",
]
