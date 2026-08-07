"""
VP3D Phase 4 — BlenderSmokePipeline (plan Stage B §4 flow orchestrator).

Runs the deterministic smoke fixture through the canonical flow:

    Production IR fixture
    -> compile scene plan            (ScenePlanCompiler — no process)
    -> COMPILE  job                  (build_scene.py -> scene.blend)
    -> SAVE     job                  (idempotent re-save proof)
    -> INSPECT  job                  (reopen + report)
    -> RENDER_CHUNK jobs             (atomic PNG/EXR chunks, cancel/resume)
    -> ASSEMBLE job                  (FFmpeg image sequence -> MP4)
    -> VERIFY   job                  (ffprobe final MP4)

Pipeline guarantees (plan §4 items 1-7):

1. Locked config: seed, frame range, fps, color management, resolution,
   Cycles samples, denoise, device are all locked in the ScenePlan.
2. Every job carries an idempotency key (inputs + config + tools).
3. Frames are written temp -> validated final; Blender never writes MP4.
4. Cancel mid-chunk publishes nothing; resume starts at the next valid frame
   (FrameManifest + execute_job resume logic).
5. Completed jobs REUSE artifacts when keys match; key change INVALIDATES
   (ArtifactReusePolicy).
6. VERIFY checks frame count, dimensions, decode, duration, stream policy and
   output SHA-256.
7. Two runs of the same IR produce a DeterminismReport (structural stability
   mandatory; pixel parity only on identical hardware).

The pipeline is process-port injectable end to end (fake blender + fake
ffmpeg), so the whole flow is contract-tested in CI with fake executables.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from windagent_core.domain.video_production.production_ir.models import (
    ProductionIrDocument,
    RenderIntent,
    SceneDescription,
    ShotExecutionIntent,
)

from windagent_tools.production_engines.blender.ffmpeg import (
    BlenderFfmpegRunner,
)
from windagent_tools.production_engines.blender.runtime.launcher import (
    BlenderJobError,
    BlenderJobLauncher,
    BlenderJobSpec,
)
from windagent_tools.production_engines.blender.runtime.supervisor import (
    STATE_CANCELLED,
    STATE_COMPLETED,
    STATE_FAILED,
    BlenderProcessSupervisor,
)
from windagent_tools.production_engines.blender.scene.compiler import (
    DEVICE_CPU,
    ScenePlan,
    ScenePlanCompiler,
)
from windagent_tools.production_engines.blender.scene.determinism import (
    DeterminismReport,
    RunSnapshot,
    compare_runs,
)
from windagent_tools.production_engines.blender.scene.frames import (
    FRAME_MANIFEST_FILENAME,
    FrameManifest,
    sha256_file,
)
from windagent_tools.production_engines.blender.scene.idempotency import (
    ArtifactReusePolicy,
    FRESH,
    INVALIDATE,
    NON_TERMINAL,
    REUSE,
    job_idempotency_key,
)

COMPILE = "COMPILE"
SAVE = "SAVE"
INSPECT = "INSPECT"
RENDER_CHUNK = "RENDER_CHUNK"
ASSEMBLE = "ASSEMBLE"
VERIFY = "VERIFY"

DEFAULT_CHUNK_FRAMES = 12
DEFAULT_EXTENSION = "png"
DEFAULT_OUTPUT_FILENAME = "final.mp4"


@dataclass(frozen=True)
class JobOutcome:
    """Outcome of one dispatched job (blender or host-side)."""

    job_id: str
    kind: str
    state: str
    reused: bool = False
    error: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "state": self.state,
            "reused": self.reused,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SmokeRunResult:
    """Result of one full pipeline run over the fixture."""

    scene_plan: ScenePlan
    scene_plan_path: str
    workspace: str
    job_outcomes: List[JobOutcome] = field(default_factory=list)
    frame_manifest_hash: str = ""
    frame_hashes: Dict[str, str] = field(default_factory=dict)
    final_mp4_hash: str = ""
    ffprobe: Dict = field(default_factory=dict)
    hardware_profile: Dict = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and all(
            o.state == STATE_COMPLETED for o in self.job_outcomes
        )

    def to_dict(self) -> dict:
        return {
            "scene_plan_hash": self.scene_plan.plan_hash(),
            "idempotency_key": self.scene_plan.idempotency_key(),
            "scene_plan_path": self.scene_plan_path,
            "workspace": self.workspace,
            "job_outcomes": [o.to_dict() for o in self.job_outcomes],
            "frame_manifest_hash": self.frame_manifest_hash,
            "frame_hashes": dict(self.frame_hashes),
            "final_mp4_hash": self.final_mp4_hash,
            "ffprobe": dict(self.ffprobe),
            "hardware_profile": dict(self.hardware_profile),
            "error": self.error,
            "ok": self.ok,
        }

    def snapshot(self, run_label: str) -> RunSnapshot:
        return RunSnapshot(
            run_label=run_label,
            scene_plan_hash=self.scene_plan.plan_hash(),
            idempotency_key=self.scene_plan.idempotency_key(),
            frame_manifest_hash=self.frame_manifest_hash,
            frame_hashes=dict(self.frame_hashes),
            final_mp4_hash=self.final_mp4_hash,
            ffprobe=dict(self.ffprobe),
            hardware_profile=dict(self.hardware_profile),
        )


class BlenderSmokePipeline:
    """Orchestrates the deterministic smoke fixture end to end."""

    def __init__(
        self,
        *,
        artifact_root: str,
        state_dir: str,
        launcher: BlenderJobLauncher,
        supervisor: BlenderProcessSupervisor,
        ffmpeg_runner: BlenderFfmpegRunner,
        compiler: Optional[ScenePlanCompiler] = None,
        reuse_policy: Optional[ArtifactReusePolicy] = None,
        chunk_frames: int = DEFAULT_CHUNK_FRAMES,
        extension: str = DEFAULT_EXTENSION,
        output_filename: str = DEFAULT_OUTPUT_FILENAME,
        device: str = DEVICE_CPU,
    ) -> None:
        self._artifact_root = Path(artifact_root).resolve()
        self._state_dir = Path(state_dir).resolve()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._launcher = launcher
        self._supervisor = supervisor
        self._ffmpeg = ffmpeg_runner
        self._compiler = compiler or ScenePlanCompiler()
        self._reuse_policy = reuse_policy or ArtifactReusePolicy()
        self._chunk_frames = chunk_frames
        self._extension = extension
        self._output_filename = output_filename
        self._device = device

    # ------------------------------------------------------------------
    # Workspace + plan preparation
    # ------------------------------------------------------------------
    def scene_workspace(self, scene_id: str) -> Path:
        return self._artifact_root / "phase_04_smoke" / str(scene_id)

    def compile_plan(
        self,
        scene: SceneDescription,
        render: RenderIntent,
        shot: Optional[ShotExecutionIntent] = None,
        *,
        seed: Optional[int] = None,
    ) -> ScenePlan:
        """Compile the locked scene plan (no process needed)."""
        return self._compiler.compile(
            scene, render, shot, seed=seed, device=self._device
        )

    def prepare_workspace(self, plan: ScenePlan) -> Path:
        """Write scene_plan.json + pinned build_scene.py into the workspace."""
        workspace = self.scene_workspace(plan.scene_id)
        workspace.mkdir(parents=True, exist_ok=True)
        plan_payload = plan.to_dict()
        plan_payload["output_blend_path"] = "scene.blend"
        (workspace / "scene_plan.json").write_text(
            json.dumps(plan_payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        (workspace / "build_scene.py").write_text(
            self._compiler.build_script(plan), encoding="utf-8"
        )
        return workspace

    # ------------------------------------------------------------------
    # Durable per-scene receipt store (reuse/invalidate decisions)
    # ------------------------------------------------------------------
    def _receipt_path(self, scene_id: str) -> Path:
        safe = str(scene_id).replace("/", "_").replace("\\", "_")
        return self._state_dir / f"{safe}.run.json"

    def _load_previous(self, scene_id: str) -> dict:
        path = self._receipt_path(scene_id)
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_run(self, scene_id: str, run: SmokeRunResult, previous: dict) -> None:
        """Persist the run plus the durable job-record keys used for reuse.

        The reuse policy reads compile_job_id/compile_state/compile_key on the
        next run — those are written here so REUSE works across runs (plan §4
        item 5: retry completed job reuse artifact when hashes match).
        """
        payload = run.to_dict()
        for key in ("compile_job_id", "compile_state", "compile_key"):
            if key in previous:
                payload[key] = previous[key]
        self._receipt_path(scene_id).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Job dispatch
    # ------------------------------------------------------------------
    def _make_spec(
        self,
        *,
        job_id: str,
        kind: str,
        executable_path: str,
        workspace: Path,
        payload: dict,
        timeout_seconds: float = 300.0,
    ) -> BlenderJobSpec:
        return BlenderJobSpec(
            job_id=job_id,
            kind=kind,
            executable_path=executable_path,
            script_path=str(
                Path(__file__).resolve().parents[1] / "scripts" / "execute_job.py"
            ),
            job_workspace=str(workspace),
            spec_payload=payload,
            timeout_seconds=timeout_seconds,
            idempotency_key=str(payload.get("idempotency_key", "")),
        )

    async def _run_blender_job(
        self,
        *,
        job_id: str,
        kind: str,
        executable_path: str,
        workspace: Path,
        payload: dict,
        timeout_seconds: float = 300.0,
    ) -> JobOutcome:
        spec = self._make_spec(
            job_id=job_id,
            kind=kind,
            executable_path=executable_path,
            workspace=workspace,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        try:
            locator, receipt = await self._supervisor.launch(spec)
        except BlenderJobError as exc:
            return JobOutcome(job_id=job_id, kind=kind, state=STATE_FAILED, error=str(exc))
        return JobOutcome(
            job_id=job_id,
            kind=kind,
            state=locator.state,
            error=locator.reason or (receipt.error_snippet or ""),
            metadata={"execution_receipt": receipt.to_dict()},
        )

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------
    async def run_smoke(
        self,
        ir: ProductionIrDocument,
        *,
        shot: Optional[ShotExecutionIntent] = None,
        seed: Optional[int] = None,
        executable_path: str,
        cancel_after_chunk: Optional[int] = None,
        run_label: str = "run",
    ) -> SmokeRunResult:
        """Run the full flow for the IR's first scene+render intent.

        `cancel_after_chunk` (test/evidence hook) stops the render after the
        Nth RENDER_CHUNK job with a cancel token, proving cancel/resume.
        """
        if not ir.scenes:
            return SmokeRunResult(
                scene_plan=ScenePlan(),
                scene_plan_path="",
                workspace=str(self._artifact_root),
                error="IR contains no scenes",
            )
        scene = ir.scenes[0]
        render = next(
            (r for r in ir.render_intents if str(r.scene_id) == str(scene.scene_id)),
            None,
        )
        if render is None:
            render = RenderIntent.model_validate(
                {"intent_id": "ri_smoke", "scene_id": str(scene.scene_id)}
            )

        plan = self.compile_plan(scene, render, shot, seed=seed)
        workspace = self.prepare_workspace(plan)
        outcomes: List[JobOutcome] = []
        previous = self._load_previous(plan.scene_id)

        # --- COMPILE (reuse or fresh) -----------------------------------
        compile_key = job_idempotency_key(
            kind=COMPILE,
            input_hash=plan.input_hash,
            config_hash=plan.config_hash,
            tool_hash=plan.tool_hash,
        )
        decision = self._reuse_policy.decide(
            requested_key=compile_key,
            recorded_job_id=previous.get("compile_job_id"),
            recorded_state=previous.get("compile_state"),
            recorded_key=previous.get("compile_key"),
        )
        if decision.decision == REUSE and (workspace / "scene.blend").is_file():
            outcomes.append(
                JobOutcome(
                    job_id=decision.job_id or "reused",
                    kind=COMPILE,
                    state=STATE_COMPLETED,
                    reused=True,
                )
            )
        else:
            if decision.decision == INVALIDATE:
                self._reuse_policy.invalidate_outputs(workspace)
            outcome = await self._run_blender_job(
                job_id=f"ej_{plan.scene_id}_compile",
                kind=COMPILE,
                executable_path=executable_path,
                workspace=workspace,
                payload={
                    "idempotency_key": compile_key,
                    "kind": COMPILE,
                },
            )
            outcomes.append(outcome)
            previous["compile_job_id"] = outcome.job_id
            previous["compile_state"] = outcome.state
            previous["compile_key"] = compile_key

        if previous.get("compile_state") != STATE_COMPLETED:
            result = SmokeRunResult(
                scene_plan=plan,
                scene_plan_path=str(workspace / "scene_plan.json"),
                workspace=str(workspace),
                job_outcomes=outcomes,
                error="COMPILE did not complete",
            )
            self._save_run(plan.scene_id, result, previous)
            return result

        # --- SAVE + INSPECT (always fresh: cheap, proves reopen) --------
        save_outcome = await self._run_blender_job(
            job_id=f"ej_{plan.scene_id}_save",
            kind=SAVE,
            executable_path=executable_path,
            workspace=workspace,
            payload={"idempotency_key": plan.idempotency_key(), "kind": SAVE},
        )
        outcomes.append(save_outcome)
        inspect_outcome = await self._run_blender_job(
            job_id=f"ej_{plan.scene_id}_inspect",
            kind=INSPECT,
            executable_path=executable_path,
            workspace=workspace,
            payload={"idempotency_key": plan.idempotency_key(), "kind": INSPECT},
        )
        outcomes.append(inspect_outcome)
        if inspect_outcome.state != STATE_COMPLETED:
            return SmokeRunResult(
                scene_plan=plan,
                scene_plan_path=str(workspace / "scene_plan.json"),
                workspace=str(workspace),
                job_outcomes=outcomes,
                error="INSPECT did not complete",
            )

        # --- RENDER_CHUNK jobs (chunked, cancel/resume, atomic) ---------
        frame_start, frame_end = plan.frame_start, plan.frame_end
        chunk_key = job_idempotency_key(
            kind=RENDER_CHUNK,
            input_hash=plan.input_hash,
            config_hash=plan.config_hash,
            tool_hash=plan.tool_hash,
        )
        manifest = FrameManifest(
            workspace=workspace,
            frame_range=(frame_start, frame_end),
            extension=self._extension,
            expected_dimensions=plan.resolution,
            content_hash=chunk_key,
        )
        cancelled = False
        chunk_index = 0
        for chunk_start in range(frame_start, frame_end + 1, self._chunk_frames):
            chunk_end = min(chunk_start + self._chunk_frames - 1, frame_end)
            chunk_index += 1
            if cancel_after_chunk is not None and chunk_index > cancel_after_chunk:
                # Simulated external cancel between chunks -> resume later.
                self._supervisor.cancel(f"ej_{plan.scene_id}_render_{chunk_index}")
                cancelled = True
                break
            # Resume: skip chunks whose frames are all validated.
            if manifest.next_frame() is None:
                break
            if all(manifest.has_frame(f) for f in range(chunk_start, chunk_end + 1)):
                continue
            outcome = await self._run_blender_job(
                job_id=f"ej_{plan.scene_id}_render_{chunk_index}",
                kind=RENDER_CHUNK,
                executable_path=executable_path,
                workspace=workspace,
                payload={
                    "idempotency_key": chunk_key,
                    "kind": RENDER_CHUNK,
                    "frame_start": chunk_start,
                    "frame_end": chunk_end,
                    "extension": self._extension,
                    "resolution": plan.resolution,
                },
            )
            outcomes.append(outcome)
            if outcome.state == STATE_CANCELLED:
                cancelled = True
                break
            if outcome.state != STATE_COMPLETED:
                return SmokeRunResult(
                    scene_plan=plan,
                    scene_plan_path=str(workspace / "scene_plan.json"),
                    workspace=str(workspace),
                    job_outcomes=outcomes,
                    error=f"RENDER_CHUNK {chunk_index} did not complete",
                )
            manifest.load()

        if cancelled:
            result = SmokeRunResult(
                scene_plan=plan,
                scene_plan_path=str(workspace / "scene_plan.json"),
                workspace=str(workspace),
                job_outcomes=outcomes,
                frame_manifest_hash=manifest.manifest_hash(),
                frame_hashes={str(e.frame): e.sha256 for e in manifest.frames},
                error="pipeline cancelled mid-render (resume from next valid frame)",
            )
            self._save_run(plan.scene_id, result, previous)
            return result

        # --- ASSEMBLE + VERIFY (host-side FFmpeg/ffprobe) ----------------
        manifest.load()
        if manifest.next_frame() is not None:
            return SmokeRunResult(
                scene_plan=plan,
                scene_plan_path=str(workspace / "scene_plan.json"),
                workspace=str(workspace),
                job_outcomes=outcomes,
                frame_manifest_hash=manifest.manifest_hash(),
                frame_hashes={str(e.frame): e.sha256 for e in manifest.frames},
                error="render did not cover the full frame range",
            )
        assemble = await self._ffmpeg.assemble_frames(
            job_id=f"ej_{plan.scene_id}_assemble",
            workspace=str(workspace),
            frame_start=frame_start,
            frame_end=frame_end,
            fps=plan.fps,
            extension=self._extension,
            output_filename=self._output_filename,
        )
        outcomes.append(
            JobOutcome(
                job_id=assemble.job_id,
                kind=ASSEMBLE,
                state=STATE_COMPLETED if assemble.ok else STATE_FAILED,
                error=assemble.error,
                metadata={"output_hash": assemble.output_hash},
            )
        )
        verify = await self._ffmpeg.verify_mp4(
            job_id=f"ej_{plan.scene_id}_verify",
            workspace=str(workspace),
            output_filename=self._output_filename,
        )
        outcomes.append(
            JobOutcome(
                job_id=verify.job_id,
                kind=VERIFY,
                state=STATE_COMPLETED if verify.ok else STATE_FAILED,
                error=verify.error,
                metadata={"ffprobe": verify.ffprobe},
            )
        )

        final_mp4_hash = ""
        final_path = workspace / self._output_filename
        if final_path.is_file():
            final_mp4_hash = sha256_file(final_path)

        result = SmokeRunResult(
            scene_plan=plan,
            scene_plan_path=str(workspace / "scene_plan.json"),
            workspace=str(workspace),
            job_outcomes=outcomes,
            frame_manifest_hash=manifest.manifest_hash(),
            frame_hashes={str(e.frame): e.sha256 for e in manifest.frames},
            final_mp4_hash=final_mp4_hash,
            ffprobe=dict(verify.ffprobe),
            hardware_profile={
                "device": self._device,
                "build": "",
                "driver": "",
                "color_management": plan.color_management,
                "resolution": plan.resolution,
            },
            error="" if result_ok(outcomes) else "one or more jobs failed",
        )
        self._save_run(plan.scene_id, result, previous)
        return result

    # ------------------------------------------------------------------
    async def determinism_check(
        self,
        ir: ProductionIrDocument,
        *,
        executable_path: str,
        run_label_a: str = "run_a",
        run_label_b: str = "run_b",
        seed: int = 42,
    ) -> DeterminismReport:
        """Run the fixture twice with the SAME input and compare structure."""
        run_a = await self.run_smoke(
            ir, seed=seed, executable_path=executable_path, run_label=run_label_a
        )
        if not run_a.ok:
            run_b = await self.run_smoke(
                ir, seed=seed, executable_path=executable_path, run_label=run_label_b
            )
            return compare_runs(run_a.snapshot(run_label_a), run_b.snapshot(run_label_b))
        # Second run should REUSE completed artifacts (identical keys).
        run_b = await self.run_smoke(
            ir, seed=seed, executable_path=executable_path, run_label=run_label_b
        )
        return compare_runs(run_a.snapshot(run_label_a), run_b.snapshot(run_label_b))


def result_ok(outcomes: List[JobOutcome]) -> bool:
    return all(o.state == STATE_COMPLETED for o in outcomes)


__all__ = [
    "COMPILE",
    "SAVE",
    "INSPECT",
    "RENDER_CHUNK",
    "ASSEMBLE",
    "VERIFY",
    "DEFAULT_CHUNK_FRAMES",
    "DEFAULT_EXTENSION",
    "DEFAULT_OUTPUT_FILENAME",
    "JobOutcome",
    "SmokeRunResult",
    "BlenderSmokePipeline",
    "result_ok",
]
