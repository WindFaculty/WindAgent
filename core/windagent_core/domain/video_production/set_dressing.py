"""
Stage F Set Dressing domain (VP3D Phase 12).

Frozen, engine-neutral DTOs for environment construction and set dressing.
No ``bpy``, no provider SDK, no transport object ever appears here: the
planner layer (`intelligence/windagent_intelligence/video/set_dressing/`)
maps Production IR + approved assets onto these typed objects, and the scene
compiler (tools layer) consumes them. Core stays tools/intelligence-neutral.

Everything is deterministic and fail-closed: spatial findings are typed, every
placed entity carries a canonical ID and (where an approved asset is required)
a revision hash, and the plan exposes a canonical content hash so a changed
input deterministically invalidates only dependent scenes/shots.

Proxy bounds (AABB) are used for cheap collision/constraint checks; exact
mesh intersection is deferred to the blender compiler / inspector (plan §7
risk: collision meshes are expensive — proxy bounds first).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.ids import (
    EnvironmentInstanceId,
    PropInstanceId,
    SetDressingSceneId,
    SpatialFindingId,
)


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Vec3(BaseModel):
    """Cartesian coordinate in meters, Z-up canonical space."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_tuple(self) -> tuple:
        return (self.x, self.y, self.z)


class Aabb(BaseModel):
    """Axis-aligned proxy bounds (min/max corners). Collision check uses these."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min: Vec3 = Field(default_factory=lambda: Vec3(x=0.0, y=0.0, z=0.0))
    max: Vec3 = Field(default_factory=lambda: Vec3(x=1.0, y=1.0, z=1.0))

    @classmethod
    def from_center_size(
        cls, center: Vec3, size: Vec3, *, up: float = 0.0
    ) -> "Aabb":
        """AABB from a center point + total size (size.z ignored for flat surfaces)."""
        half = Vec3(x=size.x / 2.0, y=size.y / 2.0, z=size.z / 2.0)
        return cls(
            min=Vec3(x=center.x - half.x, y=center.y - half.y, z=center.z - half.z),
            max=Vec3(x=center.x + half.x, y=center.y + half.y, z=center.z + half.z),
        )

    @property
    def center_x(self) -> float:
        return (self.min.x + self.max.x) / 2.0

    @property
    def center_y(self) -> float:
        return (self.min.y + self.max.y) / 2.0

    @property
    def top_z(self) -> float:
        return self.max.z

    @property
    def bottom_z(self) -> float:
        return self.min.z

    @property
    def width(self) -> float:
        return self.max.x - self.min.x

    @property
    def depth(self) -> float:
        return self.max.y - self.min.y

    @property
    def height(self) -> float:
        return self.max.z - self.min.z

    def overlaps(self, other: "Aabb") -> bool:
        """True if this AABB overlaps another (strictly less on every axis)."""
        return not (
            self.max.x <= other.min.x
            or other.max.x <= self.min.x
            or self.max.y <= other.min.y
            or other.max.y <= self.min.y
            or self.max.z <= other.min.z
            or other.max.z <= self.min.z
        )

    def contains(self, other: "Aabb") -> bool:
        """True if `other` is fully inside this AABB."""
        return (
            self.min.x <= other.min.x
            and self.max.x >= other.max.x
            and self.min.y <= other.min.y
            and self.max.y >= other.max.y
            and self.min.z <= other.min.z
            and self.max.z >= other.max.z
        )

    def contains_point(self, p: Vec3) -> bool:
        return (
            self.min.x <= p.x <= self.max.x
            and self.min.y <= p.y <= self.max.y
            and self.min.z <= p.z <= self.max.z
        )


class SupportSurface(BaseModel):
    """A floor / table / ledge that can support placed props or characters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    bounds: Aabb
    surface_z: float = Field(ge=0.0)  # top face height (where things stand)

    @property
    def top(self) -> float:
        """Reference stand height for entities resting on this surface."""
        return self.surface_z


class NavigationZone(BaseModel):
    """A walkable region characters may occupy / move through."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    bounds: Aabb


class ForbiddenVolume(BaseModel):
    """An excluded volume (wall, cabinet, blocked area) nothing may penetrate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    bounds: Aabb


class AttachmentPoint(BaseModel):
    """A named anchor on a surface where props may attach (e.g. table_corner)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    position: Vec3
    surface: str = ""  # owning SupportSurface name


class InteractionAnchor(BaseModel):
    """A locus a character must reach to interact with an object (seat, table)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    position: Vec3
    facing: Vec3 = Field(default_factory=lambda: Vec3(x=0.0, y=1.0, z=0.0))
    reachable: bool = True


