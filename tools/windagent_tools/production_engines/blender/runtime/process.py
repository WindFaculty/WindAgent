"""
VP3D Phase 3 — Blender process boundary (fake-injectable).

`BlenderProcessPort` is the seam that lets the whole runtime stack be
contract-tested with a FAKE executable in CI (plan Stage B §3 gate). The real
implementation launches `blender.exe` with an argv list (never a shell),
bounded output, timeout and cancellation — mirroring the browser runtime's
`SubprocessAgentBrowserProcess` pattern.

Two interfaces:

- `start()`  -> a running `BlenderProcessHandle` with the PID known BEFORE the
  process finishes (required by the supervisor to persist PID/job locators for
  crash recovery);
- `run()`    -> convenience that starts + waits, returning a bounded result.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, Sequence, runtime_checkable

MAX_OUTPUT_BYTES = 4_000_000
MAX_STDERR_BYTES = 1_000_000


@dataclass(frozen=True)
class BlenderProcessResult:
    """Bounded result of one blender process run."""

    argv: tuple
    returncode: int
    stdout: str  # already UTF-8-replace decoded and bounded
    stderr: str
    timed_out: bool = False
    cancelled: bool = False
    start_failed: bool = False
    pid: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout_chars": len(self.stdout),
            "stderr_chars": len(self.stderr),
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "start_failed": self.start_failed,
            "pid": self.pid,
        }


class BlenderProcessHandle:
    """A running blender process with a known PID."""

    def __init__(
        self,
        *,
        process: asyncio.subprocess.Process,
        argv: tuple,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        max_stderr_bytes: int = MAX_STDERR_BYTES,
    ) -> None:
        self._process = process
        self.argv = argv
        self.pid = process.pid
        self._max_output_bytes = max_output_bytes
        self._max_stderr_bytes = max_stderr_bytes
        self._stdout: bytearray = bytearray()
        self._stderr: bytearray = bytearray()
        self._readers: list = []

    def is_alive(self) -> bool:
        return self._process.returncode is None

    async def _drain(self) -> None:
        async def _reader(stream, sink: bytearray) -> None:
            while True:
                chunk = await stream.read(65536)
                if not chunk:
                    break
                if len(sink) < self._max_output_bytes:
                    sink.extend(chunk[: self._max_output_bytes - len(sink)])

        if not self._readers:
            self._readers = [
                asyncio.create_task(_reader(self._process.stdout, self._stdout)),
                asyncio.create_task(_reader(self._process.stderr, self._stderr)),
            ]

    async def wait(self, timeout_seconds: float) -> BlenderProcessResult:
        """Wait for the process, then return the bounded result."""
        await self._drain()
        timed_out = False
        try:
            await asyncio.wait_for(self._process.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            with _suppress():
                self._process.kill()
        await asyncio.gather(*self._readers, return_exceptions=True)
        return BlenderProcessResult(
            argv=self.argv,
            returncode=self._process.returncode if self._process.returncode is not None else -1,
            stdout=bytes(self._stdout).decode("utf-8", "replace"),
            stderr=bytes(self._stderr).decode("utf-8", "replace")[: self._max_stderr_bytes],
            timed_out=timed_out,
            pid=self.pid,
        )

    async def kill(self) -> None:
        with _suppress():
            self._process.kill()
        with _suppress():
            await self._process.wait()

    async def terminate(self) -> None:
        """Graceful request; falls back to kill when the platform cannot signal."""
        with _suppress():
            self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            with _suppress():
                self._process.kill()
            with _suppress():
                await self._process.wait()


@runtime_checkable
class BlenderProcessPort(Protocol):
    """Run one bounded blender process (real or fake)."""

    async def start(
        self,
        argv: Sequence[str],
        *,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> BlenderProcessHandle:
        ...

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
        env: Optional[Dict[str, str]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        cwd: Optional[str] = None,
    ) -> BlenderProcessResult:
        ...


class SubprocessBlenderProcess:
    """Real blender.exe process: argv list, no shell, bounded output."""

    def __init__(
        self,
        *,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        max_stderr_bytes: int = MAX_STDERR_BYTES,
    ) -> None:
        self._max_output_bytes = max_output_bytes
        self._max_stderr_bytes = max_stderr_bytes

    async def start(
        self,
        argv: Sequence[str],
        *,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> BlenderProcessHandle:
        argv_tuple = tuple(str(a) for a in argv)
        process = await asyncio.create_subprocess_exec(
            *argv_tuple,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )
        return BlenderProcessHandle(
            process=process,
            argv=argv_tuple,
            max_output_bytes=self._max_output_bytes,
            max_stderr_bytes=self._max_stderr_bytes,
        )

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
        env: Optional[Dict[str, str]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        cwd: Optional[str] = None,
    ) -> BlenderProcessResult:
        argv_tuple = tuple(str(a) for a in argv)
        try:
            handle = await self.start(argv_tuple, env=env, cwd=cwd)
        except (OSError, ValueError) as exc:
            return BlenderProcessResult(
                argv=argv_tuple,
                returncode=-1,
                stdout="",
                stderr=f"process start failure: {exc}",
                start_failed=True,
            )
        if cancel_event is not None:
            # Wake a poller so a cancel mid-run is honored by wait().
            cancel_waiter = asyncio.create_task(cancel_event.wait())

            async def _cancel_aware_wait():
                done, _ = await asyncio.wait(
                    {cancel_waiter, asyncio.create_task(handle.wait(timeout_seconds))},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancel_event.is_set():
                    await handle.kill()
                    result = await handle.wait(1.0)
                    return BlenderProcessResult(
                        argv=result.argv,
                        returncode=result.returncode,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        timed_out=result.timed_out,
                        cancelled=True,
                        pid=result.pid,
                    )
                for task in done:
                    result = task.result()
                    return result
                return await handle.wait(timeout_seconds)

            return await _cancel_aware_wait()

        return await handle.wait(timeout_seconds)


class _suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


__all__ = [
    "MAX_OUTPUT_BYTES",
    "MAX_STDERR_BYTES",
    "BlenderProcessResult",
    "BlenderProcessHandle",
    "BlenderProcessPort",
    "SubprocessBlenderProcess",
]
