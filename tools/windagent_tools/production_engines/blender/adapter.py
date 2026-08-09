"""
VP3D Phase 3 — BlenderEngineAdapter (plan Stage B §3).

`BlenderEngineAdapter` implements `ProductionEnginePort` for Blender. It
composes the Phase 3 runtime stack:

```text
BlenderEngineAdapter (ProductionEnginePort)
  ├── BlenderInstallationDetector      -> candidates with provenance
  ├── BlenderVersionValidator          -> policy-pinned 4.5.x LTS (fail closed)
  ├── BlenderCapabilityProbe/GpuProbe  -> read-only capability & GPU enumeration
  ├── BlenderAddonManifest             -> add-on allowlist (REQUIRES_HUMAN_APPROVAL)
  ├── BlenderJobLauncher               -> argv-list, env allowlist, workspace gate
  └── BlenderProcessSupervisor         -> PID/locator persist, heartbeat, cancel
```

Rules honored here:

- NO job launches unless the executable satisfies the pinned 4.5.x LTS policy
  (fail closed) — a 5.x or 4.6 install yields a typed NOT_READY receipt.
- NO job launches when an add-on referenced by the IR metadata is outside the
  allowlist (`REQUIRES_HUMAN_APPROVAL`) — the gate runs BEFORE process start.
- Every submission returns a typed `EngineJobReceipt`; every published
  artifact is a `DerivedArtifact` carrying the IR content hash it derives
  from (storage invalidation uses that hash).
- The real blender path comes from config or the detector — NEVER a
  hard-coded per-machine path.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional

from windagent_core.domain.video_production.ids import (
    DerivedArtifactId,
    EngineJobId,
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    EngineJobStatus,
    IrAssetFormat,
)
from windagent_core.domain.video_production.production_ir.models import (
    DerivedArtifact,
    EngineJobReceipt,
    RenderIntent,
    SceneDescription,
    ShotExecutionIntent,
)
from windagent_tools.production_engines.blender.manifest import (
    AddonGateError,
    BlenderAddonManifest,
    BlenderAddonRequest,
)
from windagent_tools.production_engines.blender.runtime.capabilities import (
    BlenderCapabilityProbe,
    BlenderCapabilityReport,
    BlenderGpuProbe,
    BlenderGpuProbeResult,
)
from windagent_tools.production_engines.blender.runtime.detector import (
    BlenderInstallationCandidate,
    BlenderInstallationDetector,
)
from windagent_tools.production_engines.blender.runtime.launcher import (
    BlenderJobError,
    BlenderJobLauncher,
    BlenderJobSpec,
)
from windagent_tools.production_engines.blender.runtime.process import BlenderProcessPort
from windagent_tools.production_engines.blender.runtime.supervisor import (
    STATE_CANCELLED,
    STATE_COMPLETED,
    STATE_FAILED,
    BlenderProcessSupervisor,
)
from windagent_tools.production_engines.blender.runtime.receipts import (
    BlenderExecutionReceipt,
    BlenderFailureClassification,
)
from windagent_tools.production_engines.blender.rendering import (
    CPU_FALLBACK_DENY,
    DEVICE_AUTO,
    BlenderCyclesDeviceSelector,
    BlenderRenderProfileCompiler,
    RenderDevicePolicyError,
    RenderProfileCompileError,
    build_render_cache_key,
)
from windagent_tools.production_engines.blender.render_jobs import (
    RenderJobPolicy,
)
from windagent_tools.production_engines.blender.technical_review import (
    PreRenderReviewer,
    TechnicalReviewPolicy,
)
from windagent_tools.production_engines.blender.vram_budget import (
    SceneResourceManifest,
    VramBudgetDecision,
    VramBudgetPolicy,
    VramMitigationPlanner,
)
from windagent_tools.production_engines.blender.validator import (
    BlenderVersionPolicy,
    BlenderVersionValidationResult,
    BlenderVersionValidator,
)

logger = logging.getLogger("windagent_tools.production_engines.blender")

# Job kinds the executor understands (Phase 3 runtime + Phase 4 pipeline).
JOB_KIND_PROBE = "PROBE"
JOB_KIND_COMPILE = "COMPILE"
JOB_KIND_SAVE = "SAVE"
JOB_KIND_INSPECT = "INSPECT"
JOB_KIND_RENDER_CHUNK = "RENDER_CHUNK"
JOB_KIND_ASSEMBLE = "ASSEMBLE"
JOB_KIND_VERIFY = "VERIFY"

# Metadata keys the adapter reads from IR model metadata (engine-neutral).
META_ADDONS = "addons"  # list of {"module_id","version","sha256"}
META_OUTPUT_FORMAT = "output_format"


@dataclass(frozen=True)
class BlenderEngineConfig:
    """Composition settings for the Blender engine adapter."""

    artifact_root: str
    state_dir: str
    executable_path: Optional[str] = None
    addon_manifest: Optional[BlenderAddonManifest] = None
    policy: BlenderVersionPolicy = field(default_factory=BlenderVersionPolicy)
    heartbeat_seconds: float = 5.0
    cancel_grace_seconds: float = 10.0
    default_timeout_seconds: float = 300.0
    requested_cycles_device: str = DEVICE_AUTO
    cpu_fallback_policy: str = CPU_FALLBACK_DENY
    vram_budget_policy: Optional[VramBudgetPolicy] = None
    render_job_policy: Optional[RenderJobPolicy] = None
    technical_review_policy: Optional[TechnicalReviewPolicy] = None


@dataclass(frozen=True)
class BlenderRuntimeReadiness:
    """Typed readiness outcome of the Blender runtime on this machine."""

    ready: bool
    reason: str
    candidate: Optional[BlenderInstallationCandidate] = None
    validation: Optional[BlenderVersionValidationResult] = None
    capability: Optional[BlenderCapabilityReport] = None
    gpu: Optional[BlenderGpuProbeResult] = None

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "reason": self.reason,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "capability": self.capability.to_dict() if self.capability else None,
            "gpu": self.gpu.to_dict() if self.gpu else None,
        }


class BlenderEngineAdapter:
    """ProductionEnginePort implementation backed by the Blender runtime."""

    engine_name = "blender"

    def __init__(
        self,
        *,
        config: BlenderEngineConfig,
        detector: Optional[BlenderInstallationDetector] = None,
        validator: Optional[BlenderVersionValidator] = None,
        capability_probe: Optional[BlenderCapabilityProbe] = None,
        gpu_probe: Optional[BlenderGpuProbe] = None,
        render_profile_compiler: Optional[BlenderRenderProfileCompiler] = None,
        device_selector: Optional[BlenderCyclesDeviceSelector] = None,
        process_port: Optional[BlenderProcessPort] = None,
    ) -> None:
        self._config = config
        self._artifact_root = Path(config.artifact_root).resolve()
        self._state_dir = Path(config.state_dir).resolve()
        self._state_dir.mkdir(parents=True, exist_ok=True)

        self._detector = detector or BlenderInstallationDetector(
            configured_path=config.executable_path
        )
        self._validator = validator or BlenderVersionValidator(policy=config.policy)
        self._capability_probe = capability_probe or BlenderCapabilityProbe(
            process_port=process_port
        )
        self._gpu_probe = gpu_probe or BlenderGpuProbe()
        self._render_profile_compiler = (
            render_profile_compiler or BlenderRenderProfileCompiler()
        )
        self._device_selector = device_selector or BlenderCyclesDeviceSelector()
        self._manifest = config.addon_manifest or BlenderAddonManifest.empty()

        self._launcher = BlenderJobLauncher(
            artifact_root=str(self._artifact_root),
            process_port=process_port,
        )
        self._supervisor = BlenderProcessSupervisor(
            state_dir=str(self._state_dir),
            launcher=self._launcher,
            heartbeat_seconds=config.heartbeat_seconds,
            cancel_grace_seconds=config.cancel_grace_seconds,
        )

    # ------------------------------------------------------------------
    # Runtime readiness
    # ------------------------------------------------------------------
    async def readiness(self) -> BlenderRuntimeReadiness:
        """Detect + validate + probe. NEVER reports ready on an unvalidated install."""
        candidates = self._detector.detect()
        if not candidates:
            return BlenderRuntimeReadiness(
                ready=False,
                reason="no blender executable detected (configured path, PATH, standard locations, registry)",
            )

        ready = self._validator.first_ready(candidates)
        if ready is None:
            reasons = []
            for candidate in candidates:
                validation = self._validator.validate(candidate)
                reasons.append(f"{candidate.executable_path}: {validation.reason}")
            return BlenderRuntimeReadiness(
                ready=False,
                reason="no candidate satisfies the pinned 4.5.x LTS policy: "
                + " | ".join(reasons),
                candidate=candidates[0],
                validation=self._validator.validate(candidates[0]),
            )

        # Validated — now probe capabilities + GPU (read-only).
        capability = await self._capability_probe.probe(ready.executable_path)
        gpu = self._gpu_probe.classify(capability)
        return BlenderRuntimeReadiness(
            ready=capability.parsed_ok,
            reason=(
                f"Blender {ready.major}.{ready.minor}.{ready.patch} ready; "
                f"GPU {'ready (' + gpu.backend + ')' if gpu.gpu_ready else 'CPU-only'}"
                if capability.parsed_ok
                else f"capability probe failed: {capability.probe_error}"
            ),
            candidate=ready and self._first_candidate_with_path(candidates, ready.executable_path),
            validation=ready,
            capability=capability,
            gpu=gpu,
        )

    @staticmethod
    def _first_candidate_with_path(candidates, executable_path):
        for candidate in candidates:
            if candidate.executable_path == executable_path:
                return candidate
        return candidates[0] if candidates else None

    # ------------------------------------------------------------------
    # IR helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _ir_hash(*units) -> str:
        """Stable content hash over the IR units a job derives from."""
        canonical = json.dumps(
            [u.model_dump(mode="json") for u in units],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _addon_requests_from(metadata: Dict) -> List[BlenderAddonRequest]:
        """Read add-on requests from engine-neutral IR metadata (fail closed)."""
        requests = []
        for entry in metadata.get(META_ADDONS, []) or []:
            if not isinstance(entry, dict):
                continue
            requests.append(
                BlenderAddonRequest(
                    module_id=str(entry.get("module_id", "")),
                    version=str(entry.get("version") or ""),
                    sha256=str(entry.get("sha256") or None),
                )
            )
        return requests

    def _gate_addons(self, metadata: Dict) -> None:
        """Raise AddonGateError when a referenced add-on is not allowlisted."""
        requests = self._addon_requests_from(metadata)
        if not requests:
            return
        self._manifest.ensure_all_approved(requests)

    # ------------------------------------------------------------------
    # Job construction
    # ------------------------------------------------------------------
    async def _resolve_ready_executable(self) -> tuple[Optional[str], Optional[BlenderRuntimeReadiness]]:
        """Resolve the policy-ready executable; returns (path, readiness).

        The readiness result is returned so callers reuse the SAME probe
        instead of re-running detection + a blender spawn on the failure path.
        """
        readiness = await self.readiness()
        if not readiness.ready or readiness.validation is None:
            return None, readiness
        return readiness.validation.executable_path, readiness

    def _build_spec(
        self,
        *,
        job_id: str,
        kind: str,
        executable_path: str,
        payload: dict,
        timeout_seconds: float,
    ) -> BlenderJobSpec:
        job_workspace = str(self._artifact_root / "blender_jobs" / job_id)
        return BlenderJobSpec(
            job_id=job_id,
            kind=kind,
            executable_path=executable_path,
            script_path=str(
                Path(__file__).resolve().parent / "scripts" / "execute_job.py"
            ),
            job_workspace=job_workspace,
            spec_payload=payload,
            timeout_seconds=timeout_seconds,
            idempotency_key=(
                str(payload.get("render_cache_key") or "")
                or f"{kind}:{payload.get('ir_hash', '')}"
            ),
        )

    @classmethod
    def _unit_hash(cls, unit) -> str:
        """Stable hash for one IR unit used by the Phase 19 cache identity."""
        return cls._ir_hash(unit)

    @staticmethod
    def _resolved_frame_end(render: RenderIntent, units: tuple) -> int:
        if render.frame_end >= render.frame_start:
            return render.frame_end
        shot = next((unit for unit in units if isinstance(unit, ShotExecutionIntent)), None)
        if shot is not None and shot.duration_seconds > 0:
            return max(
                render.frame_start,
                render.frame_start
                + int(round(shot.duration_seconds * render.profile.frame_rate))
                - 1,
            )
        return render.frame_start

    def _run_vram_gate(self, manifest_data: Dict, blender_profile) -> VramBudgetDecision:
        """Estimate + mitigate + verdict for a neutral resource manifest.

        Render-buffer footprint comes from the COMPILED profile resolution so
        the gate always matches what Blender will actually render.
        """
        manifest = SceneResourceManifest.from_dict(manifest_data)
        resolution = blender_profile.resolution
        buffers = manifest.render_buffers
        if buffers.width <= 0 or buffers.height <= 0:
            manifest = replace(
                manifest,
                render_buffers=replace(
                    buffers,
                    width=int(resolution.get("width", 0)),
                    height=int(resolution.get("height", 0)),
                ),
            )
        return VramMitigationPlanner().plan(manifest, self._config.vram_budget_policy)

    # ------------------------------------------------------------------
    # ProductionEnginePort
    # ------------------------------------------------------------------
    async def submit_scene(
        self, scene: SceneDescription, render: RenderIntent
    ) -> EngineJobReceipt:
        return await self._submit(
            kind=JOB_KIND_COMPILE,
            units=(scene, render),
            project_id=scene.metadata.get("project_id"),
            revision_id=scene.metadata.get("revision_id"),
            render=render,
        )

    async def submit_shot(
        self, intent: ShotExecutionIntent, render: RenderIntent
    ) -> EngineJobReceipt:
        return await self._submit(
            kind=JOB_KIND_RENDER_CHUNK,
            units=(intent, render),
            project_id=intent.metadata.get("project_id"),
            revision_id=intent.metadata.get("revision_id"),
            render=render,
        )

    async def _submit(
        self,
        *,
        kind: str,
        units: tuple,
        project_id,
        revision_id,
        render: RenderIntent,
    ) -> EngineJobReceipt:
        job_id = EngineJobId.generate(prefix="ej")
        ir_hash = self._ir_hash(*units)

        # 1. Version policy gate (fail closed) — before ANY launch.
        executable_path, readiness = await self._resolve_ready_executable()
        if executable_path is None:
            return EngineJobReceipt(
                job_id=job_id,
                project_id=project_id or VideoProjectId("vp_unknown"),
                revision_id=revision_id or ProductionRevisionId("rev_unknown"),
                ir_hash=ir_hash,
                status=EngineJobStatus.FAILED,
                engine_name=self.engine_name,
                error=f"blender runtime NOT ready: {readiness.reason}",
                metadata={"gate": "version_policy", "job_kind": kind},
            )

        # 2. Add-on allowlist gate (fail closed) — before process start.
        try:
            self._gate_addons(render.metadata)
        except AddonGateError as exc:
            return EngineJobReceipt(
                job_id=job_id,
                project_id=project_id or VideoProjectId("vp_unknown"),
                revision_id=revision_id or ProductionRevisionId("rev_unknown"),
                ir_hash=ir_hash,
                status=EngineJobStatus.FAILED,
                engine_name=self.engine_name,
                error=f"add-on gate blocked job: {exc}",
                metadata={"gate": "addon_allowlist", "job_kind": kind},
            )

        # 3. Compile the neutral RenderIntent at the adapter boundary. Device
        # selection is fail-closed: CPU fallback is never implicit.
        capability = readiness.capability if readiness is not None else None
        try:
            if capability is None:
                raise RenderDevicePolicyError("capability report missing")
            requested_device = str(
                render.profile.metadata.get(
                    "cycles_device", self._config.requested_cycles_device
                )
            )
            device_selection = self._device_selector.select(
                capability,
                requested_device=requested_device,
                cpu_fallback_policy=self._config.cpu_fallback_policy,
            )
            dependency_hashes = render.metadata.get("dependency_hashes", {})
            blender_profile = self._render_profile_compiler.compile(
                render,
                device=device_selection.selected_device,
                dependency_hashes=dependency_hashes,
            )
        except (RenderDevicePolicyError, RenderProfileCompileError) as exc:
            return EngineJobReceipt(
                job_id=job_id,
                project_id=project_id or VideoProjectId("vp_unknown"),
                revision_id=revision_id or ProductionRevisionId("rev_unknown"),
                ir_hash=ir_hash,
                status=EngineJobStatus.FAILED,
                engine_name=self.engine_name,
                error=f"render profile/device gate blocked job: {exc}",
                metadata={
                    "gate": "render_profile_device_policy",
                    "job_kind": kind,
                    "cpu_fallback_policy": self._config.cpu_fallback_policy,
                },
            )

        # 3.5 VRAM budget gate (Phase 20) — block BEFORE launch with a typed
        # recommendation when the calibrated estimate exceeds the hard limit
        # even after the mitigation chain. No data = no gate (estimation needs
        # a resource manifest), no blind crash/retry when blocked.
        scene = next((unit for unit in units if isinstance(unit, SceneDescription)), None)
        vram_decision = None
        if self._config.vram_budget_policy is not None:
            manifest_data = render.metadata.get("resource_manifest") or {}
            if not manifest_data and scene is not None:
                manifest_data = scene.metadata.get("resource_manifest") or {}
            if manifest_data:
                vram_decision = self._run_vram_gate(manifest_data, blender_profile)
                if vram_decision.blocked:
                    return EngineJobReceipt(
                        job_id=job_id,
                        project_id=project_id or VideoProjectId("vp_unknown"),
                        revision_id=revision_id or ProductionRevisionId("rev_unknown"),
                        ir_hash=ir_hash,
                        status=EngineJobStatus.FAILED,
                        engine_name=self.engine_name,
                        error=f"vram budget gate blocked job: {vram_decision.recommendation}",
                        metadata={
                            "gate": "vram_budget",
                            "job_kind": kind,
                            "vram_budget_decision": vram_decision.to_dict(),
                        },
                    )

        frame_end = self._resolved_frame_end(render, units)
        shot = next((unit for unit in units if isinstance(unit, ShotExecutionIntent)), None)

        # 3.55 Phase 22 technical review gate (Stage K §3 pre-render) - a
        # BLOCKING deterministic finding (missing object/texture, broken rig,
        # frame range, camera/character collision, lighting, audio timing,
        # unapproved asset/add-on, VRAM budget) stops render submission
        # BEFORE launch. No manifest = no gate (review needs scene data).
        review_result = None
        if self._config.technical_review_policy is not None:
            review_manifest = render.metadata.get("review_manifest") or {}
            if not review_manifest and scene is not None:
                review_manifest = scene.metadata.get("review_manifest") or {}
            if review_manifest:
                review_result = PreRenderReviewer(
                    self._config.technical_review_policy
                ).review(review_manifest)
                if review_result.blocked:
                    return EngineJobReceipt(
                        job_id=job_id,
                        project_id=project_id or VideoProjectId("vp_unknown"),
                        revision_id=revision_id or ProductionRevisionId("rev_unknown"),
                        ir_hash=ir_hash,
                        status=EngineJobStatus.FAILED,
                        engine_name=self.engine_name,
                        error=(
                            "technical review gate blocked job: "
                            + "; ".join(
                                f.code for f in review_result.findings
                                if f.severity == "BLOCKING"
                            )
                        ),
                        metadata={
                            "gate": "technical_review",
                            "job_kind": kind,
                            "review_findings": [
                                f.to_dict() for f in review_result.findings
                            ],
                        },
                    )

        # 3.6 Phase 21 render-job plan: chunk the resolved frame range when a
        # recovery policy is configured. Unmeasured renders get ONE honest
        # chunk; measured timing sizes chunks via the scheduler. A resume
        # offset from recovery metadata narrows the first chunk.
        job_plan = None
        if self._config.render_job_policy is not None:
            scheduler = self._config.render_job_policy.scheduler
            chunk_size = self._config.render_job_policy.chunk_size
            if chunk_size is None:
                chunk_size = frame_end - render.frame_start + 1
            try:
                ranges = scheduler.plan_chunks(
                    render.frame_start, frame_end, chunk_size
                )
                job_plan = [{"frame_start": s, "frame_end": e} for s, e in ranges]
            except Exception:
                job_plan = None
            resume_from = int(render.metadata.get("resume_from") or 0)
            if resume_from and job_plan:
                job_plan[0]["resume_from"] = max(
                    resume_from, job_plan[0]["frame_start"]
                )

        scene_hash = (
            self._unit_hash(scene)
            if scene is not None
            else str(render.metadata.get("scene_hash") or "")
        )
        if not scene_hash:
            scene_hash = hashlib.sha256(str(render.scene_id).encode("utf-8")).hexdigest()
        shot_hash = self._unit_hash(shot) if shot is not None else ""
        blender_version = (
            capability.build
            or (readiness.validation.version_line if readiness.validation else "")
        )
        render_cache_key = build_render_cache_key(
            scene_hash=scene_hash,
            shot_hash=shot_hash,
            frame_start=render.frame_start,
            frame_end=frame_end,
            profile=blender_profile,
            blender_version=blender_version,
            device_class=device_selection.selected_device,
        )

        # 4. Build + run the typed job.
        payload = {
            "ir_hash": ir_hash,
            "kind": kind,
            "units": [u.model_dump(mode="json") for u in units],
            "render_intent_profile": render.profile.model_dump(mode="json"),
            "render_profile": blender_profile.to_dict(),
            "render_profile_hash": blender_profile.profile_hash(),
            "device_selection": device_selection.to_dict(),
            "render_cache_key": render_cache_key,
            "frame_start": render.frame_start,
            "frame_end": frame_end,
            "chunk_plan": job_plan,
            "extension": blender_profile.extension,
            "resolution": dict(blender_profile.resolution),
            "project_id": str(project_id or ""),
            "revision_id": str(revision_id or ""),
        }
        spec = self._build_spec(
            job_id=str(job_id),
            kind=kind,
            executable_path=executable_path,
            payload=payload,
            timeout_seconds=self._config.default_timeout_seconds,
        )

        try:
            locator, execution_receipt = await self._supervisor.launch(spec)
        except BlenderJobError as exc:
            return EngineJobReceipt(
                job_id=job_id,
                project_id=project_id or VideoProjectId("vp_unknown"),
                revision_id=revision_id or ProductionRevisionId("rev_unknown"),
                ir_hash=ir_hash,
                status=EngineJobStatus.FAILED,
                engine_name=self.engine_name,
                error=f"job launch rejected: {exc}",
                metadata={"job_kind": kind, "gate": "workspace_validation"},
            )

        # 5. Read the job result + collect output artifacts and raw telemetry.
        output_files = self._collect_output_files(spec)
        job_result = self._load_job_result(spec.job_id)
        status, error = self._classify(locator.state, execution_receipt)
        return EngineJobReceipt(
            job_id=job_id,
            project_id=project_id or VideoProjectId("vp_unknown"),
            revision_id=revision_id or ProductionRevisionId("rev_unknown"),
            ir_hash=ir_hash,
            status=status,
            engine_name=self.engine_name,
            artifact_uris=[f["uri"] for f in output_files],
            error=error,
            metadata={
                "job_kind": kind,
                "execution_receipt": execution_receipt.to_dict(),
                "output_files": output_files,
                "blender_render_profile": blender_profile.to_dict(),
                "render_profile_hash": blender_profile.profile_hash(),
                "device_selection": device_selection.to_dict(),
                "render_cache_key": render_cache_key,
                "render_job_plan": job_plan,
                "render_telemetry": (job_result.get("report", {}) or {}).get(
                    "telemetry", {}
                ),
                "vram_budget_decision": (
                    vram_decision.to_dict() if vram_decision is not None else None
                ),
            },
        )

    # ------------------------------------------------------------------
    # Inspect / cancel / download
    # ------------------------------------------------------------------
    def _job_context(self, job_id) -> tuple:
        """Recover (project_id, revision_id, ir_hash) from the job workspace.

        The launcher persists the typed spec payload into job_spec.json, so a
        restarted worker can restore provenance without in-memory state.
        """
        workspace = self._artifact_root / "blender_jobs" / str(job_id)
        spec_path = workspace / "job_spec.json"
        if not spec_path.is_file():
            return ("vp_unknown", "rev_unknown", "")
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ("vp_unknown", "rev_unknown", "")
        return (
            str(spec.get("project_id") or "vp_unknown"),
            str(spec.get("revision_id") or "rev_unknown"),
            str(spec.get("ir_hash") or ""),
        )

    async def inspect_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        locator = self._supervisor.load(str(job_id))
        if locator is None:
            return EngineJobReceipt(
                job_id=job_id,
                project_id=VideoProjectId("vp_unknown"),
                revision_id=ProductionRevisionId("rev_unknown"),
                status=EngineJobStatus.FAILED,
                engine_name=self.engine_name,
                error=f"unknown engine job: {job_id}",
            )
        project_id, revision_id, ir_hash = self._job_context(job_id)
        status = self._locator_status(locator.state)
        return EngineJobReceipt(
            job_id=job_id,
            project_id=VideoProjectId(project_id),
            revision_id=ProductionRevisionId(revision_id),
            ir_hash=ir_hash,
            status=status,
            engine_name=self.engine_name,
            error=locator.reason or None,
            metadata={"locator": locator.to_dict()},
        )

    async def cancel_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        updated = self._supervisor.cancel(str(job_id))
        if updated is None:
            return EngineJobReceipt(
                job_id=job_id,
                project_id=VideoProjectId("vp_unknown"),
                revision_id=ProductionRevisionId("rev_unknown"),
                status=EngineJobStatus.FAILED,
                engine_name=self.engine_name,
                error=f"unknown engine job: {job_id}",
            )
        project_id, revision_id, ir_hash = self._job_context(job_id)
        return EngineJobReceipt(
            job_id=job_id,
            project_id=VideoProjectId(project_id),
            revision_id=ProductionRevisionId(revision_id),
            ir_hash=ir_hash,
            status=EngineJobStatus.RUNNING,
            engine_name=self.engine_name,
            metadata={"cancel_requested": True, "locator": updated.to_dict()},
        )

    async def download_artifact(
        self,
        job_id: EngineJobId,
        artifact_kind: DerivedArtifactKind,
    ) -> DerivedArtifact:
        output_files = self._collect_output_files_for(job_id)
        matching = [f for f in output_files if f.get("kind") == artifact_kind.value]
        if not matching:
            raise BlenderJobError(
                f"no {artifact_kind.value} artifact published by job {job_id}"
            )
        entry = matching[0]
        path = Path(entry["uri"])
        return DerivedArtifact(
            artifact_id=DerivedArtifactId.generate(prefix="da"),
            job_id=job_id,
            kind=artifact_kind,
            uri=entry["uri"],
            format=IrAssetFormat(entry.get("format", "UNKNOWN")),
            content_hash=entry["content_hash"],
            derived_from_ir_hash=entry["derived_from_ir_hash"],
            size_bytes=path.stat().st_size if path.is_file() else 0,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _collect_output_files(self, spec: BlenderJobSpec) -> List[Dict]:
        return self._collect_output_files_for(spec.job_id)

    def _load_job_result(self, job_id) -> Dict:
        workspace = self._artifact_root / "blender_jobs" / str(job_id)
        result_path = workspace / "job_result.json"
        if not result_path.is_file():
            return {}
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return result if isinstance(result, dict) else {}

    def _collect_output_files_for(self, job_id) -> List[Dict]:
        workspace = self._artifact_root / "blender_jobs" / str(job_id)
        result = self._load_job_result(job_id)
        if not result:
            return []

        # execute_job.py is engine-agnostic and does not know the IR hash; the
        # launcher persisted it in job_spec.json — fall back to it so derived
        # artifacts always carry the IR content hash they were built from.
        derived_from_ir_hash = result.get("ir_hash", "")
        if not derived_from_ir_hash:
            spec_path = workspace / "job_spec.json"
            if spec_path.is_file():
                try:
                    spec = json.loads(spec_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    spec = {}
                derived_from_ir_hash = spec.get("ir_hash", "")

        files = []
        for entry in result.get("output_files", []) or []:
            path = workspace / str(entry.get("path", ""))
            files.append(
                {
                    "uri": str(path),
                    "path": str(entry.get("path", "")),
                    "content_hash": entry.get("sha256", ""),
                    "derived_from_ir_hash": derived_from_ir_hash,
                    "kind": entry.get("kind", ""),
                    "format": entry.get("format", "UNKNOWN"),
                }
            )
        return files

    @staticmethod
    def _classify(locator_state: str, receipt: BlenderExecutionReceipt):
        if locator_state == STATE_CANCELLED:
            return EngineJobStatus.CANCELLED, "job cancelled"
        if (
            locator_state == STATE_COMPLETED
            and receipt.failure_classification == BlenderFailureClassification.SUCCESS
        ):
            return EngineJobStatus.COMPLETED, None
        return EngineJobStatus.FAILED, (
            receipt.error_snippet or f"job state {locator_state}"
        )

    @staticmethod
    def _locator_status(locator_state: str) -> EngineJobStatus:
        if locator_state == STATE_COMPLETED:
            return EngineJobStatus.COMPLETED
        if locator_state == STATE_CANCELLED:
            return EngineJobStatus.CANCELLED
        if locator_state == STATE_FAILED:
            return EngineJobStatus.FAILED
        return EngineJobStatus.RUNNING


def create_blender_engine_adapter(
    *,
    artifact_root: str,
    state_dir: str,
    executable_path: Optional[str] = None,
    addon_manifest: Optional[BlenderAddonManifest] = None,
    **kwargs,
) -> BlenderEngineAdapter:
    """Factory for composition roots (guarded registration uses this)."""
    config = BlenderEngineConfig(
        artifact_root=artifact_root,
        state_dir=state_dir,
        executable_path=executable_path,
        addon_manifest=addon_manifest,
        **kwargs,
    )
    return BlenderEngineAdapter(config=config)


__all__ = [
    "JOB_KIND_PROBE",
    "JOB_KIND_COMPILE",
    "JOB_KIND_SAVE",
    "JOB_KIND_INSPECT",
    "JOB_KIND_RENDER_CHUNK",
    "JOB_KIND_ASSEMBLE",
    "JOB_KIND_VERIFY",
    "BlenderEngineConfig",
    "BlenderRuntimeReadiness",
    "BlenderEngineAdapter",
    "create_blender_engine_adapter",
]
