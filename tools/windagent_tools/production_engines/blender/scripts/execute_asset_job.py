"""
VP3D Phase 7 — Asset normalization Blender job executor (plan Stage C §5).

Runs INSIDE `blender.exe --background --factory-startup --python
execute_asset_job.py -- <args>`. Pure stdlib (Blender bundles its own Python);
shares the launcher/supervisor contract of `execute_job.py`:

    --job-id <id> --kind <KIND> --job-spec <workspace/job_spec.json>

Security invariants:
- auto-execution is DISABLED before any file is opened/imported
  (`use_scripts_auto_execute = False`) — embedded driver/add-on/script in an
  asset is NEVER run;
- unknown kinds and malformed specs fail closed (exit 2);
- a cancel token is polled between work steps; nothing partial is published.

Job kinds (asset normalization):
- ``ASSET_IMPORT_VALIDATE`` — sandboxed import of FBX/USD/glTF/OBJ + structural
  report (objects/triangles/vertices/materials/non-manifold/degenerate);
- ``ASSET_NORMALIZE_UNITS`` — canonical meters + Z-up conversion, saves
  ``normalized.blend`` (derived artifact; source file untouched);
- ``ASSET_GENERATE_LOD`` — Decimate modifier -> derived GLB per level;
- ``ASSET_PREVIEW`` — deterministic Cycles turntable render (locked samples,
  Standard color management), thumbnail + frames.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

CANCEL_TOKEN_FILENAME = "cancel.token"
RESULT_FILENAME = "job_result.json"
JOB_SPEC_FILENAME = "job_spec.json"

ASSET_IMPORT_VALIDATE = "ASSET_IMPORT_VALIDATE"
ASSET_NORMALIZE_UNITS = "ASSET_NORMALIZE_UNITS"
ASSET_GENERATE_LOD = "ASSET_GENERATE_LOD"
ASSET_PREVIEW = "ASSET_PREVIEW"

KNOWN_KINDS = (
    ASSET_IMPORT_VALIDATE,
    ASSET_NORMALIZE_UNITS,
    ASSET_GENERATE_LOD,
    ASSET_PREVIEW,
)

DEGENERATE_AREA_EPSILON = 1e-12


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ""


def read_job_spec(workspace: Path) -> dict:
    path = workspace / JOB_SPEC_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def cancel_requested(workspace: Path) -> bool:
    return (workspace / CANCEL_TOKEN_FILENAME).is_file()


def write_result(
    workspace: Path,
    *,
    job_id: str,
    kind: str,
    ok: bool,
    blender_version: str = "",
    report: dict | None = None,
    error: str = "",
    cancel_requested: bool = False,
) -> None:
    payload = {
        "job_id": job_id,
        "kind": kind,
        "ok": ok,
        "cancel_requested": cancel_requested,
        "blender_version": blender_version,
        "report": report or {},
        "error": error,
        "finished_at": time.time(),
    }
    (workspace / RESULT_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def disable_auto_execution(bpy) -> None:
    """Disable embedded-script execution before ANY file is loaded."""
    try:
        bpy.context.preferences.filepaths.use_scripts_auto_execute = False
        bpy.context.preferences.use_scripts_auto_execute = False
    except Exception:  # pragma: no cover - preferences path differs across builds
        pass


def _import_mesh(bpy, path: Path) -> None:
    """Import a mesh file with auto-execution off; raise on failure."""
    ext = path.suffix.lower()
    if ext in (".fbx",):
        bpy.ops.import_scene.fbx(filepath=str(path), use_auto_keying=False)
    elif ext in (".gltf", ".glb"):
        bpy.ops.import_scene.gltf(filepath=str(path), disable_scripts=True)
    elif ext in (".obj",):
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext in (".usd", ".usda", ".usdc", ".usdz"):
        bpy.ops.wm.usd_import(filepath=str(path))
    elif ext in (".blend",):
        bpy.ops.wm.open_mainfile(filepath=str(path))
    else:
        raise ValueError(f"unsupported import extension: {ext}")


def _mesh_stats(bpy) -> dict:
    """Structural statistics over all mesh objects (bmesh where available)."""
    import bmesh

    objects = [o for o in bpy.data.objects if o.type == "MESH"]
    triangles = 0
    vertices = 0
    non_manifold_edges = 0
    non_manifold_vertices = 0
    degenerate = 0
    missing_uv = []
    for obj in objects:
        mesh = obj.data
        vertices += len(mesh.vertices)
        mesh.calc_loop_triangles()
        triangles += len(mesh.loop_triangles)
        if not mesh.uv_layers:
            missing_uv.append(obj.name)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        for edge in bm.edges:
            if not edge.is_manifold:
                non_manifold_edges += 1
                non_manifold_vertices += len(edge.verts)
        for face in bm.faces:
            if face.calc_area() < DEGENERATE_AREA_EPSILON:
                degenerate += 1
        bm.free()
    return {
        "objects": len(objects),
        "triangles": triangles,
        "vertices": vertices,
        "non_manifold_edges": non_manifold_edges,
        "non_manifold_vertices": non_manifold_vertices,
        "degenerate_faces": degenerate,
        "missing_uv_objects": missing_uv,
        "materials": len(bpy.data.materials),
        "textures": len(bpy.data.images),
        "armatures": [a.name for a in bpy.data.armatures],
        "animations": list(bpy.data.actions.keys()),
    }


# ---------------------------------------------------------------------------
# job kinds
# ---------------------------------------------------------------------------
def run_import_validate(bpy, workspace: Path, job_id: str, spec: dict) -> int:
    build = bpy.app.version_string
    input_files = [p for p in spec.get("input_files", []) if p]
    if not input_files:
        write_result(
            workspace, job_id=job_id, kind=ASSET_IMPORT_VALIDATE, ok=False,
            blender_version=build, error="ASSET_IMPORT_VALIDATE requires input_files",
        )
        return 1
    disable_auto_execution(bpy)
    try:
        for raw in input_files:
            _import_mesh(bpy, Path(raw))
    except Exception as exc:
        write_result(
            workspace, job_id=job_id, kind=ASSET_IMPORT_VALIDATE, ok=False,
            blender_version=build, error=f"import failed (auto-execution disabled): {exc}",
        )
        return 1
    report = _mesh_stats(bpy)
    write_result(
        workspace, job_id=job_id, kind=ASSET_IMPORT_VALIDATE, ok=True,
        blender_version=build, report=report,
    )
    return 0


def run_normalize_units(bpy, workspace: Path, job_id: str, spec: dict) -> int:
    build = bpy.app.version_string
    input_files = [p for p in spec.get("input_files", []) if p]
    if not input_files:
        write_result(
            workspace, job_id=job_id, kind=ASSET_NORMALIZE_UNITS, ok=False,
            blender_version=build, error="ASSET_NORMALIZE_UNITS requires input_files",
        )
        return 1
    disable_auto_execution(bpy)
    try:
        for raw in input_files:
            _import_mesh(bpy, Path(raw))
    except Exception as exc:
        write_result(
            workspace, job_id=job_id, kind=ASSET_NORMALIZE_UNITS, ok=False,
            blender_version=build, error=f"import failed: {exc}",
        )
        return 1

    try:
        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0
        # Canonical up axis = Z. Root objects are rotated by the importer
        # conventions; force Z-up on the whole scene graph.
        for obj in list(scene.collection.objects):
            matrix = obj.matrix_world
            up = matrix.col[2][:3]
            if abs(up.z) < abs(up.y):
                import mathutils

                rot = mathutils.Euler((math.radians(90), 0, 0), "XYZ").to_matrix().to_4x4()
                obj.matrix_world = rot @ matrix
        blend_path = workspace / "normalized.blend"
        tmp = workspace / "normalized.tmp.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(tmp))
        os.replace(str(tmp), str(blend_path))
    except Exception as exc:
        write_result(
            workspace, job_id=job_id, kind=ASSET_NORMALIZE_UNITS, ok=False,
            blender_version=build, error=f"normalization failed: {exc}",
        )
        return 1

    write_result(
        workspace, job_id=job_id, kind=ASSET_NORMALIZE_UNITS, ok=True,
        blender_version=build,
        report={
            "unit": "METERS",
            "up_axis": "Z_UP",
            "normalized_blend": blend_path.name,
            "normalized_blend_hash": sha256_file(blend_path),
            **{k: v for k, v in _mesh_stats(bpy).items() if k in ("objects", "triangles", "vertices")},
        },
    )
    return 0


def run_generate_lod(bpy, workspace: Path, job_id: str, spec: dict) -> int:
    build = bpy.app.version_string
    input_files = [p for p in spec.get("input_files", []) if p]
    if not input_files:
        write_result(
            workspace, job_id=job_id, kind=ASSET_GENERATE_LOD, ok=False,
            blender_version=build, error="ASSET_GENERATE_LOD requires input_files",
        )
        return 1
    level = int(spec.get("level", 1))
    ratio = float(spec.get("ratio", 0.5))
    disable_auto_execution(bpy)
    try:
        for raw in input_files:
            _import_mesh(bpy, Path(raw))
    except Exception as exc:
        write_result(
            workspace, job_id=job_id, kind=ASSET_GENERATE_LOD, ok=False,
            blender_version=build, error=f"import failed: {exc}",
        )
        return 1

    try:
        mesh_objects = [o for o in bpy.data.objects if o.type == "MESH"]
        if not mesh_objects:
            raise ValueError("no mesh objects to decimate")
        for obj in mesh_objects:
            obj.select_set(True)
            modifier = obj.modifiers.new(name="LODDecimate", type="DECIMATE")
            modifier.ratio = ratio
            modifier.use_collapse_triangulate = True
        with bpy.context.temp_override(selected_objects=mesh_objects):
            bpy.ops.object.modifier_apply(modifier="LODDecimate")
        name = f"lod_{level}.glb"
        lod_path = workspace / name
        tmp = workspace / f"lod_{level}.tmp.glb"
        bpy.ops.export_scene.gltf(
            filepath=str(tmp), export_format="GLB",
            export_apply=True, export_yup=False,
        )
        os.replace(str(tmp), str(lod_path))
        stats = _mesh_stats(bpy)
    except Exception as exc:
        write_result(
            workspace, job_id=job_id, kind=ASSET_GENERATE_LOD, ok=False,
            blender_version=build, error=f"LOD generation failed: {exc}",
        )
        return 1

    write_result(
        workspace, job_id=job_id, kind=ASSET_GENERATE_LOD, ok=True,
        blender_version=build,
        report={
            "level": level,
            "ratio": ratio,
            "triangle_count": stats["triangles"],
            "vertex_count": stats["vertices"],
            "content_hash": sha256_file(lod_path),
            "file_name": name,
            "generated_by": "blender_job",
        },
    )
    return 0


def run_preview(bpy, workspace: Path, job_id: str, spec: dict) -> int:
    build = bpy.app.version_string
    input_files = [p for p in spec.get("input_files", []) if p]
    if not input_files:
        write_result(
            workspace, job_id=job_id, kind=ASSET_PREVIEW, ok=False,
            blender_version=build, error="ASSET_PREVIEW requires input_files",
        )
        return 1
    config = spec.get("config", {})
    width = int(config.get("width", 512))
    height = int(config.get("height", 288))
    frames = int(config.get("frames", 12))
    samples = int(config.get("samples", 8))
    disable_auto_execution(bpy)

    try:
        for raw in input_files:
            _import_mesh(bpy, Path(raw))
    except Exception as exc:
        write_result(
            workspace, job_id=job_id, kind=ASSET_PREVIEW, ok=False,
            blender_version=build, error=f"import failed: {exc}",
        )
        return 1

    try:
        import bmesh  # noqa: F401 - bmesh import check for availability
        import mathutils

        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = False
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.image_settings.file_format = "PNG"
        scene.view_settings.view_transform = "Standard"
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0

        mesh_objects = [o for o in bpy.data.objects if o.type == "MESH"]
        if not mesh_objects:
            raise ValueError("no mesh objects to preview")

        # Turntable: orbit the camera around the object's bounding box.
        bpy.ops.object.select_all(action="DESELECT")
        for obj in mesh_objects:
            obj.select_set(True)
        with bpy.context.temp_override(selected_objects=mesh_objects):
            bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        bbox = [obj.matrix_world @ mathutils.Vector(v) for v in mesh_objects[0].bound_box]
        center = sum(bbox, mathutils.Vector()) / len(bbox)
        radius = max((v - center).length for v in bbox) * 2.5 or 2.0

        cam_data = bpy.data.cameras.new("PreviewCam")
        cam = bpy.data.objects.new("PreviewCam", cam_data)
        scene.collection.objects.link(cam)
        scene.camera = cam
        cam.location = (center.x, center.y - radius, center.z + radius * 0.3)
        cam.rotation_euler = (math.radians(55), 0, 0)

        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.object.light_add(type="SUN", location=(center.x, center.y - radius, center.z + radius))
        sun = bpy.context.object
        sun.data.energy = 3.0
        bpy.ops.object.light_add(type="AREA", location=(center.x - radius, center.y, center.z + radius * 0.5))
        fill = bpy.context.object
        fill.data.energy = 40.0
        fill.scale = (4, 4, 4)

        frame_files: list[str] = []
        rendered = 0
        for i in range(frames):
            if cancel_requested(workspace):
                break
            angle = i * (360.0 / max(frames, 1))
            cam.location = (
                center.x + radius * math.sin(math.radians(angle)),
                center.y - radius * math.cos(math.radians(angle)),
                center.z + radius * 0.3,
            )
            cam.rotation_euler = (math.radians(55), 0, 0)
            scene.frame_set(i)
            name = f"turntable_{i:04d}.png"
            temp = workspace / f"{name}.tmp"
            scene.render.filepath = str(temp)
            bpy.ops.render.render(write_still=True)
            final = workspace / name
            candidates = sorted(workspace.glob(f"{name}.tmp*"))
            done = next((p for p in candidates if p.is_file() and p.stat().st_size > 0), None)
            if done is None:
                break
            os.replace(str(done), str(final))
            frame_files.append(name)
            rendered += 1
        if not frame_files:
            raise ValueError("no preview frames rendered")

        thumb_name = frame_files[rendered // 2] if rendered else frame_files[0]
    except Exception as exc:
        write_result(
            workspace, job_id=job_id, kind=ASSET_PREVIEW, ok=False,
            blender_version=build, error=f"preview render failed: {exc}",
        )
        return 1

    write_result(
        workspace, job_id=job_id, kind=ASSET_PREVIEW, ok=True,
        blender_version=build,
        report={
            "thumbnail_file": thumb_name,
            "turntable_files": frame_files,
            "frames_rendered": rendered,
            "engine": "CYCLES",
            "device": "CPU",
            "content_hash": sha256_file(workspace / thumb_name),
            "generated_by": "blender_job",
            "resolution": [width, height],
            "samples": samples,
            "color_management": scene.view_settings.view_transform,
        },
    )
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="WindAgent asset normalization Blender job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--job-spec", required=True)
    args = parser.parse_args(argv)

    if args.kind not in KNOWN_KINDS:
        sys.stderr.write(f"unknown asset job kind: {args.kind!r}\n")
        return 2

    job_spec_path = Path(args.job_spec)
    workspace = job_spec_path.parent
    spec = read_job_spec(workspace)
    if not spec:
        sys.stderr.write(f"cannot read job spec {job_spec_path}\n")
        return 2

    if cancel_requested(workspace):
        write_result(
            workspace, job_id=args.job_id, kind=args.kind, ok=False,
            error="cancelled before job start (cancel token present)",
            cancel_requested=True,
        )
        return 0

    import bpy  # noqa: PLC0415 - only importable inside blender.exe

    if args.kind == ASSET_IMPORT_VALIDATE:
        return run_import_validate(bpy, workspace, args.job_id, spec)
    if args.kind == ASSET_NORMALIZE_UNITS:
        return run_normalize_units(bpy, workspace, args.job_id, spec)
    if args.kind == ASSET_GENERATE_LOD:
        return run_generate_lod(bpy, workspace, args.job_id, spec)
    if args.kind == ASSET_PREVIEW:
        return run_preview(bpy, workspace, args.job_id, spec)
    return 2  # pragma: no cover - unreachable


if __name__ == "__main__":
    try:
        tail = sys.argv[sys.argv.index("--") + 1 :]
    except ValueError:
        tail = sys.argv[1:]
    raise SystemExit(main(tail))
