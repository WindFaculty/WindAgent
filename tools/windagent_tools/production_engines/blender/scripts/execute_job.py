"""
VP3D Phase 3+4 — Trusted headless Blender job executor (plan Stage B §3-§4).

Runs INSIDE `blender.exe --background --factory-startup --python execute_job.py
-- <args>`. It is deliberately PURE STDLIB: Blender bundles its own Python and
windagent packages are NOT importable there.

Contract with `BlenderJobLauncher` (argv after the trailing ``--``):

    --job-id <id> --kind <KIND> --job-spec <workspace/job_spec.json>

Behavior:

- reads the TYPED job spec JSON the launcher wrote (``job_spec.json``);
- polls ``<workspace>/cancel.token`` between work steps and aborts cleanly
  (exit 0, ``cancel_requested=true``) the moment it appears;
- writes ``<workspace>/job_result.json`` with a typed result;
- exit code 0 == job fulfilled, non-zero == job failed.

Phase 3: ``PROBE`` implemented (reports build + job machinery proof).

Phase 4 (deterministic scene smoke test):

- ``COMPILE``      — execs the pinned trusted build script (written next to
                     scene_plan.json by the compiler), saves ``scene.blend``.
- ``SAVE``         — re-saves the opened scene.blend (idempotent save proof).
- ``INSPECT``      — reopens scene.blend and reports objects/camera/lights/
                     material/keyframes (create -> save -> reopen proof).
- ``RENDER_CHUNK`` — renders frames [start..end] to PNG/EXR via the ATOMIC
                     temp -> validated final -> manifest path; polls cancel
                     token between frames; resume starts at the first frame
                     missing from the manifest (plan §4 items 3-4).
- ``ASSEMBLE`` / ``VERIFY`` — HOST-SIDE jobs (FFmpeg/ffprobe). They fail
  closed here with a clear message; the pipeline runs them through
  `BlenderFfmpegRunner` (Blender never renders MP4 directly).

The manifest JSON contract is shared with the host-side `FrameManifest`
(scene/frames.py): {frame_range, extension, frames:[{frame, filename, sha256,
width, height, size_bytes}]}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

CANCEL_TOKEN_FILENAME = "cancel.token"
RESULT_FILENAME = "job_result.json"
JOB_SPEC_FILENAME = "job_spec.json"
FRAME_MANIFEST_FILENAME = "frame_manifest.json"
TEMP_SUFFIX = ".tmp"
FRAME_NAME_TEMPLATE = "frame_{frame:04d}.{ext}"

PROBE = "PROBE"
COMPILE = "COMPILE"
SAVE = "SAVE"
INSPECT = "INSPECT"
RENDER_CHUNK = "RENDER_CHUNK"
ASSEMBLE = "ASSEMBLE"
VERIFY = "VERIFY"

KNOWN_KINDS = (PROBE, COMPILE, SAVE, INSPECT, RENDER_CHUNK, ASSEMBLE, VERIFY)

# Host-side kinds: never dispatched to a blender.exe job (fail closed here).
HOST_SIDE_KINDS = (ASSEMBLE, VERIFY)


# ---------------------------------------------------------------------------
# Cancel token
# ---------------------------------------------------------------------------
def cancel_requested(workspace: Path) -> bool:
    return (workspace / CANCEL_TOKEN_FILENAME).is_file()


def wait_for_cancel(workspace: Path, interval: float = 0.2) -> bool:
    """Sleep-poll the cancel token; returns True when cancel was requested."""
    while not cancel_requested(workspace):
        time.sleep(interval)
    return True


# ---------------------------------------------------------------------------
# Result writer
# ---------------------------------------------------------------------------
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
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Shared helpers (pure stdlib)
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ""


def read_job_spec(workspace: Path) -> dict | None:
    path = workspace / JOB_SPEC_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _load_manifest(workspace: Path) -> dict:
    path = workspace / FRAME_MANIFEST_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("frames", [])
    return data


def _save_manifest(workspace: Path, manifest: dict) -> None:
    (workspace / FRAME_MANIFEST_FILENAME).write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def _validated_frames(workspace: Path) -> set[int]:
    manifest = _load_manifest(workspace)
    valid: set[int] = set()
    for entry in manifest.get("frames", []):
        try:
            frame = int(entry["frame"])
            filename = str(entry["filename"])
        except (KeyError, TypeError, ValueError):
            continue
        if (workspace / filename).is_file():
            valid.add(frame)
    return valid


def _finalize_frame_atomic(workspace: Path, frame: int, extension: str) -> dict | None:
    """Move frame_XXXX.ext.tmp -> frame_XXXX.ext and register in the manifest.

    Blender appends the detected format extension to an extensionless/runtime
    temp filepath (real 4.5.x behaviour): writing to
    ``frame_XXXX.ext.tmp`` lands on disk as ``frame_XXXX.ext.tmp.png``. So the
    finalize locates the written temp by glob (*.tmp*) rather than asserting
    an exact filename — otherwise real renders are never finalized (temp is
    "missing" -> nothing published -> spurious cancel). See plan §4 item 4.

    Returns the manifest entry, or None when no temp file is found/empty
    (NOTHING is published — cancel-safe).
    """
    base = FRAME_NAME_TEMPLATE.format(frame=frame, ext=extension)
    temps = sorted(workspace.glob(f"{base}.tmp*"))
    temp = next((t for t in temps if t.is_file() and t.stat().st_size > 0), None)
    if temp is None:
        # Housekeep an empty temp if it exists.
        for t in temps:
            t.unlink(missing_ok=True)
        return None
    final = workspace / base
    os.replace(str(temp), str(final))  # atomic on same filesystem
    entry = {
        "frame": frame,
        "filename": final.name,
        "sha256": sha256_file(final),
        "width": 0,
        "height": 0,
        "size_bytes": final.stat().st_size if final.is_file() else 0,
    }
    manifest = _load_manifest(workspace)
    manifest.setdefault("frame_range", [])
    manifest["frames"] = [e for e in manifest["frames"] if e.get("frame") != frame]
    manifest["frames"].append(entry)
    _save_manifest(workspace, manifest)
    return entry


# ---------------------------------------------------------------------------
# Job kinds
# ---------------------------------------------------------------------------
def run_probe(workspace: Path, job_id: str) -> int:
    """Report the Blender build and prove the job machinery end-to-end."""
    build = ""
    try:
        import bpy

        build = bpy.app.version_string
    except Exception as exc:  # pragma: no cover - bpy is always present in blender
        build = f"<bpy unavailable: {exc}>"

    report = {
        "build": build,
        "job_spec_read": (workspace / JOB_SPEC_FILENAME).is_file(),
        "cancel_token_present_at_start": cancel_requested(workspace),
    }
    write_result(
        workspace,
        job_id=job_id,
        kind=PROBE,
        ok=True,
        blender_version=build,
        report=report,
    )
    return 0


def run_compile(workspace: Path, job_id: str, job_spec: dict) -> int:
    """Compile scene_plan.json -> scene.blend via the PINNED trusted script."""
    build = ""
    try:
        import bpy

        build = bpy.app.version_string
    except Exception as exc:  # pragma: no cover
        build = f"<bpy unavailable: {exc}>"

    script_path = workspace / "build_scene.py"
    plan_path = workspace / "scene_plan.json"
    if not script_path.is_file() or not plan_path.is_file():
        write_result(
            workspace,
            job_id=job_id,
            kind=COMPILE,
            ok=False,
            error=(
                f"COMPILE requires build_scene.py + scene_plan.json in the "
                f"workspace (missing script={script_path.is_file()}, "
                f"plan={plan_path.is_file()})"
            ),
        )
        return 1

    try:
        source = script_path.read_text(encoding="utf-8")
        # Exec the pinned trusted script in blender's namespace (bpy exists).
        namespace: dict = {"__name__": "__main__"}
        exec(compile(source, str(script_path), "exec"), namespace)
    except Exception as exc:
        write_result(
            workspace,
            job_id=job_id,
            kind=COMPILE,
            ok=False,
            blender_version=build,
            error=f"trusted build script failed: {exc}",
        )
        return 1

    blend_path = workspace / "scene.blend"
    report = {
        "blend_saved": blend_path.is_file(),
        "blend_hash": sha256_file(blend_path) if blend_path.is_file() else "",
        "blend_size_bytes": blend_path.stat().st_size if blend_path.is_file() else 0,
    }
    ok = bool(report["blend_saved"])
    write_result(
        workspace,
        job_id=job_id,
        kind=COMPILE,
        ok=ok,
        blender_version=build,
        report=report,
        error="" if ok else "scene.blend was not produced by the build script",
    )
    return 0 if ok else 1


def run_save(workspace: Path, job_id: str) -> int:
    """Re-save the opened scene.blend (idempotent save proof)."""
    build = ""
    try:
        import bpy

        build = bpy.app.version_string
    except Exception as exc:  # pragma: no cover
        build = f"<bpy unavailable: {exc}>"

    blend_path = workspace / "scene.blend"
    if not blend_path.is_file():
        write_result(
            workspace,
            job_id=job_id,
            kind=SAVE,
            ok=False,
            error="SAVE requires an existing scene.blend in the workspace",
        )
        return 1
    try:
        import bpy

        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        # Save to a temp name then atomically replace (idempotent + crash-safe).
        tmp_path = workspace / "scene.save.tmp.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(tmp_path))
        os.replace(str(tmp_path), str(blend_path))
    except Exception as exc:
        write_result(
            workspace,
            job_id=job_id,
            kind=SAVE,
            ok=False,
            blender_version=build,
            error=f"SAVE failed: {exc}",
        )
        return 1

    write_result(
        workspace,
        job_id=job_id,
        kind=SAVE,
        ok=True,
        blender_version=build,
        report={"blend_hash": sha256_file(blend_path)},
    )
    return 0


def run_inspect(workspace: Path, job_id: str) -> int:
    """Reopen scene.blend and report objects/camera/lights/material/keyframes."""
    build = ""
    report: dict = {}
    try:
        import bpy

        build = bpy.app.version_string
        blend_path = workspace / "scene.blend"
        if not blend_path.is_file():
            raise FileNotFoundError("scene.blend missing")
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        mesh_objects = [o for o in bpy.data.objects if o.type == "MESH"]
        cameras = [o for o in bpy.data.objects if o.type == "CAMERA"]
        lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
        materials = [m for m in bpy.data.materials]
        animated = [
            o.name for o in bpy.data.objects if o.animation_data is not None
        ]
        report = {
            "mesh_objects": len(mesh_objects),
            "cameras": len(cameras),
            "lights": len(lights),
            "materials": len(materials),
            "animated_objects": animated,
            "camera_names": [c.name for c in cameras],
            "light_names": [l.name for l in lights],
            "material_names": [m.name for m in materials],
        }
    except Exception as exc:
        write_result(
            workspace,
            job_id=job_id,
            kind=INSPECT,
            ok=False,
            blender_version=build,
            error=f"INSPECT failed: {exc}",
        )
        return 1

    write_result(
        workspace,
        job_id=job_id,
        kind=INSPECT,
        ok=True,
        blender_version=build,
        report=report,
    )
    return 0


def run_render_chunk(workspace: Path, job_id: str, job_spec: dict) -> int:
    """Render frames [start..end] atomically, cancel-safe, resume-aware."""
    build = ""
    try:
        import bpy

        build = bpy.app.version_string
    except Exception as exc:  # pragma: no cover
        build = f"<bpy unavailable: {exc}>"

    try:
        frame_start = int(job_spec["frame_start"])
        frame_end = int(job_spec["frame_end"])
    except (KeyError, TypeError, ValueError):
        write_result(
            workspace,
            job_id=job_id,
            kind=RENDER_CHUNK,
            ok=False,
            error="RENDER_CHUNK requires frame_start/frame_end in the job spec",
        )
        return 1
    extension = str(job_spec.get("extension", "png"))
    resolution = job_spec.get("resolution") or {}

    blend_path = workspace / "scene.blend"
    if not blend_path.is_file():
        write_result(
            workspace,
            job_id=job_id,
            kind=RENDER_CHUNK,
            ok=False,
            error="RENDER_CHUNK requires scene.blend in the workspace",
        )
        return 1

    try:
        import bpy

        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        if resolution:
            bpy.context.scene.render.resolution_x = int(resolution.get("width", 0)) or bpy.context.scene.render.resolution_x
            bpy.context.scene.render.resolution_y = int(resolution.get("height", 0)) or bpy.context.scene.render.resolution_y
        bpy.context.scene.render.image_settings.file_format = (
            "PNG" if extension.lower() == "png" else "OPEN_EXR"
        )
    except Exception as exc:
        write_result(
            workspace,
            job_id=job_id,
            kind=RENDER_CHUNK,
            ok=False,
            blender_version=build,
            error=f"failed to open scene for render: {exc}",
        )
        return 1

    # Resume: skip frames already validated (manifest + file present).
    validated = _validated_frames(workspace)
    pending = [f for f in range(frame_start, frame_end + 1) if f not in validated]

    rendered: list[int] = []
    cancelled = False
    for frame in pending:
        if cancel_requested(workspace):
            cancelled = True
            break
        temp = workspace / (FRAME_NAME_TEMPLATE.format(frame=frame, ext=extension) + TEMP_SUFFIX)
        try:
            bpy.context.scene.frame_set(frame)
            bpy.context.scene.render.filepath = str(temp)
            bpy.ops.render.render(write_still=True)
        except Exception as exc:
            write_result(
                workspace,
                job_id=job_id,
                kind=RENDER_CHUNK,
                ok=False,
                blender_version=build,
                error=f"render failed at frame {frame}: {exc}",
            )
            return 1
        entry = _finalize_frame_atomic(workspace, frame, extension)
        if entry is None:
            # temp was missing/empty -> nothing published (cancel-safe)
            cancelled = True
            break
        rendered.append(frame)

    report = {
        "frame_start": frame_start,
        "frame_end": frame_end,
        "rendered_frames": rendered,
        "cancelled": cancelled,
        "resumed_from_validated": sorted(validated),
        "frame_count": len(_validated_frames(workspace)),
    }
    write_result(
        workspace,
        job_id=job_id,
        kind=RENDER_CHUNK,
        ok=not cancelled,
        blender_version=build,
        report=report,
        cancel_requested=cancelled,
        error="" if not cancelled else "cancelled mid-chunk; partial frames discarded",
    )
    return 0 if not cancelled else 0  # cancel is a CLEAN stop, exit 0


def run_host_side(workspace: Path, job_id: str, kind: str) -> int:
    """ASSEMBLE/VERIFY run on the HOST (FFmpeg/ffprobe), never inside Blender."""
    write_result(
        workspace,
        job_id=job_id,
        kind=kind,
        ok=False,
        error=(
            f"job kind {kind!r} is host-side (FFmpeg/ffprobe); the pipeline "
            f"dispatches it through BlenderFfmpegRunner, never blender.exe"
        ),
    )
    return 1


# ---------------------------------------------------------------------------
# Entry point (runs inside blender.exe)
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="WindAgent trusted Blender job executor")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--job-spec", required=True)
    args = parser.parse_args(argv)

    if args.kind not in KNOWN_KINDS:
        # Unknown kind — refuse (fail closed), never invent behavior.
        sys.stderr.write(f"unknown job kind: {args.kind!r}\n")
        return 2

    job_spec_path = Path(args.job_spec)
    workspace = job_spec_path.parent
    job_spec = read_job_spec(workspace)
    if job_spec is None:
        sys.stderr.write(f"cannot read job spec {job_spec_path}\n")
        return 2

    if cancel_requested(workspace):
        write_result(
            workspace,
            job_id=args.job_id,
            kind=args.kind,
            ok=False,
            error="cancelled before job start (cancel token present)",
            cancel_requested=True,
        )
        return 0

    if args.kind == PROBE:
        return run_probe(workspace, args.job_id)
    if args.kind == COMPILE:
        return run_compile(workspace, args.job_id, job_spec)
    if args.kind == SAVE:
        return run_save(workspace, args.job_id)
    if args.kind == INSPECT:
        return run_inspect(workspace, args.job_id)
    if args.kind == RENDER_CHUNK:
        return run_render_chunk(workspace, args.job_id, job_spec)
    if args.kind in HOST_SIDE_KINDS:
        return run_host_side(workspace, args.job_id, args.kind)
    return run_not_implemented(workspace, args.job_id, args.kind)


def run_not_implemented(workspace: Path, job_id: str, kind: str) -> int:
    write_result(
        workspace,
        job_id=job_id,
        kind=kind,
        ok=False,
        error=f"job kind {kind!r} is not implemented",
    )
    return 1


if __name__ == "__main__":
    # Blender appends blender's own args before the trailing `--`; take only
    # the args AFTER `--` (exactly what the launcher appended).
    try:
        tail = sys.argv[sys.argv.index("--") + 1 :]
    except ValueError:
        tail = sys.argv[1:]
    raise SystemExit(main(tail))
