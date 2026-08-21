"""
VP3D Phase 3 — Blender process supervisor (plan Stage B §3 backlog item 6).

`BlenderProcessSupervisor` owns the durable lifecycle of a blender job:

- a `BlenderJobLocator` (job id, PID, workspace, state, heartbeat) is
  persisted to a state file BEFORE the process starts, so a worker crash mid
  job leaves a recoverable record;
- a heartbeat loop touches the locator while the job runs;
- cancel is GRACEFUL first (a durable `cancel.token` file the trusted
  `execute_job.py` polls), then a BOUNDED kill after a grace window; the
  running launch loop detects the token itself, so cancel works cross-process;
- on worker restart, `reconcile()` either REATTACHES a locator whose PID is
  still alive, or QUARANTINES one whose process is gone — never silently
  drops a running job.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional

from windagent_tools.production_engines.blender.runtime.launcher import (
    BlenderJobLauncher,
    BlenderJobSpec,
)
from windagent_tools.production_engines.blender.runtime.process import (
    BlenderProcessHandle,
    BlenderProcessResult,
)
from windagent_tools.production_engines.blender.runtime.receipts import (
    BlenderExecutionReceipt,
)

CANCEL_TOKEN_FILENAME = "cancel.token"

# Durable job states.
STATE_STARTING = "STARTING"
STATE_RUNNING = "RUNNING"
STATE_CANCELLING = "CANCELLING"
STATE_COMPLETED = "COMPLETED"
STATE_FAILED = "FAILED"
STATE_CANCELLED = "CANCELLED"
STATE_QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class BlenderJobLocator:
    """Durable record of one blender job (persisted to a state file)."""

    job_id: str
    kind: str
    executable_path: str
    workspace: str
    state: str = STATE_STARTING
    pid: Optional[int] = None
    started_at: float = 0.0
    heartbeat_at: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "executable_path": self.executable_path,
            "workspace": self.workspace,
            "state": self.state,
            "pid": self.pid,
            "started_at": self.started_at,
            "heartbeat_at": self.heartbeat_at,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlenderJobLocator":
        keys = (
            "job_id", "kind", "executable_path", "workspace", "state",
            "pid", "started_at", "heartbeat_at", "reason",
        )
        return cls(**{k: data.get(k) for k in keys})


class BlenderProcessSupervisor:
    """Durable lifecycle owner for blender jobs."""

    def __init__(
        self,
        *,
        state_dir: str,
        launcher: BlenderJobLauncher,
        heartbeat_seconds: float = 5.0,
        cancel_grace_seconds: float = 10.0,
        clock=None,
    ) -> None:
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._launcher = launcher
        self._heartbeat_seconds = heartbeat_seconds
        self._cancel_grace_seconds = cancel_grace_seconds
        self._clock = clock or time.time
        self._handles: Dict[str, BlenderProcessHandle] = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _state_path(self, job_id: str) -> Path:
        return self._state_dir / f"{job_id}.locator.json"

    def _persist(self, locator: BlenderJobLocator) -> None:
        self._state_path(locator.job_id).write_text(
            json.dumps(locator.to_dict(), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def load(self, job_id: str) -> Optional[BlenderJobLocator]:
        path = self._state_path(job_id)
        if not path.is_file():
            return None
        try:
            return BlenderJobLocator.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError, KeyError):
            return None

    def load_all(self) -> List[BlenderJobLocator]:
        locators = []
        for path in sorted(self._state_dir.glob("*.locator.json")):
            locator = self.load(path.stem[: -len(".locator")])
            if locator is not None:
                locators.append(locator)
        return locators

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------
    async def launch(
        self,
        spec: BlenderJobSpec,
        *,
        cancel_event: Optional[asyncio.Event] = None,
        started_at: Optional[float] = None,
    ) -> tuple[BlenderJobLocator, BlenderExecutionReceipt]:
        workspace = self._launcher.validate_workspace(spec.job_workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        start = started_at if started_at is not None else self._clock()
        locator = BlenderJobLocator(
            job_id=spec.job_id,
            kind=spec.kind,
            executable_path=spec.executable_path,
            workspace=str(workspace),
            state=STATE_STARTING,
            started_at=start,
            heartbeat_at=start,
        )
        self._persist(locator)  # persisted BEFORE process start (crash-safe)

        try:
            handle = await self._launcher.start_process(spec)
        except Exception as exc:  # fail closed on start failure
            argv = self._launcher.build_argv(spec)
            result = BlenderProcessResult(
                argv=tuple(argv),
                returncode=-1,
                stdout="",
                stderr=f"supervisor start failure: {exc}",
                start_failed=True,
            )
            locator = replace(locator, state=STATE_FAILED, reason=str(exc))
            self._persist(locator)
            return locator, self._build_receipt(spec, argv, result, start)

        self._handles[spec.job_id] = handle
        locator = replace(locator, state=STATE_RUNNING, pid=handle.pid, heartbeat_at=self._clock())
        self._persist(locator)

        argv = self._launcher.build_argv(spec)
        result = await self._wait_with_heartbeat(handle, spec, locator, cancel_event)
        receipt = self._build_receipt(spec, argv, result, start)

        if result.cancelled:
            state, reason = STATE_CANCELLED, "cancelled via cancel token/kill"
        elif result.timed_out:
            state, reason = STATE_FAILED, "job exceeded its time budget"
        elif result.start_failed or result.returncode != 0:
            state, reason = STATE_FAILED, f"process exit code {result.returncode}"
        else:
            state, reason = STATE_COMPLETED, ""

        locator = replace(locator, state=state, reason=reason, heartbeat_at=self._clock())
        self._persist(locator)
        self._handles.pop(spec.job_id, None)
        return locator, receipt

    def _build_receipt(self, spec, argv, result, start) -> BlenderExecutionReceipt:
        return BlenderExecutionReceipt.from_process_result(
            job_id=spec.job_id,
            kind=spec.kind,
            executable_path=spec.executable_path,
            argv=argv,
            result=result,
            started_at=start,
            metadata={
                "workspace": spec.job_workspace,
                "timeout_seconds": spec.timeout_seconds,
                "idempotency_key": spec.idempotency_key,
            },
        )

    # ------------------------------------------------------------------
    # Wait + heartbeat + cancel
    # ------------------------------------------------------------------
    async def _wait_with_heartbeat(
        self,
        handle: BlenderProcessHandle,
        spec: BlenderJobSpec,
        locator: BlenderJobLocator,
        cancel_event: Optional[asyncio.Event],
    ) -> BlenderProcessResult:
        deadline = self._clock() + spec.timeout_seconds
        cancel_waiter = None
        if cancel_event is not None:
            cancel_waiter = asyncio.create_task(cancel_event.wait())
        workspace = Path(locator.workspace)

        while True:
            if not handle.is_alive():
                if cancel_waiter is not None and not cancel_waiter.done():
                    cancel_waiter.cancel()
                return await handle.wait(1.0)
            cancel_requested = (
                (cancel_waiter is not None and cancel_waiter.done() and cancel_waiter.result())
                or (workspace / CANCEL_TOKEN_FILENAME).is_file()
            )
            if cancel_requested:
                if cancel_waiter is not None and not cancel_waiter.done():
                    cancel_waiter.cancel()
                return await self._graceful_cancel_and_wait(handle, locator)
            if self._clock() >= deadline:
                if cancel_waiter is not None and not cancel_waiter.done():
                    cancel_waiter.cancel()
                await handle.kill()
                result = await handle.wait(1.0)
                return BlenderProcessResult(
                    argv=result.argv,
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    timed_out=True,
                    pid=result.pid,
                )
            self._persist(replace(locator, heartbeat_at=self._clock()))
            await asyncio.sleep(min(self._heartbeat_seconds, 1.0))

    async def _graceful_cancel_and_wait(
        self, handle: BlenderProcessHandle, locator: BlenderJobLocator
    ) -> BlenderProcessResult:
        """Graceful cancel: durable token file, bounded grace, then kill."""
        self._write_cancel_token(Path(locator.workspace))
        self._persist(replace(locator, state=STATE_CANCELLING))
        grace_deadline = self._clock() + self._cancel_grace_seconds
        while handle.is_alive() and self._clock() < grace_deadline:
            await asyncio.sleep(0.2)
        if handle.is_alive():
            await handle.kill()
        result = await handle.wait(1.0)
        return BlenderProcessResult(
            argv=result.argv,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            cancelled=True,
            pid=result.pid,
        )

    # ------------------------------------------------------------------
    # Public cancel / recovery
    # ------------------------------------------------------------------
    def cancel(self, job_id: str) -> Optional[BlenderJobLocator]:
        """Durable cancel request (works cross-process).

        Writes the `cancel.token` file that the trusted `execute_job.py` and
        the running launch loop both poll; the process exits cleanly (or is
        killed after the grace window) within the next heartbeat tick.
        """
        locator = self.load(job_id)
        if locator is None:
            return None
        self._write_cancel_token(Path(locator.workspace))
        updated = replace(locator, state=STATE_CANCELLING)
        self._persist(updated)
        return updated

    def reconcile(self) -> List[BlenderJobLocator]:
        """Worker-restart recovery: reattach alive jobs, quarantine dead ones.

        Policy (plan Stage B §3): a locator whose PID is still alive is
        REATTACHED (kept RUNNING for the restarted worker); a locator whose
        process is gone is QUARANTINED so no new job is scheduled over it.
        A locator that never reached RUNNING (no PID) is QUARANTINED.
        """
        results: List[BlenderJobLocator] = []
        for locator in self.load_all():
            if locator.state in (STATE_COMPLETED, STATE_FAILED, STATE_CANCELLED, STATE_QUARANTINED):
                continue
            if locator.pid is not None and _pid_alive(locator.pid):
                results.append(replace(locator, state=STATE_RUNNING, reason="reattached by supervisor"))
            else:
                updated = replace(
                    locator,
                    state=STATE_QUARANTINED,
                    reason="process not alive at supervisor recovery",
                )
                self._persist(updated)
                results.append(updated)
        return results

    # ------------------------------------------------------------------
    @staticmethod
    def _write_cancel_token(workspace: Path) -> None:
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / CANCEL_TOKEN_FILENAME).write_text("cancel\n", encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    """Cross-platform liveness check for a PID.

    On POSIX `os.kill(pid, 0)` probes existence. On Windows signal 0 is
    `CTRL_C_EVENT` (NOT a liveness probe — it signals console process
    groups), so we use `OpenProcess` via ctypes instead.
    """
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def _windows_pid_alive(pid: int) -> bool:
    """Probe PID existence on Windows without signaling it."""
    import ctypes

    # PROCESS_QUERY_LIMITED_INFORMATION (0x1000) is sufficient for existence.
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


__all__ = [
    "CANCEL_TOKEN_FILENAME",
    "STATE_STARTING",
    "STATE_RUNNING",
    "STATE_CANCELLING",
    "STATE_COMPLETED",
    "STATE_FAILED",
    "STATE_CANCELLED",
    "STATE_QUARANTINED",
    "BlenderJobLocator",
    "BlenderProcessSupervisor",
]
