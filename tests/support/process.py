"""Process helpers for e2e / multiprocess tests.

Extracted from ``tests/integration/test_phase14_two_process_e2e.py`` and
``tests/integration/test_phase_g25_session_recovery.py`` to provide a single,
well-tested implementation for:

* finding a free TCP port
* waiting for an HTTP URL to become ready / return an expected status
* waiting for a subprocess to exit with bounded timeout and cleanup
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import httpx


def free_port() -> int:
    """Return a free TCP port on 127.0.0.1 (ephemeral bind)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_url(
    url: str,
    *,
    timeout: float = 40.0,
    expect_status: int = 200,
    interval: float = 0.3,
) -> None:
    """Block until ``GET url`` returns ``expect_status`` or timeout.

    Raises ``RuntimeError`` on timeout.
    """
    deadline = time.time() + timeout
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2.0).status_code == expect_status:
                return
        except Exception as exc:  # noqa: BLE001 — network may not be up yet
            last_exc = exc
        time.sleep(interval)
    raise RuntimeError(f"{url} not ready in {timeout}s (last error: {last_exc})")


def wait_exit(proc: subprocess.Popen, *, timeout: float = 10.0) -> None:
    """Wait for ``proc`` to exit, killing it if it does not within ``timeout``."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.2)
    proc.kill()
    proc.wait(timeout=5)


@contextmanager
def managed_subprocess(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | str | None = None,
    log_path: Path | None = None,
) -> Generator[subprocess.Popen, None, None]:
    """Context manager that ensures ``Popen`` is terminated on exit."""
    proc_env = {**os.environ, **(env or {})}
    # Ensure PYTHONPATH includes workspace roots for subprocess imports
    stdout = open(log_path, "w") if log_path else None  # noqa: SIM115
    proc = subprocess.Popen(
        args,
        env=proc_env,
        cwd=str(cwd) if cwd else None,
        stdout=stdout,
        stderr=subprocess.STDOUT if stdout else None,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if stdout:
            stdout.close()


def build_workspace_pythonpath(root: Path) -> str:
    """Return a PYTHONPATH that exposes all workspace packages to a subprocess."""
    package_roots = [
        root / path
        for path in (
            "apps/api",
            "apps/cli",
            "apps/worker",
            "core",
            "orchestration",
            "intelligence",
            "providers",
            "tools",
            "workflows",
            "verification",
            "context",
            "memory",
            "execution",
            "storage",
            "observability",
            "evals",
            "plugins",
            "skills",
        )
    ]
    inherited = os.environ.get("PYTHONPATH")
    if inherited:
        package_roots.append(Path(inherited))
    return os.pathsep.join(str(p) for p in package_roots)


def ensure_schema(db_url: str, root: Path | None = None) -> None:
    """Pre-create canonical schema so child processes don't race on DDL."""
    import textwrap

    root = root or Path(__file__).resolve().parents[2]
    script = textwrap.dedent(
        """
        import asyncio, os
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.orm.models import BaseORM
        asyncio.run(DatabaseManager(os.environ['WINDAGENT_DATABASE_URL']).create_tables(BaseORM.metadata))
        """
    )
    env = {**os.environ, "WINDAGENT_DATABASE_URL": db_url}
    # Write to a temp file to avoid shell quoting issues on Windows
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        subprocess.run([sys.executable, fname], env=env, cwd=str(root), check=True)
    finally:
        Path(fname).unlink(missing_ok=True)
