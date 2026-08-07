"""
VP3D Phase 3 — Blender job launcher (plan Stage B §3 backlog item 5).

`BlenderJobLauncher` builds and runs a typed blender job:

- argv is ALWAYS a list (never a shell string — no interpolation);
- only an environment ALLOWLIST is passed to the child (plus explicit job
  additions), so the child never inherits arbitrary host secrets;
- the job workspace must resolve INSIDE the validated artifact root;
- every arg is validated (no NUL bytes, no non-str, workspace-bounded);
- timeout and a cancel event bound the process run.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from windagent_tools.production_engines.blender.runtime.process import (
    BlenderProcessPort,
    BlenderProcessResult,
    SubprocessBlenderProcess,
)
from windagent_tools.production_engines.blender.runtime.receipts import BlenderExecutionReceipt

DEFAULT_ENV_ALLOWLIST = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "PROCESSOR_ARCHITECTURE",
    "NUMBER_OF_PROCESSORS",
    "PATHEXT",
    "COMSPEC",
)


class BlenderJobError(RuntimeError):
    """Typed error raised before/around launching a blender job."""


@dataclass(frozen=True)
class BlenderJobSpec:
    """Typed, immutable specification of one blender job."""

    job_id: str
    kind: str  # PROBE | COMPILE_SAVE | INSPECT | RENDER_CHUNK | ASSEMBLE | VERIFY
    executable_path: str
    script_path: str  # path to the trusted execute_job.py
    job_workspace: str  # absolute path, must resolve inside artifact_root
    spec_payload: dict = field(default_factory=dict)
    env_additions: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 300.0
    idempotency_key: str = ""


class BlenderJobLauncher:
    """Validates and launches one blender job through the process port."""

    def __init__(
        self,
        *,
        artifact_root: str,
        env_allowlist: Sequence[str] = DEFAULT_ENV_ALLOWLIST,
        process_port: Optional[BlenderProcessPort] = None,
    ) -> None:
        self._artifact_root = Path(artifact_root).resolve()
        self._env_allowlist = tuple(env_allowlist)
        self._process = process_port or SubprocessBlenderProcess()

    # ------------------------------------------------------------------
    def validate_workspace(self, job_workspace: str) -> Path:
        """Resolve and bound a job workspace inside the artifact root."""
        if not job_workspace:
            raise BlenderJobError("job workspace must not be empty")
        candidate = Path(job_workspace)
        if not candidate.is_absolute():
            candidate = self._artifact_root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self._artifact_root)
        except ValueError:
            raise BlenderJobError(
                f"job workspace escapes artifact root: {resolved}"
            ) from None
        return resolved

    def prepare(self, spec: BlenderJobSpec) -> tuple[Path, List[str], Dict[str, str]]:
        """Validate workspace, persist the typed job spec, build argv + env.

        Shared by `launch` (run-and-wait) and `start_process` (the supervisor
        needs the PID BEFORE the process finishes for crash recovery).
        """
        import json

        workspace = self.validate_workspace(spec.job_workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        (workspace / "job_spec.json").write_text(
            json.dumps(spec.spec_payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

        argv = self.build_argv(spec)
        self.validate_argv(argv)
        env = self.build_env(spec)
        return workspace, argv, env

    async def start_process(
        self,
        spec: BlenderJobSpec,
        *,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ):
        """Start the blender process and return a live handle (PID known)."""
        workspace, argv, built_env = self.prepare(spec)
        return await self._process.start(
            argv,
            env=env if env is not None else built_env,
            cwd=cwd if cwd is not None else str(workspace),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def build_argv(spec: BlenderJobSpec) -> List[str]:
        """Build the blender argv list (no shell)."""
        return [
            spec.executable_path,
            "--background",
            "--factory-startup",
            "--python",
            str(spec.script_path),
            "--",
            "--job-id",
            spec.job_id,
            "--kind",
            spec.kind,
            "--job-spec",
            str(Path(spec.job_workspace) / "job_spec.json"),
        ]

    # ------------------------------------------------------------------
    @staticmethod
    def validate_argv(argv: Sequence[str]) -> None:
        """Fail closed on malformed or injection-suspect argv entries."""
        if not argv:
            raise BlenderJobError("argv must not be empty")
        for arg in argv:
            if not isinstance(arg, str):
                raise BlenderJobError(f"argv entry is not a string: {arg!r}")
            if "\x00" in arg:
                raise BlenderJobError("argv entry contains a NUL byte (rejected)")
            if not arg:
                raise BlenderJobError("argv entry is empty")

    # ------------------------------------------------------------------
    def build_env(self, spec: BlenderJobSpec, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build the child environment from the allowlist + job additions."""
        base = dict(os.environ) if base_env is None else dict(base_env)
        env: Dict[str, str] = {}
        for key in self._env_allowlist:
            if key in base and base[key] is not None:
                env[key] = str(base[key])
        for key, value in spec.env_additions.items():
            env[str(key)] = str(value)
        return env

    # ------------------------------------------------------------------
    async def launch(
        self,
        spec: BlenderJobSpec,
        *,
        cancel_event: Optional[asyncio.Event] = None,
        started_at: Optional[float] = None,
    ) -> tuple[BlenderProcessResult, BlenderExecutionReceipt]:
        workspace, argv, env = self.prepare(spec)

        start = started_at if started_at is not None else time.time()
        try:
            result = await self._process.run(
                argv,
                timeout_seconds=spec.timeout_seconds,
                env=env,
                cancel_event=cancel_event,
                cwd=str(workspace),
            )
        except asyncio.CancelledError:
            result = BlenderProcessResult(
                argv=tuple(argv),
                returncode=-1,
                stdout="",
                stderr="",
                cancelled=True,
            )
        except Exception as exc:  # fail closed on unexpected launch errors
            result = BlenderProcessResult(
                argv=tuple(argv),
                returncode=-1,
                stdout="",
                stderr=f"launcher error: {exc}",
                start_failed=True,
            )

        receipt = BlenderExecutionReceipt.from_process_result(
            job_id=spec.job_id,
            kind=spec.kind,
            executable_path=spec.executable_path,
            argv=argv,
            result=result,
            started_at=start,
            metadata={
                "workspace": str(workspace),
                "timeout_seconds": spec.timeout_seconds,
                "idempotency_key": spec.idempotency_key,
            },
        )
        return result, receipt


__all__ = [
    "DEFAULT_ENV_ALLOWLIST",
    "BlenderJobError",
    "BlenderJobSpec",
    "BlenderJobLauncher",
]
