"""
VP3D Phase 3 — Blender capability & GPU probes (plan Stage B §3 backlog 3-4).

`BlenderCapabilityProbe` runs a READ-ONLY blender python expression that
prints a JSON capability report: build, bundled Python, Cycles devices,
import/export operators and video codecs. Parsing is fail-closed: malformed
or unexpected output never raises — it yields a typed probe failure.

`BlenderGpuProbe` classifies GPU readiness from the enumerated Cycles devices.
It NEVER claims GPU-ready unless a CUDA/OptiX/METAL device actually
enumerated: an empty device list is CPU-only, not GPU-ready.
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from windagent_tools.production_engines.blender.runtime.process import (
    BlenderProcessPort,
    SubprocessBlenderProcess,
)

CAPABILITY_PROBE_TIMEOUT_SECONDS = 60.0
GPU_BACKENDS = ("OPTIX", "CUDA", "METAL")


# The read-only blender --python-expr payload. It prints a single JSON object.
# Kept as a module constant so the exact probe is auditable and version-frozen.
PROBE_SCRIPT = r"""
import sys, json
out = {"build": "", "python": "", "cycles_compute": "NONE", "cycles_devices": [],
       "importers": [], "exporters": [], "codecs": []}
try:
    import bpy
    out["build"] = bpy.app.version_string
except Exception as exc:
    out["probe_error"] = f"bpy unavailable: {exc}"
    print(json.dumps(out))
    sys.exit(0)
out["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
# `--factory-startup` does NOT load the Cycles add-on, so it must be enabled
# before device enumeration — otherwise GPU discovery is always empty.
try:
    if "cycles" not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module="cycles")
    prefs = bpy.context.preferences.addons["cycles"].preferences
    # Force the compute backend so Cycles populates its device list (an empty
    # device list then genuinely means CPU-only — fail closed).
    for backend in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            break
        except Exception:
            continue
    out["cycles_compute"] = getattr(prefs, "compute_device_type", "NONE")
    try:
        devices = getattr(prefs, "devices", None)
        if devices is None or len(devices) == 0:
            devices = prefs.get_devices() or []
        out["cycles_devices"] = [{"name": d.name, "type": d.type,
                                  "compute": getattr(d, "compute_component_type", "")}
                                 for d in devices]
    except Exception:
        out["cycles_devices"] = []
except Exception:
    pass
for cat, names in (("importers", "import_"), ("exporters", "export_")):
    for name in ("gltf", "fbx", "usd", "usdz", "obj", "stl"):
        try:
            if hasattr(getattr(bpy.ops, cat + "_" + name, None), "POLL"):
                out[cat].append(cat.replace("_", "") + "_" + name)
        except Exception:
            continue
for codec in ("ffmpeg_video_h264", "ffmpeg_video_h265", "ffmpeg_video_vp9",
              "png", "exr", "jpeg"):
    try:
        if hasattr(bpy.ops.image, codec) or codec in dir(bpy.ops):
            out["codecs"].append(codec)
    except Exception:
        continue
