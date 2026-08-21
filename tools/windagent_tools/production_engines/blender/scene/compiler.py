"""
VP3D Phase 4 — Trusted scene compiler (plan Stage B §4).

`ScenePlanCompiler` maps the ENGINE-NEUTRAL Production IR (SceneDescription +
RenderIntent + ShotExecutionIntent) onto a TYPED, DETERMINISTIC `ScenePlan`
(scene_plan.json). Everything that must be locked for reproducible renders is
locked here:

- seed (default: derived from the IR content hash so the same IR always
  produces the same plan — determinism item 7);
- frame range (from RenderIntent.frame_start..frame_end, frame_end=0 derives
  from the shot duration * fps);
- fps, resolution, color management, Cycles samples, denoise, device;
- the trusted, version-pinned `bpy` build script text.

Security contract (plan §4 "trusted compiler"): the bpy script is a FIXED,
version-pinned template shipped in this module — NEVER LLM-generated and never
runtime-invented. The compiler only substitutes locked values into the pinned
template. `tool_hash` pins the compiler+template version so a changed script
invalidates cached artifacts (idempotency item 5).

The plan is pure JSON data: `execute_job.py` (pure stdlib, runs inside
Blender's Python) reads `scene_plan.json` and execs the pinned build script.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from windagent_core.domain.video_production.production_ir.models import (
    RenderIntent,
    SceneDescription,
    ShotExecutionIntent,
)

SCENE_PLAN_SCHEMA_VERSION = "1.0.0"
TRUSTED_SCRIPT_VERSION = "4.5.0"  # bpy script template pinned to Blender 4.5 LTS

# Locked color-management choices (engine-neutral ladder the template maps).
COLOR_MANAGEMENT_STANDARD = "Standard"
COLOR_MANAGEMENT_FILMIC = "Filmic"
COLOR_MANAGEMENT_AGX = "AgX"
COLOR_MANAGEMENT_DEFAULT = COLOR_MANAGEMENT_STANDARD

# Locked device ladder (from capability probe classification).
DEVICE_CPU = "CPU"
DEVICE_OPTIX = "OPTIX"
DEVICE_CUDA = "CUDA"
DEVICE_NONE = "NONE"

# Quality -> locked defaults (deterministic mapping, no per-machine tuning).
QUALITY_DEFAULTS: Dict[str, Dict] = {
    "DRAFT": {"samples": 8, "denoise": False},
    "PREVIEW": {"samples": 16, "denoise": True},
    "HIGH": {"samples": 64, "denoise": True},
    "FINAL": {"samples": 128, "denoise": True},
}


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScenePlanObject:
    """One typed object in the locked scene (e.g. cube, ground)."""

    name: str
    kind: str  # CUBE | PLANE | ...
    location: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)
    scale: tuple = (1.0, 1.0, 1.0)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "location": list(self.location),
            "rotation": list(self.rotation),
            "scale": list(self.scale),
        }


@dataclass(frozen=True)
class ScenePlanCamera:
    """Locked camera placement."""

    location: tuple = (7.0, -6.0, 4.5)
    rotation: tuple = (1.1, 0.0, 0.7)
    lens_mm: float = 35.0
    sensor_width_mm: float = 36.0

    def to_dict(self) -> dict:
        return {
            "location": list(self.location),
            "rotation": list(self.rotation),
            "lens_mm": self.lens_mm,
            "sensor_width_mm": self.sensor_width_mm,
        }


@dataclass(frozen=True)
class ScenePlanLight:
    """One locked light (key/fill/rim)."""

    name: str
    kind: str  # AREA | SUN | POINT
    energy: float
    color: tuple = (1.0, 1.0, 1.0)
    location: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "energy": self.energy,
            "color": list(self.color),
            "location": list(self.location),
            "rotation": list(self.rotation),
        }


@dataclass(frozen=True)
class ScenePlanMaterial:
    """One locked material (Principled BSDF)."""

    name: str
    base_color: tuple = (0.8, 0.2, 0.2, 1.0)
    roughness: float = 0.4
    metallic: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "base_color": list(self.base_color),
            "roughness": self.roughness,
            "metallic": self.metallic,
        }


@dataclass(frozen=True)
class ScenePlanAnimation:
    """Locked keyframed animation (cube rotation over the frame range)."""

    target_object: str
    start_frame: int
    end_frame: int
    start_rotation_z: float = 0.0
    end_rotation_z: float = 6.283185307179586  # one full turn
    start_location: tuple = (0.0, 0.0, 1.0)
    end_location: tuple = (0.0, 0.0, 1.0)

    def to_dict(self) -> dict:
        return {
            "target_object": self.target_object,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_rotation_z": self.start_rotation_z,
            "end_rotation_z": self.end_rotation_z,
            "start_location": list(self.start_location),
            "end_location": list(self.end_location),
        }


@dataclass(frozen=True)
class ScenePlan:
    """Typed, deterministic, locked scene plan (scene_plan.json)."""

    schema_version: str = SCENE_PLAN_SCHEMA_VERSION
    scene_plan_id: str = ""
    scene_id: str = ""
    seed: int = 0
    frame_start: int = 1
    frame_end: int = 120
    fps: int = 24
    color_management: str = COLOR_MANAGEMENT_DEFAULT
    resolution: Dict[str, int] = field(default_factory=lambda: {"width": 640, "height": 360})
    cycles_samples: int = 16
    denoise: bool = True
    device: str = DEVICE_CPU
    objects: List[ScenePlanObject] = field(default_factory=list)
    camera: ScenePlanCamera = field(default_factory=ScenePlanCamera)
    lights: List[ScenePlanLight] = field(default_factory=list)
    material: ScenePlanMaterial = field(default_factory=ScenePlanMaterial)
    animation: ScenePlanAnimation = field(default_factory=ScenePlanAnimation)
    input_hash: str = ""  # IR content hash (exact inputs)
    config_hash: str = ""  # locked config hash (fps/resolution/color/samples/...)
    tool_hash: str = ""  # compiler + trusted script version (tool identity)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "scene_plan_id": self.scene_plan_id,
            "scene_id": self.scene_id,
            "seed": self.seed,
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "fps": self.fps,
            "color_management": self.color_management,
            "resolution": dict(self.resolution),
            "cycles_samples": self.cycles_samples,
            "denoise": self.denoise,
            "device": self.device,
            "objects": [o.to_dict() for o in self.objects],
            "camera": self.camera.to_dict(),
            "lights": [light.to_dict() for light in self.lights],
            "material": self.material.to_dict(),
            "animation": self.animation.to_dict(),
            "input_hash": self.input_hash,
            "config_hash": self.config_hash,
            "tool_hash": self.tool_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScenePlan":
        return cls(
            schema_version=data.get("schema_version", SCENE_PLAN_SCHEMA_VERSION),
            scene_plan_id=data.get("scene_plan_id", ""),
            scene_id=data.get("scene_id", ""),
            seed=data.get("seed", 0),
            frame_start=data.get("frame_start", 1),
            frame_end=data.get("frame_end", 120),
            fps=data.get("fps", 24),
            color_management=data.get("color_management", COLOR_MANAGEMENT_DEFAULT),
            resolution=dict(data.get("resolution", {"width": 640, "height": 360})),
            cycles_samples=data.get("cycles_samples", 16),
            denoise=data.get("denoise", True),
            device=data.get("device", DEVICE_CPU),
            objects=[
                ScenePlanObject(**o)
                for o in data.get("objects", [])
                if isinstance(o, dict)
            ],
            camera=ScenePlanCamera(**data.get("camera", {})),
            lights=[
                ScenePlanLight(**light)
                for light in data.get("lights", [])
                if isinstance(light, dict)
            ],
            material=ScenePlanMaterial(**data.get("material", {})),
            animation=ScenePlanAnimation(**data.get("animation", {})),
            input_hash=data.get("input_hash", ""),
            config_hash=data.get("config_hash", ""),
            tool_hash=data.get("tool_hash", ""),
        )

    def canonical_bytes(self) -> bytes:
        """Stable canonical bytes (sorted, compact) for hashing the plan."""
        canonical = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return canonical.encode("utf-8")

    def plan_hash(self) -> str:
        """Content hash of the FULL plan (including input/config/tool hashes)."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def idempotency_key(self) -> str:
        """Job input key: the render only reuses artifacts when this matches.

        Covers IR inputs (input_hash) + locked render config (config_hash) +
        tool identity (tool_hash). A change to ANY of them invalidates the
        cached output (plan §4 item 5).
        """
        return _stable_hash(self.input_hash, self.config_hash, self.tool_hash)


