"""Supervised API/worker topology for Studio certification runs.

The launcher is deliberately small and process-oriented: it owns only the
processes it starts, gives API and worker one immutable configuration, and
persists enough telemetry to explain the first broken process hop.  It does
not decide a certification verdict and it never repairs certification state.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from scripts.studio_roadmap.c7_slice_harness import CANONICAL_MODEL, _get

REPO_ROOT = Path(__file__).resolve().parents[2]
CERTIFICATION_ENV_KEYS = (
    "WINDAGENT_DATABASE_URL",
    "WINDAGENT_CERTIFICATION_MODE",
    "WINDAGENT_STUDIO_RUNTIME",
    "WINDAGENT_STUDIO_MODEL_ROUTE",
    "WINDAGENT_STUDIO_CANONICAL_MODEL",
    "WINDAGENT_SOURCE_SHA",
    "OLLAMA_BASE_URL",
)


def configure_utf8_stdio(*streams: Any) -> None:
    """Make certification console output Unicode-safe on Windows hosts."""
    targets = streams or (sys.stdout, sys.stderr)
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


SECRET_MARKERS = ("authorization", "credential", "password", "secret", "token", "api_key")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "workspace"


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-invalid-url>"
    if not parsed.scheme:
        return value
    # ponytail: file-backed sqlite URLs carry no credentials and the
    # urlsplit/urlunsplit roundtrip drops a slash from "///" absolute paths.
    if parsed.scheme.startswith("sqlite"):
        return value
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def sanitize_environment(env: Dict[str, str]) -> Dict[str, str]:
    """Return a certification-only manifest without credentials or tokens."""

    manifest: Dict[str, str] = {}
    for key in CERTIFICATION_ENV_KEYS:
        if key not in env:
            continue
        value = env[key]
        if any(marker in key.lower() for marker in SECRET_MARKERS):
            manifest[key] = "<redacted>"
        elif "://" in value:
            manifest[key] = _sanitize_url(value)
        else:
            manifest[key] = value
    return manifest


def prepare_certification_database(db_url: str) -> Optional[Path]:
    """Create only the parent directory for a file-backed certification DB."""

    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    prefix = next((item for item in prefixes if db_url.startswith(item)), None)
    if prefix is None:
        return None
    raw = db_url[len(prefix) :]
    if not raw or raw == ":memory:":
        raise ValueError("certification requires a file-backed SQLite database")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class ProcessReceipt:
    name: str
    command: list[str]
    cwd: str
    environment: Dict[str, str]
    config_digest: str
    candidate_sha: str
    python_version: str
    package_version: str
    stdout_log: str
    stderr_log: str
    pid: Optional[int] = None
    started_at: Optional[str] = None
    ready_at: Optional[str] = None
    ended_at: Optional[str] = None
    exit_code: Optional[int] = None
    unexpected_exit: bool = False
    listener_alive_at_failure: Optional[bool] = None
    stdout_tail: list[str] = field(default_factory=list)
    stderr_tail: list[str] = field(default_factory=list)


@dataclass
class _ManagedProcess:
    receipt: ProcessReceipt
    process: subprocess.Popen[Any]
    stdout_handle: Any
    stderr_handle: Any


class CertificationProcessError(RuntimeError):
    """A managed certification process failed or became unreachable."""

    def __init__(self, message: str, *, first_broken_hop: Dict[str, Any]):
        super().__init__(message)
        self.first_broken_hop = first_broken_hop


class CertificationLauncher:
    """Own an API/worker pair and persist process lifecycle receipts."""

    def __init__(
        self,
        *,
        db_url: str,
        api_base: str = "http://127.0.0.1:8878",
        canonical_model: str = CANONICAL_MODEL,
        log_dir: Path = REPO_ROOT / ".tmp" / "studio-certification",
        poll_interval: float = 0.25,
    ) -> None:
        if db_url in {"", "sqlite+aiosqlite:///:memory:", "sqlite:///:memory:"}:
            raise ValueError("certification requires an explicit durable database URL")
        prepare_certification_database(db_url)
        self.db_url = db_url
        self.api_base = api_base.rstrip("/")
        self.canonical_model = canonical_model.strip()
        if not self.canonical_model:
            raise ValueError("certification requires a canonical model")
        self.log_dir = log_dir
        self.poll_interval = poll_interval
        self.candidate_sha = git_sha()
        self.receipt_path = self.log_dir / "process-receipts.json"
        self._processes: Dict[str, _ManagedProcess] = {}
        self._receipts: list[ProcessReceipt] = []
        self._stop_watchdog = threading.Event()
        self._watchdog: Optional[threading.Thread] = None
        self._unexpected: Optional[Dict[str, Any]] = None
        self._expected_stops: set[str] = set()
        self._lock = threading.Lock()

    def environment(self) -> Dict[str, str]:
        env = os.environ.copy()
        legacy = env.get("WIND_STUDIO_CERTIFICATION")
        if legacy and legacy.lower() not in {"1", "true", "yes", "on"}:
            raise ValueError("legacy and canonical certification flags conflict")
        env.update(
            {
                "WINDAGENT_DATABASE_URL": self.db_url,
                "WINDAGENT_CERTIFICATION_MODE": "1",
                "WINDAGENT_STUDIO_RUNTIME": "1",
                "WINDAGENT_STUDIO_MODEL_ROUTE": "1",
                "WINDAGENT_STUDIO_CANONICAL_MODEL": self.canonical_model,
                "WINDAGENT_SOURCE_SHA": self.candidate_sha,
                "PYTHONUNBUFFERED": "1",
            }
        )
        env.pop("WIND_STUDIO_CERTIFICATION", None)
        for unsafe in ("WINDAGENT_FAKE_RUNTIME", "WINDAGENT_MODEL_BACKEND"):
            env.pop(unsafe, None)
        return env

    def _command(self, name: str) -> list[str]:
        if name == "api":
            parsed = urlsplit(self.api_base)
            return [
                sys.executable,
                "-m",
                "uvicorn",
                "windagent_api.main:app",
                "--host",
                parsed.hostname or "127.0.0.1",
                "--port",
                str(parsed.port or 8878),
            ]
        if name == "worker":
            return [sys.executable, "-m", "windagent_worker"]
        raise ValueError(f"unsupported managed process: {name}")

    def _new_receipt(self, name: str, command: list[str], env: Dict[str, str]) -> ProcessReceipt:
        manifest = sanitize_environment(env)
        digest = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return ProcessReceipt(
            name=name,
            command=command,
            cwd=str(REPO_ROOT),
            environment=manifest,
            config_digest=digest,
            candidate_sha=self.candidate_sha,
            python_version=platform.python_version(),
            package_version=_package_version(f"windagent-{name}"),
            stdout_log=str(self.log_dir / f"{name}.stdout.log"),
            stderr_log=str(self.log_dir / f"{name}.stderr.log"),
        )

    def _persist_receipts(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "candidate_sha": self.candidate_sha,
            "database_url": _sanitize_url(self.db_url),
            "api_base": _sanitize_url(self.api_base),
            "generated_at": utc_now_iso(),
            "first_broken_hop": self._unexpected,
            "processes": [asdict(receipt) for receipt in self._receipts],
        }
        temporary = self.receipt_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.receipt_path)

    @staticmethod
    def _tail(path: str, *, lines: int = 40) -> list[str]:
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        except OSError:
            return []

    def start(self, name: str) -> None:
        existing = self._processes.get(name)
        if existing and existing.process.poll() is None:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        env = self.environment()
        command = self._command(name)
        receipt = self._new_receipt(name, command, env)
        stdout_handle = Path(receipt.stdout_log).open("a", encoding="utf-8")
        stderr_handle = Path(receipt.stderr_log).open("a", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        receipt.pid = process.pid
        receipt.started_at = utc_now_iso()
        self._processes[name] = _ManagedProcess(receipt, process, stdout_handle, stderr_handle)
        self._receipts.append(receipt)
        self._persist_receipts()
        self._ensure_watchdog()

    def pid(self, name: str) -> Optional[int]:
        managed = self._processes.get(name)
        return managed.process.pid if managed and managed.process.poll() is None else None

    def start_api(self, *, readiness_timeout: float = 60) -> None:
        self.start("api")
        deadline = time.monotonic() + readiness_timeout
        last_error: Optional[Exception] = None
        while time.monotonic() < deadline:
            self.raise_if_unhealthy()
            try:
                if _get(self.api_base, "/api/v3/studio/capabilities")[0] == 200:
                    self._processes["api"].receipt.ready_at = utc_now_iso()
                    self._persist_receipts()
                    return
            except (OSError, ValueError) as exc:
                last_error = exc
            time.sleep(0.25)
        self._record_listener_failure("api", last_error)
        self.raise_if_unhealthy()

    def start_worker(self) -> None:
        self.start("worker")
        managed = self._processes["worker"]
        time.sleep(0.1)
        if managed.process.poll() is not None:
            self._record_exit("worker", unexpected=True)
            self.raise_if_unhealthy()
        managed.receipt.ready_at = utc_now_iso()
        self._persist_receipts()

    def start_all(self) -> None:
        self.start_api()
        self.start_worker()

    def _ensure_watchdog(self) -> None:
        if self._watchdog and self._watchdog.is_alive():
            return
        self._stop_watchdog.clear()
        self._watchdog = threading.Thread(
            target=self._watch_processes,
            name="studio-certification-watchdog",
            daemon=True,
        )
        self._watchdog.start()

    def _watch_processes(self) -> None:
        while not self._stop_watchdog.wait(self.poll_interval):
            for name, managed in list(self._processes.items()):
                if managed.process.poll() is not None and managed.receipt.ended_at is None:
                    self._record_exit(name, unexpected=name not in self._expected_stops)

    def _api_listener_alive(self) -> bool:
        try:
            return _get(self.api_base, "/api/v3/studio/capabilities")[0] == 200
        except (OSError, ValueError):
            return False

    def _record_exit(self, name: str, *, unexpected: bool) -> None:
        with self._lock:
            managed = self._processes[name]
            receipt = managed.receipt
            if receipt.ended_at is not None:
                return
            receipt.exit_code = managed.process.poll()
            receipt.ended_at = utc_now_iso()
            receipt.unexpected_exit = unexpected
            receipt.listener_alive_at_failure = self._api_listener_alive() if name == "api" else None
            managed.stdout_handle.flush()
            managed.stderr_handle.flush()
            receipt.stdout_tail = self._tail(receipt.stdout_log)
            receipt.stderr_tail = self._tail(receipt.stderr_log)
            managed.stdout_handle.close()
            managed.stderr_handle.close()
            if unexpected and self._unexpected is None:
                self._unexpected = {
                    "process": name,
                    "failure": "process_exited",
                    "pid": receipt.pid,
                    "exit_code": receipt.exit_code,
                    "detected_at": utc_now_iso(),
                    "stderr_tail": receipt.stderr_tail,
                }
            self._persist_receipts()

    def _record_listener_failure(self, name: str, error: Optional[Exception]) -> None:
        with self._lock:
            managed = self._processes[name]
            if self._unexpected is None:
                self._unexpected = {
                    "process": name,
                    "failure": (
                        "listener_unreachable_process_alive"
                        if managed.process.poll() is None
                        else "process_exited"
                    ),
                    "pid": managed.receipt.pid,
                    "exit_code": managed.process.poll(),
                    "detected_at": utc_now_iso(),
                    "probe_error": repr(error) if error else None,
                }
            self._persist_receipts()

    def raise_if_unhealthy(self) -> None:
        if self._unexpected:
            raise CertificationProcessError(
                "certification topology failed at its first broken process hop",
                first_broken_hop=dict(self._unexpected),
            )

    def run_guarded(
        self, operation: Callable[[Callable[[], None]], Any]
    ) -> Any:
        """Run an operation that cooperatively checks the topology watchdog."""

        self.raise_if_unhealthy()
        try:
            result = operation(self.raise_if_unhealthy)
        except Exception:
            self.raise_if_unhealthy()
            raise
        self.raise_if_unhealthy()
        return result

    def stop(self, name: str, *, force: bool = False) -> None:
        managed = self._processes.get(name)
        if not managed or managed.receipt.ended_at is not None:
            return
        process = managed.process
        if process.poll() is None:
            self._expected_stops.add(name)
            process.kill() if force else process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        self._record_exit(name, unexpected=False)
        self._expected_stops.discard(name)

    def stop_all(self) -> None:
        self._stop_watchdog.set()
        self.stop("worker")
        self.stop("api")
        if self._watchdog and self._watchdog.is_alive():
            self._watchdog.join(timeout=2)
        for managed in self._processes.values():
            managed.stdout_handle.close()
            managed.stderr_handle.close()

    def __enter__(self) -> CertificationLauncher:
        self.start_all()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.stop_all()


__all__ = [
    "CertificationLauncher",
    "CertificationProcessError",
    "ProcessReceipt",
    "git_sha",
    "prepare_certification_database",
    "sanitize_environment",
]