print(json.dumps(out))
"""


@dataclass(frozen=True)
class BlenderGpuDevice:
    """One enumerated Cycles device."""

    name: str
    device_type: str = ""  # CUDA | OPTIX | CPU | METAL | ...
    compute_component_type: str = ""

    @property
    def is_gpu(self) -> bool:
        return self.device_type.upper() in GPU_BACKENDS

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "device_type": self.device_type,
            "compute_component_type": self.compute_component_type,
        }


@dataclass(frozen=True)
class BlenderCapabilityReport:
    """Parsed capability report from the read-only probe."""

    executable_path: str
    build: str = ""
    python_version: str = ""
    cycles_compute: str = "NONE"
    cycles_devices: List[BlenderGpuDevice] = field(default_factory=list)
    importers: List[str] = field(default_factory=list)
    exporters: List[str] = field(default_factory=list)
    codecs: List[str] = field(default_factory=list)
    probe_error: str = ""
    raw_stdout_chars: int = 0

    @property
    def parsed_ok(self) -> bool:
        return not self.probe_error and bool(self.build)

    def to_dict(self) -> dict:
        return {
            "executable_path": self.executable_path,
            "build": self.build,
            "python_version": self.python_version,
            "cycles_compute": self.cycles_compute,
            "cycles_devices": [d.to_dict() for d in self.cycles_devices],
            "importers": self.importers,
            "exporters": self.exporters,
            "codecs": self.codecs,
            "probe_error": self.probe_error,
            "parsed_ok": self.parsed_ok,
            "raw_stdout_chars": self.raw_stdout_chars,
        }


def _extract_json_object(raw: str):
    """Extract the first JSON object from a text blob (banner + JSON).

    Returns the parsed payload, or None when no object can be parsed — the
    caller fails closed on None.
    """
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start : idx + 1])
                except (ValueError, TypeError):
                    return None
    return None


class BlenderCapabilityProbe:
    """Runs the read-only capability probe against a validated executable."""

    def __init__(
        self,
        *,
        process_port: Optional[BlenderProcessPort] = None,
        timeout_seconds: float = CAPABILITY_PROBE_TIMEOUT_SECONDS,
    ) -> None:
        self._process = process_port or SubprocessBlenderProcess()
        self._timeout = timeout_seconds

    async def probe(self, executable_path: str) -> BlenderCapabilityReport:
        argv = [
            executable_path,
            "--background",
            "--factory-startup",
            "--python-expr",
            PROBE_SCRIPT,
        ]
        result = await self._process.run(argv, timeout_seconds=self._timeout)
        raw = result.stdout
        report = BlenderCapabilityReport(
            executable_path=executable_path,
            raw_stdout_chars=len(raw),
        )
        if result.start_failed or result.timed_out or result.returncode != 0:
            report = BlenderCapabilityReport(
                executable_path=executable_path,
                probe_error=(
                    result.stderr[:500]
                    or f"probe process failed: rc={result.returncode}"
                ),
                raw_stdout_chars=len(raw),
            )
            return report

        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            # Real blender.exe prints a banner/log line before the JSON payload
            # (e.g. 'Blender 5.1.2', 'Read prefs: ...'). Extract the FIRST JSON
            # object in stdout; fail closed if none can be found.
            payload = _extract_json_object(raw)
        if payload is None:
            return BlenderCapabilityReport(
                executable_path=executable_path,
                probe_error=(
                    "capability probe returned no parseable JSON object "
                    f"(stdout {len(raw)} chars)"
                ),
                raw_stdout_chars=len(raw),
            )

        if not isinstance(payload, dict):
            return BlenderCapabilityReport(
                executable_path=executable_path,
                probe_error="capability probe returned a non-object payload",
                raw_stdout_chars=len(raw),
            )
        if payload.get("probe_error"):
            return BlenderCapabilityReport(
                executable_path=executable_path,
                probe_error=str(payload["probe_error"]),
                raw_stdout_chars=len(raw),
            )

        devices = []
        for device in payload.get("cycles_devices", []) or []:
            if not isinstance(device, dict):
                continue
            devices.append(
                BlenderGpuDevice(
                    name=str(device.get("name", "")),
                    device_type=str(device.get("type", "")),
                    compute_component_type=str(device.get("compute", "")),
                )
            )
        return BlenderCapabilityReport(
            executable_path=executable_path,
            build=str(payload.get("build", "")),
            python_version=str(payload.get("python", "")),
            cycles_compute=str(payload.get("cycles_compute", "NONE")),
            cycles_devices=devices,
            importers=[str(x) for x in payload.get("importers", []) or []],
            exporters=[str(x) for x in payload.get("exporters", []) or []],
            codecs=[str(x) for x in payload.get("codecs", []) or []],
            raw_stdout_chars=len(raw),
        )


@dataclass(frozen=True)
class BlenderGpuProbeResult:
    """GPU readiness classification from the enumerated Cycles devices."""

    gpu_ready: bool
    backend: str = "NONE"  # OPTIX | CUDA | METAL | NONE
    gpu_devices: List[BlenderGpuDevice] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "gpu_ready": self.gpu_ready,
            "backend": self.backend,
            "gpu_devices": [d.to_dict() for d in self.gpu_devices],
            "reason": self.reason,
        }


class BlenderGpuProbe:
    """Classify GPU readiness from a capability report (fail closed)."""

    def classify(self, report: BlenderCapabilityReport) -> BlenderGpuProbeResult:
        if not report.parsed_ok:
            return BlenderGpuProbeResult(
                gpu_ready=False,
                reason=f"capability probe failed: {report.probe_error or 'unparsed'}",
            )
        gpu_devices = [d for d in report.cycles_devices if d.is_gpu]
        if not gpu_devices:
            return BlenderGpuProbeResult(
                gpu_ready=False,
                reason="no CUDA/OptiX/Metal device enumerated by Cycles; CPU-only",
            )
        backend = gpu_devices[0].device_type.upper()
        if backend == "OPTIX":
            backend = "OPTIX"
        return BlenderGpuProbeResult(
            gpu_ready=True,
            backend=backend,
            gpu_devices=gpu_devices,
            reason=f"{len(gpu_devices)} GPU device(s) enumerated",
        )


__all__ = [
    "CAPABILITY_PROBE_TIMEOUT_SECONDS",
    "GPU_BACKENDS",
    "PROBE_SCRIPT",
    "BlenderGpuDevice",
    "BlenderCapabilityReport",
    "BlenderCapabilityProbe",
    "BlenderGpuProbeResult",
    "BlenderGpuProbe",
]
