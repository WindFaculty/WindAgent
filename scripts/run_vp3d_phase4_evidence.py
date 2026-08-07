"""VP3D Phase 4 — REAL Blender smoke pipeline evidence driver.

Runs the full deterministic pipeline with the REAL blender 4.5.x LTS and REAL
ffmpeg/ffprobe binaries (never fake, never placeholder):

    COMPILE -> SAVE -> INSPECT -> RENDER_CHUNK -> ASSEMBLE -> VERIFY

Proves a valid .blend is produced, reopened/re-inspected, real PNG/EXR frames
are rendered (Cycles), and an MP4 is assembled by FFmpeg + verified by ffprobe.
Cancel/resume + deterministic reuse are exercised by `run_smoke`.

Exit code 0 + a populated phase_04_evidence.json == evidence produced.

Usage:
    python scripts/run_vp3d_phase4_evidence.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

# Ensure the repo root is importable as a namespace package (tests/ has no
# __init__.py; run standalone, not via pytest which adds rootdir itself).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

EVIDENCE_DIR = Path(os.environ.get("VP3D_EVIDENCE_DIR", "artifacts/video_production_3d/phase_04"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def main() -> None:
    from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir

    from windagent_tools.production_engines.blender.scene.pipeline import BlenderSmokePipeline
    from windagent_tools.production_engines.blender.runtime.launcher import BlenderJobLauncher
    from windagent_tools.production_engines.blender.runtime.supervisor import BlenderProcessSupervisor
    from windagent_tools.production_engines.blender.ffmpeg import (
        probe_ffmpeg_binaries,
        BlenderFfmpegRunner,
    )

    artifact_root = os.environ.get("VP3D_ARTIFACT_ROOT", "artifacts/video_production_3d")
    state_dir = os.path.join(artifact_root, "blender_state")

    launcher = BlenderJobLauncher(artifact_root=artifact_root)
    supervisor = BlenderProcessSupervisor(state_dir=state_dir, launcher=launcher)
    ffmpeg_version = probe_ffmpeg_binaries()
    ffmpeg = BlenderFfmpegRunner(version=ffmpeg_version)

    pipeline = BlenderSmokePipeline(
        artifact_root=artifact_root,
        state_dir=state_dir,
        launcher=launcher,
        supervisor=supervisor,
        ffmpeg_runner=ffmpeg,
    )

    # Resolve the REAL 4.5.x LTS blender via the SAME detector the composition
    # root uses (never a hard-coded path, fail-closed on policy).
    from windagent_tools.production_engines.blender.adapter import create_blender_engine_adapter

    adapter = create_blender_engine_adapter(artifact_root=artifact_root, state_dir=state_dir)
    readiness = await adapter.readiness()
    if not readiness.ready or readiness.validation is None:
        raise SystemExit(f"blender NOT ready for 4.5.x LTS policy: {readiness.reason}")
    executable_path = readiness.validation.executable_path

    ir = build_valid_ir()
    result = await pipeline.run_smoke(ir, executable_path=executable_path, run_label="real_p4")

    evidence = {
        "candidate_sha": os.environ.get("VP3D_CANDIDATE_SHA", ""),
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "blender_executable": executable_path,
        "blender_ready": readiness.ready,
        "ready_reason": readiness.reason,
        "ffmpeg_version": ffmpeg_version.to_dict(),
        "workspace": result.workspace,
        "scene_plan_path": result.scene_plan_path,
        "error": result.error,
        "job_outcomes": [
            {
                "job_id": o.job_id,
                "kind": o.kind,
                "state": o.state,
                "error": o.error,
                "reused": o.reused,
                "metadata": o.metadata,
            }
            for o in result.job_outcomes
        ],
        "artifacts": {
            str(Path(dirpath).joinpath(name).relative_to(result.workspace)).replace("\\", "/"): {
                "size_bytes": Path(dirpath).joinpath(name).stat().st_size,
                "sha256": sha256_file(Path(dirpath).joinpath(name)),
            }
            for dirpath, _dirs, files in os.walk(result.workspace)
            for name in files
        },
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "phase_04_evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=== VP3D Phase 4 REAL pipeline ===")
    print(f"blender : {executable_path}")
    print(f"ready   : {readiness.ready}  ({readiness.reason})")
    print(f"ffmpeg  : {ffmpeg_version.ffmpeg_path}")
    print(f"ffprobe : {ffmpeg_version.ffprobe_path}")
    for o in result.job_outcomes:
        print(f"  [{o.state}] {o.kind} {o.job_id}{' (reused)' if o.reused else ''}")
    if result.error:
        print(f"RESULT ERROR: {result.error[:300]}")
    print(f"evidence: {EVIDENCE_DIR / 'phase_04_evidence.json'}")
    return 0 if not result.error else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