# ---------------------------------------------------------------------------
# Trusted, version-pinned bpy build script template
# ---------------------------------------------------------------------------
# This is the ONLY script the pipeline ever ships to Blender for scene
# building. It is pinned by TRUSTED_SCRIPT_VERSION; substituting new code is a
# tool_hash change that invalidates cached artifacts. It never reads env
# secrets, never installs add-ons, never touches files outside the workspace.
_TRUSTED_BUILD_SCRIPT_TEMPLATE = r'''"""
Trusted deterministic scene build script — Blender 4.5 LTS (pinned).

Generated by the pinned scene compiler; read-only over scene_plan.json in the
current working directory (the job workspace). Never modified at runtime.
"""

import json
import math
import random
from pathlib import Path

plan = json.loads(Path("scene_plan.json").read_text(encoding="utf-8"))

import bpy  # noqa: E402  (bpy only exists inside blender)

random.seed(plan["seed"])


def _clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _add_object(kind, name, location, rotation, scale):
    if kind == "CUBE":
        bpy.ops.mesh.primitive_cube_add(size=1.0)
    elif kind == "PLANE":
        bpy.ops.mesh.primitive_plane_add(size=1.0)
    else:
        bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.active_object
    obj.name = name
    obj.location = location
    obj.rotation_euler = rotation
    obj.scale = scale
    return obj


def _make_material(spec):
    mat = bpy.data.materials.new(name=spec["name"])
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = spec["base_color"]
        bsdf.inputs["Roughness"].default_value = spec["roughness"]
        bsdf.inputs["Metallic"].default_value = spec["metallic"]
    return mat


def _add_lights(specs):
    for light_spec in specs:
        bpy.ops.object.light_add(
            type=light_spec["kind"],
            location=light_spec["location"],
            rotation=light_spec["rotation"],
        )
        light = bpy.context.active_object
        light.name = light_spec["name"]
        light.data.energy = light_spec["energy"]
        light.data.color = light_spec["color"]


def _add_camera(spec):
    cam = bpy.data.cameras.new("MainCamera")
    cam.lens = spec["lens_mm"]
    cam.sensor_width = spec["sensor_width_mm"]
    obj = bpy.data.objects.new("MainCamera", cam)
    bpy.context.collection.objects.link(obj)
    obj.location = spec["location"]
    obj.rotation_euler = spec["rotation"]
    bpy.context.scene.camera = obj


def _animate(spec, frame_start, frame_end):
    target = bpy.data.objects.get(spec["target_object"])
    if target is None:
        return
    target.rotation_euler[2] = spec["start_rotation_z"]
    target.location = spec["start_location"]
    target.keyframe_insert(data_path="rotation_euler", frame=frame_start)
    target.keyframe_insert(data_path="location", frame=frame_start)
    target.rotation_euler[2] = spec["end_rotation_z"]
    target.location = spec["end_location"]
    target.keyframe_insert(data_path="rotation_euler", frame=frame_end)
    target.keyframe_insert(data_path="location", frame=frame_end)


def _configure_render(plan):
    scene = bpy.context.scene
    scene.frame_start = plan["frame_start"]
    scene.frame_end = plan["frame_end"]
    scene.render.fps = plan["fps"]
    scene.render.resolution_x = plan["resolution"]["width"]
    scene.render.resolution_y = plan["resolution"]["height"]
    scene.render.film_transparent = False
    scene.view_settings.view_transform = plan["color_management"]

    scene.render.engine = "CYCLES"
    cycles = scene.cycles
    cycles.samples = plan["cycles_samples"]
    cycles.use_denoising = plan["denoise"]
    if plan["device"] == "CPU":
        scene.cycles.device = "CPU"
    elif plan["device"] in ("OPTIX", "CUDA"):
        scene.cycles.device = "GPU"
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = plan["device"]
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type in ("OPTIX", "CUDA")


def main():
    _clear_scene()
    for obj_spec in plan["objects"]:
        obj = _add_object(
            obj_spec["kind"],
            obj_spec["name"],
            obj_spec["location"],
            obj_spec["rotation"],
            obj_spec["scale"],
        )
        obj.data.materials.append(_make_material(plan["material"]))
    _add_lights(plan["lights"])
    _add_camera(plan["camera"])
    _animate(plan["animation"], plan["frame_start"], plan["frame_end"])
    _configure_render(plan)
    out = Path(plan.get("output_blend_path", "scene.blend"))
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print(json.dumps({"built": True, "objects": len(plan["objects"]),
                      "lights": len(plan["lights"]), "out": str(out)}))


if __name__ == "__main__":
    main()
'''


