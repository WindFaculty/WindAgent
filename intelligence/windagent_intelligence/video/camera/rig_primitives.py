"""
Versioned camera rig primitives (VP3D Phase 13, stage_g §3 backlog 1).

Maps the canonical `CameraMovement` values (STATIC, PAN, TILT, DOLLY, TRACK,
CRANE) onto named, versioned rig primitives the Blender adapter can realize.
The registry version participates in the rig manifest hash, so bumping a
primitive definition deterministically changes every dependent rig manifest.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import CameraMovement
from windagent_core.domain.video_production.errors import CameraCompileError

RIG_PRIMITIVES_VERSION = "1.0.0"


class CameraRigPrimitive(BaseModel):
    """One versioned rig primitive: what motion axes the rig drives."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    primitive_id: str
    movement: CameraMovement
    motion_axes: List[str] = Field(default_factory=list)
    description: str = ""
    version: str = RIG_PRIMITIVES_VERSION


_PRIMITIVES: Dict[CameraMovement, CameraRigPrimitive] = {
    CameraMovement.STATIC: CameraRigPrimitive(
        primitive_id="cam_rig/static/v1", movement=CameraMovement.STATIC,
        motion_axes=[], description="Fixed pose; no motion axes."),
    CameraMovement.PAN: CameraRigPrimitive(
        primitive_id="cam_rig/pan/v1", movement=CameraMovement.PAN,
        motion_axes=["yaw"], description="Rotates around the camera's Y (yaw)."),
    CameraMovement.TILT: CameraRigPrimitive(
        primitive_id="cam_rig/tilt/v1", movement=CameraMovement.TILT,
        motion_axes=["pitch"], description="Rotates around the camera's X (pitch)."),
    CameraMovement.DOLLY: CameraRigPrimitive(
        primitive_id="cam_rig/dolly/v1", movement=CameraMovement.DOLLY,
        motion_axes=["forward"], description="Translates along the look direction."),
    CameraMovement.TRACK: CameraRigPrimitive(
        primitive_id="cam_rig/track/v1", movement=CameraMovement.TRACK,
        motion_axes=["lateral"], description="Translates sideways, parallel to the subject."),
    CameraMovement.CRANE: CameraRigPrimitive(
        primitive_id="cam_rig/crane/v1", movement=CameraMovement.CRANE,
        motion_axes=["vertical"], description="Translates vertically (boom up/down)."),
}


def resolve_primitive(movement: CameraMovement) -> CameraRigPrimitive:
    """Resolve a movement to its versioned primitive; unknown values fail closed."""
    primitive = _PRIMITIVES.get(movement)
    if primitive is None:
        raise CameraCompileError(
            f"no rig primitive registered for movement {movement!r}",
            details={"movement": getattr(movement, "value", str(movement))},
        )
    return primitive


def all_primitives() -> List[CameraRigPrimitive]:
    return [resolve_primitive(m) for m in CameraMovement]


def supported_movements() -> List[str]:
    return sorted(m.value for m in CameraMovement)


__all__ = [
    "RIG_PRIMITIVES_VERSION",
    "CameraRigPrimitive",
    "resolve_primitive",
    "all_primitives",
    "supported_movements",
]
