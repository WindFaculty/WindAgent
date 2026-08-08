"""
BlenderAssetJobRunner — engine-side asset normalization jobs (VP3D Phase 7).

Implements the ``AssetJobRunner`` protocol (defined in
``windagent_tools.media_assets.normalization.job_runner``) with REAL Blender
jobs dispatched through the Stage B launcher/supervisor:

- input asset files are copied into a sandboxed job workspace INSIDE the
  validated artifact root (never imported from arbitrary paths);
- jobs run ``blender.exe --background --factory-startup`` with the trusted
  ``execute_asset_job.py`` (auto-execution disabled inside the job);
- outputs land in the workspace; the host reads them back for the bundle.

This module is the ONLY place asset normalization talks to Blender.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from windagent_core.domain.video_production.asset_normalization.models import (
    PreviewProfile,
)

from windagent_tools.media_assets.normalization.job_runner import (
    JobInvocation,
    JobResult,
)
from windagent_tools.production_engines.blender.runtime.launcher import (
    BlenderJobError,
    BlenderJobLauncher,
    BlenderJobSpec,
)
from windagent_tools.production_engines.blender.runtime.supervisor import (
    STATE_COMPLETED,
    BlenderProcessSupervisor,
)

ASSET_JOB_SCRIPT = "execute_asset_job.py"


class BlenderAssetJobRunner:
    """AssetNormalizer engine jobs over the Stage B Blender runtime."""

    def __init__(
        self,
        *,
        executable_path: str,
        artifact_root: str,
        state_dir: str,
        launcher: Optional[BlenderJobLauncher] = None,
        supervisor: Optional[BlenderProcessSupervisor] = None,
    ) -> None:
        self._executable_path = executable_path
        self._artifact_root = Path(artifact_root).resolve()
        self._launcher = launcher or BlenderJobLauncher(artifact_root=artifact_root)
        self._supervisor = supervisor or BlenderProcessSupervisor(
            state_dir=state_dir,
            launcher=self._launcher,
        )
        self._script_path = str(
            Path(__file__).resolve().parents[0] / "scripts" / ASSET_JOB_SCRIPT
        )

    @property
    def available(self) -> bool:
        exe = Path(self._executable_path)
        return exe.is_file() and Path(self._script_path).is_file()

    # ------------------------------------------------------------------
    async def import_validate(self, invocation: JobInvocation) -> JobResult:
        return await self._dispatch(invocation, kind="ASSET_IMPORT_VALIDATE")

    async def generate_lod(self, invocation: JobInvocation) -> JobResult:
        return await self._dispatch(invocation, kind="ASSET_GENERATE_LOD")

    async def render_preview(
        self,
        invocation: JobInvocation,
        profile: PreviewProfile,
    ) -> JobResult:
        payload = dict(invocation.config)
        payload.update(
            {
                "width": profile.width,
                "height": profile.height,
                "frames": profile.frames,
                "samples": profile.samples,
                "engine": profile.engine,
                "device": profile.device,
                "denoise": profile.denoise,
            }
        )
        invocation = JobInvocation(
            kind=invocation.kind,
            job_id=invocation.job_id,
            input_files=invocation.input_files,
            output_dir=invocation.output_dir,
            workspace=invocation.workspace,
            config=payload,
        )
        return await self._dispatch(invocation, kind="ASSET_PREVIEW")

    # ------------------------------------------------------------------
    async def _dispatch(self, invocation: JobInvocation, *, kind: str) -> JobResult:
        if not self.available:
            return JobResult(
                job_id=invocation.job_id,
                kind=kind,
                ok=False,
                error="Blender executable or asset job script unavailable",
            )
        workspace = self._workspace(invocation.job_id)
        workspace.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        try:
            for raw in invocation.input_files:
                src = Path(raw)
                if not src.is_file():
                    raise BlenderJobError(f"input file missing: {src}")
                target = workspace / src.name
                if not target.exists():
                    shutil.copy2(src, target)
                copied.append(str(target))
        except OSError as exc:
            return JobResult(
                job_id=invocation.job_id, kind=kind, ok=False,
                error=f"workspace staging failed: {exc}",
            )

        payload = dict(invocation.config)
        payload["input_files"] = copied
        payload["output_dir"] = str(workspace)
        spec = BlenderJobSpec(
            job_id=invocation.job_id,
            kind=kind,
            executable_path=self._executable_path,
            script_path=self._script_path,
            job_workspace=str(workspace),
            spec_payload=payload,
            timeout_seconds=1200.0,
        )
        try:
            locator, receipt = await self._supervisor.launch(spec)
        except BlenderJobError as exc:
            return JobResult(
                job_id=invocation.job_id, kind=kind, ok=False, error=str(exc)
            )

        # The job result contract is the workspace/job_result.json written by
        # the trusted script inside blender.exe.
        report: dict = {}
        result_path = workspace / "job_result.json"
        if result_path.is_file():
            try:
                import json as _json

                result = _json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(result, dict):
                    report = result.get("report") or {}
            except (OSError, ValueError):
                report = {}
        return JobResult(
            job_id=invocation.job_id,
            kind=kind,
            ok=locator.state == STATE_COMPLETED,
            report=report,
            error=locator.reason or receipt.error_snippet or "",
            generated_files=[
                str(workspace / name) for name in _reported_files(report)
            ],
        )

    def _workspace(self, job_id: str) -> Path:
        safe = job_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self._artifact_root / "phase_07_jobs" / safe


def _reported_files(report: dict) -> list[str]:
    """Collect engine-produced file names from a job result report."""
    names: list[str] = []
    thumbnail = report.get("thumbnail_file")
    if thumbnail:
        names.append(str(thumbnail))
    for frame in report.get("turntable_files", []):
        names.append(str(frame))
    file_name = report.get("file_name")
    if file_name:
        names.append(str(file_name))
    normalized = report.get("normalized_blend")
    if normalized:
        names.append(str(normalized))
    return names


__all__ = ["BlenderAssetJobRunner"]
