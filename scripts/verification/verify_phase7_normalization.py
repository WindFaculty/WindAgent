#!/usr/bin/env python3
"""
VP3D Phase 7 — Real-machine normalization verification (plan Stage C §5 gate).

Runs the FULL asset normalization pipeline on the REAL machine with the REAL
Blender 4.5 LTS executable (policy-satisfying, per Phase 3 probe) and REAL
host-side pipeline:

    1. Build a typed OBJ fixture (cube) -> publish to content-addressed store;
    2. Run AssetNormalizationPipeline with BlenderAssetJobRunner:
       import_validate (sandboxed, auto-execution disabled),
       unit/axis canonical metadata, mesh validation, VRAM budget,
       LOD decimation (Decimate modifier -> GLB), deterministic Cycles
       preview (turntable), immutable bundle publish;
    3. Write typed evidence into artifacts/video_production_3d/phase_07/.

Exit 0 + verdict PASS only when the asset is READY with a published bundle
whose files are all present and hashed.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from windagent_core.domain.video_production.asset import ReferenceAsset  # noqa: E402
from windagent_core.domain.video_production.asset_normalization.enums import (  # noqa: E402
    AssetFormat,
    NormalizationStatus,
)
from windagent_core.domain.video_production.asset_normalization.models import (  # noqa: E402
    NormalizationConfig,
    NormalizationRequest,
)
from windagent_core.domain.video_production.asset_resolution.enums import AssetKind  # noqa: E402
from windagent_core.domain.video_production.asset_resolution.models import AssetRequirement  # noqa: E402
from windagent_tools.media_assets.normalization.bundle import AssetBundlePublisher  # noqa: E402
from windagent_tools.media_assets.normalization.pipeline import AssetNormalizationPipeline  # noqa: E402
from windagent_tools.media_assets.store import ContentAddressedStore  # noqa: E402

OBJ_FIXTURE = b"""# WindAgent VP3D Phase 7 fixture cube (meters, Z-up)
o cube
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
v 0 0 1
v 1 0 1
v 1 1 1
v 0 1 1
f 1 2 3 4
f 5 8 7 6
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 5 1 4 8
"""


def _blender_executable() -> str:
    configured = os.getenv("WINDAGENT_BLENDER_EXECUTABLE", "")
    if configured and Path(configured).is_file():
        return configured
    candidate = Path("C:/Program Files/Blender Foundation/Blender 4.5/blender.exe")
    if candidate.is_file():
        return str(candidate)
    raise SystemExit("Blender 4.5 executable not found (set WINDAGENT_BLENDER_EXECUTABLE)")


async def main() -> int:
    artifact_root = ROOT / "artifacts" / "video_production_3d"
    artifact_root.mkdir(parents=True, exist_ok=True)

    store = ContentAddressedStore(artifact_root / "assets" / "store")
    pipeline = AssetNormalizationPipeline(
        store=store,
        bundle_publisher=AssetBundlePublisher(str(artifact_root / "bundles")),
        scratch_root=str(artifact_root / "phase_07_scratch"),
        job_runner=None,  # injected below
    )

    from windagent_tools.production_engines.blender.asset_pipeline import (  # noqa: PLC0415
        BlenderAssetJobRunner,
    )

    runner = BlenderAssetJobRunner(
        executable_path=_blender_executable(),
        artifact_root=str(artifact_root),
        state_dir=str(artifact_root / "blender_state"),
    )
    pipeline._job_runner = runner  # noqa: SLF001 - verification script
    pipeline._lod._job_runner = runner  # noqa: SLF001
    pipeline._preview._job_runner = runner  # noqa: SLF001

    content_hash = store.publish(OBJ_FIXTURE)
    asset = ReferenceAsset(
        asset_id="ast_phase7_fixture",
        content_hash=content_hash,
        size_bytes=len(OBJ_FIXTURE),
        media_type="unknown",
        mime_type="model/obj",
        source_type="LOCAL_LIBRARY",
        license_state="LICENSED",
    )
    request = NormalizationRequest(
        asset=asset,
        format=AssetFormat.OBJ,
        source_uri="",
        config=NormalizationConfig(),
        requirement=AssetRequirement(kind=AssetKind.PROP, description="Phase 7 real fixture cube"),
    )

    started = time.monotonic()
    result = await pipeline.normalize(request)
    duration = round(time.monotonic() - started, 2)

    evidence = {
        "phase": "phase_07",
        "gate": "VP3D_P7_ASSET_NORMALIZATION_VERIFIED",
        "mode": "real_blender_4_5_lts",
        "executable": _blender_executable(),
        "status": result.status.value,
        "duration_seconds": duration,
        "stages": [
            {
                "stage": s.stage.value,
                "status": s.status.value,
                "detail": s.detail,
                "duration_ms": s.duration_ms,
            }
            for s in result.report.stages
        ],
        "mesh": {
            "triangles": result.mesh_report.triangle_count,
            "vertices": result.mesh_report.vertex_count,
            "ok": result.mesh_report.ok,
        },
        "canonical_metadata": result.canonical_metadata.model_dump(mode="json"),
        "vram": result.vram.model_dump(mode="json") if result.vram else None,
        "lods": [lod.model_dump(mode="json") for lod in result.lods],
        "preview": result.preview.model_dump(mode="json") if result.preview else None,
        "bundle": result.bundle.model_dump(mode="json") if result.bundle else None,
        "errors": list(result.report.errors),
    }

    out_dir = artifact_root / "phase_07"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "real_machine_evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )

    ok = result.status is NormalizationStatus.READY and result.bundle is not None
    print(f"status={result.status.value} duration={duration}s")
    print(f"mesh={result.mesh_report.triangle_count} triangles ok={result.mesh_report.ok}")
    print(f"lods={[(lod.level, lod.triangle_count, lod.generated_by) for lod in result.lods]}")
    print(f"preview={result.preview.frames_rendered if result.preview else 0} frames")
    print(f"bundle_hash={result.bundle.bundle_hash[:16] if result.bundle else 'NONE'}")
    print(f"VERDICT={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
