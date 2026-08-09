"""Run the VP3D Phase 19 one-frame real-Blender verification lane.

The script is intentionally argument-driven: it never hard-codes a machine
Blender path. It probes OptiX/CUDA/CPU, compiles a neutral RenderIntent into a
versioned BlenderRenderProfile, renders one small PNG through the trusted job
executor, and persists the profile, cache identity, frame manifest, raw
telemetry, execution receipt, and gate evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import time
from pathlib import Path

from windagent_core.domain.video_production.ids import (
    RenderIntentId,
    RenderProfileId,
    SceneDescriptionId,
)
from windagent_core.domain.video_production.production_ir.enums import (
    IrAssetFormat,
    RenderQuality,
)
from windagent_core.domain.video_production.production_ir.models import (
    RenderIntent,
    RenderProfile,
)
from windagent_tools.production_engines.blender.rendering import (
    CPU_FALLBACK_DENY,
    DEVICE_AUTO,
    PROFILE_PREVIEW,
    BlenderCyclesDeviceSelector,
    BlenderRenderProfileCompiler,
    build_render_cache_key,
)
from windagent_tools.production_engines.blender.runtime.capabilities import (
    BlenderCapabilityProbe,
)
from windagent_tools.production_engines.blender.runtime.launcher import (
    BlenderJobLauncher,
    BlenderJobSpec,
)


GATE = "VP3D_P19_CYCLES_RENDERER_VERIFIED"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _intent(width: int, height: int, samples: int) -> RenderIntent:
    profile = RenderProfile(
        profile_id=RenderProfileId("rp_p19_preview"),
        quality=RenderQuality.PREVIEW,
        engine_hint="cycles",
        samples=samples,
        resolution={"width": width, "height": height},
        denoise=True,
        adaptive_sampling=True,
        output_format=IrAssetFormat.PNG,
        frame_rate=24,
        metadata={
            "blender_profile": PROFILE_PREVIEW,
            "adaptive_threshold": 0.1,
            "motion_blur": False,
            "seed": 1919,
        },
    )
    return RenderIntent(
        intent_id=RenderIntentId("ri_p19_smoke"),
        scene_id=SceneDescriptionId("scn_p19_smoke"),
        profile=profile,
        frame_start=1,
        frame_end=1,
    )


async def _run(args) -> tuple[dict, int]:
    executable = Path(args.blender_executable).resolve()
    source_blend = Path(args.source_blend).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not executable.is_file():
        raise FileNotFoundError(f"Blender executable not found: {executable}")
    if not source_blend.is_file():
        raise FileNotFoundError(f"source .blend not found: {source_blend}")

    capability = await BlenderCapabilityProbe().probe(str(executable))
    selection = BlenderCyclesDeviceSelector().select(
        capability,
        requested_device=DEVICE_AUTO,
        cpu_fallback_policy=CPU_FALLBACK_DENY,
    )
    scene_hash = _sha256_file(source_blend)
    intent = _intent(args.width, args.height, args.samples)
    profile = BlenderRenderProfileCompiler().compile(
        intent,
        device=selection.selected_device,
        dependency_hashes={"scene_blend": scene_hash},
    )
    cache_key = build_render_cache_key(
        scene_hash=scene_hash,
        shot_hash=hashlib.sha256(b"phase19-smoke-shot").hexdigest(),
        frame_start=1,
        frame_end=1,
        profile=profile,
        blender_version=capability.build,
        device_class=selection.selected_device,
    )

    run_id = hashlib.sha256(
        f"{cache_key}:{time.time_ns()}".encode("utf-8")
    ).hexdigest()[:10]
    workspace = output_dir / f"workspace_{run_id}"
    workspace.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source_blend, workspace / "scene.blend")

    job_id = f"ej_p19_{run_id}"
    payload = {
        "kind": "RENDER_CHUNK",
        "ir_hash": hashlib.sha256(
            json.dumps(intent.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "frame_start": 1,
        "frame_end": 1,
        "extension": profile.extension,
        "resolution": dict(profile.resolution),
        "render_profile": profile.to_dict(),
        "render_profile_hash": profile.profile_hash(),
        "render_cache_key": cache_key,
        "device_selection": selection.to_dict(),
    }
    root = Path(__file__).resolve().parents[2]
    spec = BlenderJobSpec(
        job_id=job_id,
        kind="RENDER_CHUNK",
        executable_path=str(executable),
        script_path=str(
            root
            / "tools"
            / "windagent_tools"
            / "production_engines"
            / "blender"
            / "scripts"
            / "execute_job.py"
        ),
        job_workspace=str(workspace),
        spec_payload=payload,
        timeout_seconds=float(args.timeout_seconds),
        idempotency_key=cache_key,
    )
    process_result, receipt = await BlenderJobLauncher(
        artifact_root=str(output_dir)
    ).launch(spec)

    result_path = workspace / "job_result.json"
    manifest_path = workspace / "frame_manifest.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {}
    )
    telemetry = (result.get("report") or {}).get("telemetry") or {}
    frames = manifest.get("frames") or []
    frame_path = workspace / str(frames[0].get("filename", "")) if frames else workspace / "missing"
    checks = {
        "process_exit_zero": process_result.returncode == 0,
        "job_result_ok": bool(result.get("ok")),
        "one_frame_published": len(frames) == 1 and frame_path.is_file(),
        "frame_nonempty": frame_path.is_file() and frame_path.stat().st_size > 0,
        "frame_hash_matches": (
            frame_path.is_file()
            and str(frames[0].get("sha256", "")) == _sha256_file(frame_path)
        ) if frames else False,
        "dimensions_match": (
            int(frames[0].get("width", 0)) == args.width
            and int(frames[0].get("height", 0)) == args.height
        ) if frames else False,
        "actual_device_matches": telemetry.get("actual_device") == selection.selected_device,
        "frame_telemetry_present": len(telemetry.get("frames") or []) == 1,
        "profile_hash_pinned": manifest.get("render_profile_hash") == profile.profile_hash(),
        "cache_key_pinned": manifest.get("render_cache_key") == cache_key,
        "preview_artifact_class_pinned": manifest.get("artifact_class") == "PREVIEW",
    }
    passed = all(checks.values())

    _write_json(output_dir / "device_probe.json", capability.to_dict())
    _write_json(output_dir / "render_profile.json", profile.to_dict())
    _write_json(
        output_dir / "render_cache_identity.json",
        {
            "cache_key": cache_key,
            "scene_hash": scene_hash,
            "frame_range": [1, 1],
            "profile_hash": profile.profile_hash(),
            "blender_version": capability.build,
            "device_class": selection.selected_device,
            "artifact_class": profile.artifact_class,
            "dependency_hashes": profile.dependency_hashes,
        },
    )
    _write_json(output_dir / "raw_render_telemetry.json", telemetry)
    _write_json(output_dir / "execution_receipt.json", receipt.to_dict())
    evidence = {
        "phase": "phase_19",
        "gate": GATE,
        "gate_passed": passed,
        "run_id": run_id,
        "workspace": str(workspace.relative_to(root)).replace("\\", "/"),
        "profile": profile.name,
        "profile_hash": profile.profile_hash(),
        "render_cache_key": cache_key,
        "requested_device": selection.requested_device,
        "actual_device": telemetry.get("actual_device", ""),
        "device_verdict": selection.to_dict(),
        "output_format": profile.output_format,
        "frame": (
            {
                **frames[0],
                "path": str(frame_path.relative_to(root)).replace("\\", "/"),
            }
            if frames
            else {}
        ),
        "telemetry": telemetry,
        "checks": checks,
    }
    _write_json(output_dir / "real_render_evidence.json", evidence)
    return evidence, 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender-executable", required=True)
    parser.add_argument("--source-blend", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    args = parser.parse_args()
    evidence, exit_code = asyncio.run(_run(args))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

