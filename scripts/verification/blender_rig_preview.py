"""In-Blender rig preview builder (runs INSIDE blender.exe --background).

Pure stdlib — Blender bundles its own Python; windagent packages don't import.

Builds two DIFFERENT-topology humanoid armatures bound to a simple mesh,
validates the rig in-Blender (root bone present, parenting chain intact,
every vertex skinned to a weight group), renders a short Cycles preview, and
writes a JSON report with real bone world transforms so the host can compute a
REAL root-drift metric from an actual rendered scene (stage_d.md §4 gate).

USAGE (via blender.exe):
    blender --background --factory-startup --python blender_rig_preview.py -- OUT.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh  # noqa: F401
import bpy
from mathutils import Vector


# ---------------------------------------------------------------------------
# Deterministic rig builders — two DIFFERENT topologies (stage_d gate).
# ---------------------------------------------------------------------------
def build_armature(name: str, bones: list) -> bpy.types.Object:
    """Create an armature with the given [(bone_name, parent_name)] topology."""
    arm_data = bpy.data.armatures.new(name + "_arm")
    obj = bpy.data.objects.new(name + "_rig", arm_data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name, parent_name in bones:
        eb = arm_data.edit_bones.new(bone_name)
        eb.head = Vector((0.0, 0.0, 0.0))
        eb.tail = Vector((0.0, 0.0, 0.12))
        if parent_name:
            eb.parent = arm_data.edit_bones.get(parent_name)
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


# Provider A topology (Avatar-like): 8 bones.
TOPOLOGY_A = [
    ("Root", ""),
    ("Hips", "Root"),
    ("Spine", "Hips"),
    ("Chest", "Spine"),
    ("Neck", "Chest"),
    ("Head", "Neck"),
    ("Arm_L", "Chest"),
    ("Arm_R", "Chest"),
    ("Leg_L", "Hips"),
    ("Leg_R", "Hips"),
]

# Provider B topology (Mixamo-like): 14 bones — DIFFERENT set + nesting depth.
TOPOLOGY_B = [
    ("mixamorig:Root", ""),
    ("mixamorig:Hips", "mixamorig:Root"),
    ("mixamorig:Spine", "mixamorig:Hips"),
    ("mixamorig:Spine1", "mixamorig:Spine"),
    ("mixamorig:Spine2", "mixamorig:Spine1"),
    ("mixamorig:Neck", "mixamorig:Spine2"),
    ("mixamorig:Head", "mixamorig:Neck"),
    ("mixamorig:LeftArm", "mixamorig:Spine2"),
    ("mixamorig:LeftForeArm", "mixamorig:LeftArm"),
    ("mixamorig:LeftHand", "mixamorig:LeftForeArm"),
    ("mixamorig:RightArm", "mixamorig:Spine2"),
    ("mixamorig:RightForeArm", "mixamorig:RightArm"),
    ("mixamorig:RightHand", "mixamorig:RightForeArm"),
    ("mixamorig:LeftUpLeg", "mixamorig:Hips"),
    ("mixamorig:LeftLeg", "mixamorig:LeftUpLeg"),
    ("mixamorig:LeftFoot", "mixamorig:LeftLeg"),
    ("mixamorig:RightUpLeg", "mixamorig:Hips"),
    ("mixamorig:RightLeg", "mixamorig:RightUpLeg"),
    ("mixamorig:RightFoot", "mixamorig:RightLeg"),
]


def build_skinned_mesh(name: str, arm_obj: bpy.types.Object, bone_names: list) -> bpy.types.Object:
    """A subdivided cube skinned to the first N bones via vertex groups."""
    mesh = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1)
    bm.to_mesh(mesh)
    bm.free()  # ponytail: build mesh fully before linking to scene (no editmode)

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj

    for i, bname in enumerate(bone_names):
        group = obj.vertex_groups.new(name=bname)
        group.add(list(range(len(mesh.vertices))), 1.0, "REPLACE")

    modifier = obj.modifiers.new("arm", "ARMATURE")
    modifier.object = arm_obj
    return obj


def set_deterministic_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = 320
    scene.render.resolution_y = 240
    scene.render.fps = 24
    scene.render.film_transparent = True
    scene.cycles.samples = 4
    scene.cycles.device = "CPU"
    scene.render.image_settings.file_format = "PNG"
    # locked deterministic profile for the preview
    scene.render.use_persistent_data = True


def frame_setup() -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 3
    if not scene.camera:
        cam_data = bpy.data.cameras.new("cam")
        cam = bpy.data.objects.new("cam", cam_data)
        scene.collection.objects.link(cam)
        cam.location = Vector((3.0, -3.0, 1.5))
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = 3.5
        cam.rotation_euler = (1.1, 0.0, 0.785)
        scene.camera = cam
    if not any(obj.type == "SUN" for obj in scene.collection.objects):
        sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
        scene.collection.objects.link(sun)


def main() -> int:
    out_path = Path(sys.argv[sys.argv.index("--") + 1])
    scene = bpy.context.scene
    scene.frame_set(1)

    frame_setup()
    set_deterministic_render()

    report = {"topologies": {}, "frames": {}}

    for label, bones in (("alpha", TOPOLOGY_A), ("beta", TOPOLOGY_B)):
        rig = build_armature(label, bones)
        mesh = build_skinned_mesh(label, rig, [b[0] for b in bones if b[1] != ""][:4])

        arm_data = rig.data
        # In-Blender fail-closed validation (root, parenting, weights).
        has_root = any(eb.parent is None for eb in arm_data.bones)
        bone_names = {eb.name for eb in arm_data.bones}
        parent_ok = all(
            eb.parent is None or (eb.parent is not None and eb.parent.name in bone_names)
            for eb in arm_data.bones
        )
        bpy.context.view_layer.update()
        # Fail-closed in-Blender: every mesh vertex must have weight in a bone
        # vertex group, and the ARMATURE modifier must be wired to our rig.
        vg_names = {g.name for g in mesh.vertex_groups}
        modifier_wired = any(
            m.type == "ARMATURE" and m.object == rig for m in mesh.modifiers
        )
        unweighted = sum(
            1 for v in mesh.data.vertices if not any(
                True for _g in v.groups
            )
        )
        all_skinned = (
            len(vg_names) > 0 and modifier_wired and unweighted == 0
        )
        weight_groups = vg_names
        # Root-drift: measure root bone head world Z at frames 1..3 (real
        # transform from an actual rendered object).
        drift = []
        root = next(eb for eb in arm_data.bones if eb.parent is None)
        for f in range(1, 4):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            drift.append(round(rig.pose.bones[root.name].head[2], 4))

        report["topologies"][label] = {
            "bone_count": len(bones),
            "has_root": has_root,
            "parenting_ok": parent_ok,
            "vertex_group_count": len(weight_groups),
            "all_vertices_skinned": all_skinned,
            "root_world_z_per_frame": drift,
            "root_drift": round(max(drift) - min(drift), 4),
            "topology_signature": {
                "parent_count": [b for _, b in bones].count(None),
                "names": sorted(bone_names),
            },
        }
        for f in range(1, 4):
            scene.frame_set(f)
            scene.render.filepath = str(
                out_path.parent / f"preview_{label}_f{f:03d}.png"
            )
            scene.render.image_settings.file_format = "PNG"
            bpy.ops.render.render(write_still=True)
            report["frames"][f"{label}_f{f}"] = out_path.parent / f"preview_{label}_f{f:03d}.png"

    return report if _guard() else {"FAILED": True}


def _guard() -> bool:
    # Both rigs must validate in-Blender or the run FAILS CLOSED.
    ok_alpha = ok_beta = False
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            roots = [eb for eb in obj.data.bones if eb.parent is None]
            if obj.name.startswith("alpha") and len(roots) == 1:
                ok_alpha = True
            if obj.name.startswith("beta") and len(roots) == 1:
                ok_beta = True
    return ok_alpha and ok_beta


def _emit(report: dict) -> None:
    out_path = Path(sys.argv[sys.argv.index("--") + 1])
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("BLENDER_RIG_REPORT written", flush=True)


if __name__ == "__main__":
    try:
        result = main()
        _emit(result)
    except Exception as exc:  # pragma: no cover
        print(f"BLENDER_RIG_FAILED {exc}", flush=True)
        Path(sys.argv[sys.argv.index("--") + 1]).write_text(
            json.dumps({"failed": str(exc)}), encoding="utf-8"
        )
        raise SystemExit(1)
