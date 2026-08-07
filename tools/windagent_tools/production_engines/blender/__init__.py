"""
Blender production engine adapter (VP3D Phase 3 — Blender Runtime Foundation).

Stack:

```text
BlenderEngineAdapter (ProductionEnginePort)
  ├── BlenderInstallationDetector     -> candidates with provenance
  ├── BlenderVersionValidator         -> policy-pinned 4.5.x LTS (fail closed)
  ├── BlenderCapabilityProbe/GpuProbe -> read-only capability & GPU enumeration
  ├── BlenderJobLauncher              -> argv-list, env allowlist, workspace gate
  ├── BlenderProcessSupervisor        -> PID/locator persist, heartbeat, cancel, recovery
  ├── BlenderExecutionReceipt         -> redacted argv, hashes, failure classification
  └── BlenderAddonManifest            -> add-on allowlist (REQUIRES_HUMAN_APPROVAL gate)
```

The real `blender.exe` path comes from config or the detector — NEVER a
hard-coded per-machine path. core/domain does not import this package.
"""

from windagent_tools.production_engines.blender.adapter import (
    BlenderEngineAdapter,
    BlenderEngineConfig,
    create_blender_engine_adapter,
)
from windagent_tools.production_engines.blender.validator import (
    BlenderVersionPolicy,
    BlenderVersionValidationResult,
    BlenderVersionValidator,
)
from windagent_tools.production_engines.blender.manifest import (
    APPROVED,
    REJECTED,
    REQUIRES_HUMAN_APPROVAL,
    AddonGateError,
    BlenderAddonDecision,
    BlenderAddonManifest,
    BlenderAddonRequest,
    BlenderAddonSpec,
)
from windagent_tools.production_engines.blender.runtime.detector import (
    BlenderInstallationCandidate,
    BlenderInstallationDetector,
)
from windagent_tools.production_engines.blender.runtime.capabilities import (
    BlenderCapabilityProbe,
    BlenderCapabilityReport,
    BlenderGpuDevice,
    BlenderGpuProbe,
    BlenderGpuProbeResult,
)
from windagent_tools.production_engines.blender.runtime.launcher import (
    BlenderJobError,
    BlenderJobLauncher,
    BlenderJobSpec,
)
from windagent_tools.production_engines.blender.runtime.supervisor import BlenderProcessSupervisor
from windagent_tools.production_engines.blender.runtime.receipts import (
    BlenderExecutionReceipt,
    BlenderFailureClassification,
    redact_argv,
)
from windagent_tools.production_engines.blender.ffmpeg import (
    BlenderFfmpegPort,
    BlenderFfmpegRunner,
    FfmpegReceipt,
    FfmpegResult,
    FfmpegVersion,
    SubprocessFfmpegPort,
    probe_ffmpeg_binaries,
)
from windagent_tools.production_engines.blender.scene.compiler import (
    DEVICE_CPU,
    DEVICE_CUDA,
    DEVICE_NONE,
    DEVICE_OPTIX,
    ScenePlan,
    ScenePlanAnimation,
    ScenePlanCamera,
    ScenePlanCompiler,
    ScenePlanLight,
    ScenePlanMaterial,
    ScenePlanObject,
)
from windagent_tools.production_engines.blender.scene.determinism import (
    DeterminismReport,
    RunSnapshot,
    compare_runs,
)
from windagent_tools.production_engines.blender.scene.frames import (
    FrameEntry,
    FrameManifest,
    cancel_requested,
    probe_dimensions,
    sha256_file,
)
from windagent_tools.production_engines.blender.scene.idempotency import (
    FRESH,
    INVALIDATE,
    NON_TERMINAL,
    REUSE,
    ArtifactReusePolicy,
    ReuseDecision,
    job_idempotency_key,
)
from windagent_tools.production_engines.blender.scene.pipeline import (
    BlenderSmokePipeline,
    JobOutcome,
    SmokeRunResult,
)

__all__ = [
    "APPROVED",
    "REJECTED",
    "REQUIRES_HUMAN_APPROVAL",
    "AddonGateError",
    "BlenderEngineAdapter",
    "BlenderEngineConfig",
    "create_blender_engine_adapter",
    "BlenderVersionPolicy",
    "BlenderVersionValidationResult",
    "BlenderVersionValidator",
    "BlenderAddonDecision",
    "BlenderAddonManifest",
    "BlenderAddonRequest",
    "BlenderAddonSpec",
    "BlenderInstallationCandidate",
    "BlenderInstallationDetector",
    "BlenderCapabilityProbe",
    "BlenderCapabilityReport",
    "BlenderGpuDevice",
    "BlenderGpuProbe",
    "BlenderGpuProbeResult",
    "BlenderJobLauncher",
    "BlenderProcessSupervisor",
    "BlenderExecutionReceipt",
    "BlenderFailureClassification",
    "redact_argv",
    "BlenderFfmpegPort",
    "BlenderFfmpegRunner",
    "FfmpegReceipt",
    "FfmpegResult",
    "FfmpegVersion",
    "SubprocessFfmpegPort",
    "probe_ffmpeg_binaries",
    "DEVICE_CPU",
    "DEVICE_CUDA",
    "DEVICE_NONE",
    "DEVICE_OPTIX",
    "ScenePlan",
    "ScenePlanAnimation",
    "ScenePlanCamera",
    "ScenePlanCompiler",
    "ScenePlanLight",
    "ScenePlanMaterial",
    "ScenePlanObject",
    "DeterminismReport",
    "RunSnapshot",
    "compare_runs",
    "FrameEntry",
    "FrameManifest",
    "cancel_requested",
    "probe_dimensions",
    "sha256_file",
    "FRESH",
    "INVALIDATE",
    "NON_TERMINAL",
    "REUSE",
    "ArtifactReusePolicy",
    "ReuseDecision",
    "job_idempotency_key",
    "BlenderSmokePipeline",
    "JobOutcome",
    "SmokeRunResult",
]

