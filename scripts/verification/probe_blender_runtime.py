"""
VP3D Phase 3 — Real Blender runtime probe (plan Stage B §3 gate).

Runs the DETECTOR + VALIDATOR + capability/GPU PROBES against the REAL
machine (baseline: RTX 5060, Windows). On this machine the installed Blender
is 5.1 (NOT the pinned 4.5 LTS), so the probe is expected to:

- detect the real install with provenance;
- REJECT it against the 4.5.x LTS policy (fail-closed typed readiness);
- still capture the raw capability/GPU report so hardware readiness is
  documented even when the version gate blocks jobs.

Usage:

    uv run python scripts/verification/probe_blender_runtime.py \
        [--artifact-root artifacts] [--out <probe_output.json>]

Exit code 0 when the probe machinery ran (detection + policy evaluation
completed), regardless of whether the machine is policy-ready — the READY
verdict is in the JSON output. Exit code 2 on probe machinery failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from windagent_tools.production_engines.blender import (
    BlenderCapabilityProbe,
    BlenderGpuProbe,
    BlenderInstallationDetector,
    BlenderVersionValidator,
    create_blender_engine_adapter,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Blender runtime probe (VP3D Phase 3)")
    parser.add_argument("--artifact-root", default="artifacts")
    parser.add_argument("--out", default="")
    parser.add_argument("--configured-path", default="", help="optional explicit blender.exe path")
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    evidence_dir = artifact_root / "video_production_3d" / "phase_03"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "probe_name": "blender_runtime",
        "phase": "phase_03",
        "gate": "VP3D_P3_BLENDER_RUNTIME_VERIFIED",
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "configured_path": args.configured_path or None,
        "candidates": [],
        "validations": [],
        "capability": None,
        "gpu": None,
        "readiness": {"ready": False, "reason": "not evaluated"},
    }

    detector = BlenderInstallationDetector(configured_path=args.configured_path or None)
    validator = BlenderVersionValidator()
    capability_probe = BlenderCapabilityProbe()
    gpu_probe = BlenderGpuProbe()

    candidates = detector.detect()
    report["candidates"] = [c.to_dict() for c in candidates]
    report["validations"] = [validator.validate(c).to_dict() for c in candidates]

    ready = validator.first_ready(candidates)
    if ready is None:
        report["readiness"] = {
            "ready": False,
            "reason": "no candidate satisfies pinned 4.5.x LTS policy (fail closed)",
            "policy": "4.5.x LTS",
        }
    else:
        report["readiness"]["ready"] = True
        report["readiness"]["reason"] = (
            f"Blender {ready.major}.{ready.minor}.{ready.patch} satisfies policy"
        )

    # Still probe capabilities of the FIRST detected candidate (hardware
    # documentation even when the version gate blocks job launch).
    if candidates:
        try:
            capability = await capability_probe.probe(candidates[0].executable_path)
            report["capability"] = capability.to_dict()
            report["gpu"] = gpu_probe.classify(capability).to_dict()
        except Exception as exc:  # pragma: no cover - probe machinery must not die
            report["capability"] = {"probe_error": str(exc)}

    # Also run the full adapter readiness (composes detector+validator+probe).
    adapter = create_blender_engine_adapter(
        artifact_root=str(artifact_root),
        state_dir=str(evidence_dir / "blender_state"),
        executable_path=args.configured_path or None,
    )
    try:
        adapter_readiness = await adapter.readiness()
        report["adapter_readiness"] = adapter_readiness.to_dict()
    except Exception as exc:  # pragma: no cover
        report["adapter_readiness"] = {"error": str(exc)}

    out_path = Path(args.out) if args.out else evidence_dir / "blender_runtime_probe.json"
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Probe written to {out_path}")
    print(f"Readiness: ready={report['readiness']['ready']} ({report['readiness']['reason']})")
    if report["gpu"]:
        print(
            "GPU: "
            f"ready={report['gpu']['gpu_ready']} backend={report['gpu']['backend']} "
            f"({report['gpu']['reason']})"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(2)