class EnvironmentSpec(BaseModel):
    """Compiled neutral description of the world: surfaces, zones, volumes, anchors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    environment_id: EnvironmentInstanceId
    support_surfaces: List[SupportSurface] = Field(default_factory=list)
    navigation_zones: List[NavigationZone] = Field(default_factory=list)
    forbidden_volumes: List[ForbiddenVolume] = Field(default_factory=list)
    attachment_points: List[AttachmentPoint] = Field(default_factory=list)
    interaction_anchors: List[InteractionAnchor] = Field(default_factory=list)
    unit: str = "METERS"


class PropPlacement(BaseModel):
    """One placed prop: canonical ID + approved asset revision hash + transform."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prop_id: PropInstanceId
    asset_hash: str = Field(min_length=64, max_length=64)  # approved revision hash
    anchor: str = ""  # AttachmentPoint name (or explicit position when empty)
    position: Vec3
    rotation_yaw: float = Field(default=0.0, ge=0.0, lt=360.0)
    scale: Vec3 = Field(default_factory=lambda: Vec3(x=1.0, y=1.0, z=1.0))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def content_tuple(self) -> tuple:
        return (
            str(self.prop_id),
            self.asset_hash,
            self.anchor,
            round(self.position.x, 6),
            round(self.position.y, 6),
            round(self.position.z, 6),
            round(self.rotation_yaw, 6),
            round(self.scale.x, 6),
            round(self.scale.y, 6),
            round(self.scale.z, 6),
        )


class CharacterPlacement(BaseModel):
    """One placed character: canonical ID + approved asset + anchor + facing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    character_id: str
    asset_hash: str = Field(min_length=64, max_length=64)
    anchor: str = ""
    position: Vec3
    facing: Vec3 = Field(default_factory=lambda: Vec3(x=0.0, y=1.0, z=0.0))
    stand_z: float = Field(default=0.0, ge=0.0)  # surface top the character stands on


class CameraPlaceholder(BaseModel):
    """Typed camera placeholder — Stage G compiles the detailed rig."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    position: Vec3
    look_at: Vec3 = Field(default_factory=Vec3)


class LightPlaceholder(BaseModel):
    """Typed light placeholder — Stage G compiles the detailed rig."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: str = "POINT"  # AREA | SUN | POINT (placeholder only)
    position: Vec3 = Field(default_factory=Vec3)


class SetDressingPlan(BaseModel):
    """Deterministic, versioned set-dressing plan for one scene."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    plan_id: str = ""
    scene_id: str = ""
    seed: int = 0
    compiler_version: str = ""
    environment: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    props: List[PropPlacement] = Field(default_factory=list)
    characters: List[CharacterPlacement] = Field(default_factory=list)
    cameras: List[CameraPlaceholder] = Field(default_factory=list)
    lights: List[LightPlaceholder] = Field(default_factory=list)
    input_hash: str = ""
    tool_hash: str = ""

    @property
    def sorted_props(self) -> List[PropPlacement]:
        return sorted(self.props, key=lambda p: str(p.prop_id))

    @property
    def sorted_characters(self) -> List[CharacterPlacement]:
        return sorted(self.characters, key=lambda c: str(c.character_id))

    def canonical_bytes(self) -> bytes:
        payload = json.loads(self.model_dump_json())
        payload["props"] = [p.content_tuple() for p in self.sorted_props]
        payload["characters"] = sorted(
            (str(c.character_id), c.anchor, round(c.position.x, 6),
             round(c.position.y, 6), round(c.position.z, 6))
            for c in self.characters
        )
        payload["cameras"] = sorted(
            (c.name, round(c.position.x, 6), round(c.position.y, 6),
             round(c.position.z, 6))
            for c in self.cameras
        )
        payload["lights"] = sorted(
            (l.name, l.kind, round(l.position.x, 6), round(l.position.y, 6),
             round(l.position.z, 6))
            for l in self.lights
        )
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return canonical.encode("utf-8")

    def plan_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def idempotency_key(self) -> str:
        return _stable_hash(self.input_hash, self.tool_hash, self.seed)


class SpatialFindingKind:
    PENETRATION = "PENETRATION"
    FLOATING = "FLOATING"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    CAMERA_IN_MESH = "CAMERA_IN_MESH"
    OCCLUDING_BLOCKER = "OCCLUDING_BLOCKER"
    DUPLICATE_ID = "DUPLICATE_ID"
    MISSING_APPROVED_ASSET = "MISSING_APPROVED_ASSET"
    OUT_OF_REACH = "OUT_OF_REACH"
    WRONG_FACING = "WRONG_FACING"
    BELOW_FLOOR = "BELOW_FLOOR"


class SpatialFinding(BaseModel):
    """One typed spatial/constraint finding (blocking or advisory)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: SpatialFindingId
    kind: str
    entity: str = ""
    detail: str = ""
    blocking: bool = False
    position: Vec3 = Field(default_factory=Vec3)


class SpatialValidationReport(BaseModel):
    """Aggregate result of spatial validation over a set-dressing plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool = False
    findings: List[SpatialFinding] = Field(default_factory=list)
    checked_entity_count: int = Field(default=0, ge=0)

    @property
    def blocking_findings(self) -> List[SpatialFinding]:
        return [f for f in self.findings if f.blocking]

    @property
    def blocking_kinds(self) -> List[str]:
        return sorted({f.kind for f in self.blocking_findings})


__all__ = [
    "_stable_hash",
    "Vec3",
    "Aabb",
    "SupportSurface",
    "NavigationZone",
    "ForbiddenVolume",
    "AttachmentPoint",
    "InteractionAnchor",
    "EnvironmentSpec",
    "PropPlacement",
    "CharacterPlacement",
    "CameraPlaceholder",
    "LightPlaceholder",
    "SetDressingPlan",
    "SpatialFindingKind",
    "SpatialFinding",
    "SpatialValidationReport",
]