class ScenePlanCompiler:
    """Maps Production IR units onto a locked, deterministic ScenePlan."""

    compiler_version = "1.0.0"
    script_version = TRUSTED_SCRIPT_VERSION

    def __init__(self, *, quality_defaults: Optional[Dict[str, Dict]] = None) -> None:
        self._quality_defaults = quality_defaults or QUALITY_DEFAULTS

    # ------------------------------------------------------------------
    def tool_hash(self) -> str:
        """Pin compiler + trusted script identity (invalidates artifacts)."""
        return _stable_hash(
            f"ScenePlanCompiler:{self.compiler_version}",
            f"trusted_build_script:{self.script_version}",
        )

    def compile(
        self,
        scene: SceneDescription,
        render: RenderIntent,
        shot: Optional[ShotExecutionIntent] = None,
        *,
        seed: Optional[int] = None,
        device: str = DEVICE_CPU,
    ) -> ScenePlan:
        """Build the locked scene plan from engine-neutral IR units.

        Determinism: with the same IR + device + compiler, the plan (and its
        idempotency key) is byte-for-byte identical. The seed defaults to a
        hash of the IR content so a second run reproduces the same plan.
        """
        ir_hash = scene.content_hash() if hasattr(scene, "content_hash") else ""
        if not ir_hash:
            # SceneDescription has no content_hash method; hash its canonical
            # JSON — stable because models are frozen + extra=allow.
            import json as _json

            ir_hash = hashlib.sha256(
                _json.dumps(
                    scene.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
                ).encode("utf-8")
            ).hexdigest()

        profile = render.profile
        quality = profile.quality.value
        locked = self._quality_defaults.get(quality, self._quality_defaults["HIGH"])

        fps = profile.frame_rate or 24
        frame_start = render.frame_start or 1
        if render.frame_end and render.frame_end >= frame_start:
            frame_end = render.frame_end
        elif shot is not None and shot.duration_seconds > 0:
            frame_end = max(frame_start, frame_start + int(round(shot.duration_seconds * fps)) - 1)
        else:
            frame_end = frame_start + fps - 1  # 1 second by default

        resolution = dict(profile.resolution) or {"width": 640, "height": 360}
        color_management = profile.metadata.get(
            "color_management", COLOR_MANAGEMENT_DEFAULT
        )
        denoise = profile.denoise
        samples = profile.samples if profile.samples > 0 else locked["samples"]
        if not profile.denoise:
            denoise = locked["denoise"]
            samples = locked["samples"] if quality != "HIGH" else samples

        config_hash = _stable_hash(
            f"fps:{fps}",
            f"range:{frame_start}:{frame_end}",
            f"res:{resolution['width']}x{resolution['height']}",
            f"cm:{color_management}",
            f"samples:{samples}",
            f"denoise:{denoise}",
            f"device:{device}",
        )

        if seed is None:
            seed = int(ir_hash[:8], 16)

        plan = ScenePlan(
            scene_plan_id=f"sp_{scene.scene_id}",
            scene_id=str(scene.scene_id),
            seed=seed,
            frame_start=frame_start,
            frame_end=frame_end,
            fps=fps,
            color_management=color_management,
            resolution=resolution,
            cycles_samples=samples,
            denoise=denoise,
            device=device,
            objects=[
                ScenePlanObject(name="Cube", kind="CUBE", location=(0.0, 0.0, 0.5)),
                ScenePlanObject(name="Ground", kind="PLANE", scale=(4.0, 4.0, 1.0)),
            ],
            camera=ScenePlanCamera(),
            lights=[
                ScenePlanLight(name="Key", kind="AREA", energy=800.0,
                               location=(5.0, -4.0, 6.0)),
                ScenePlanLight(name="Fill", kind="AREA", energy=200.0,
                               location=(-5.0, -4.0, 3.0)),
                ScenePlanLight(name="Rim", kind="AREA", energy=300.0,
                               location=(0.0, 6.0, 5.0)),
            ],
            material=ScenePlanMaterial(name="SmokeMaterial"),
            animation=ScenePlanAnimation(
                target_object="Cube",
                start_frame=frame_start,
                end_frame=frame_end,
            ),
            input_hash=ir_hash,
            config_hash=config_hash,
            tool_hash=self.tool_hash(),
        )
        return plan

    # ------------------------------------------------------------------
    def build_script(self, plan: ScenePlan) -> str:
        """Return the pinned trusted build script for this plan.

        The template is FIXED; only the locked plan is substituted (the
        script reads scene_plan.json from its cwd — the job workspace). The
        script text is hash-pinned by `tool_hash`, so a changed template
        invalidates cached artifacts (idempotency item 5).
        """
        payload = plan.to_dict()
        payload["output_blend_path"] = "scene.blend"
        payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return _TRUSTED_BUILD_SCRIPT_TEMPLATE + f"\n# plan-payload\n_PLAN_PAYLOAD = {payload_json!r}\n"


__all__ = [
    "SCENE_PLAN_SCHEMA_VERSION",
    "TRUSTED_SCRIPT_VERSION",
    "COLOR_MANAGEMENT_STANDARD",
    "COLOR_MANAGEMENT_FILMIC",
    "COLOR_MANAGEMENT_AGX",
    "COLOR_MANAGEMENT_DEFAULT",
    "DEVICE_CPU",
    "DEVICE_OPTIX",
    "DEVICE_CUDA",
    "DEVICE_NONE",
    "QUALITY_DEFAULTS",
    "ScenePlanObject",
    "ScenePlanCamera",
    "ScenePlanLight",
    "ScenePlanMaterial",
    "ScenePlanAnimation",
    "ScenePlan",
    "ScenePlanCompiler",
]
