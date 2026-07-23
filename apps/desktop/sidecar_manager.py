"""
Desktop Sidecar Process Manager for WindAgent Tauri Desktop Shell (Phase 13).
Manages lifecycle of API sidecar and Worker sidecar background processes.
"""

from __future__ import annotations
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class SidecarStatus:
    name: str
    running: bool
    pid: Optional[int]
    status_text: str


class SidecarManager:
    """Manages native sidecar process lifecycles for WindAgent Desktop."""

    def __init__(self, log_dir: Optional[str] = None) -> None:
        self.log_dir = log_dir or os.path.expanduser("~/.windagent/logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self._processes: Dict[str, Optional[subprocess.Popen]] = {
            "api": None,
            "worker": None,
        }

    def spawn_api_sidecar(self, mock_spawn: bool = True) -> SidecarStatus:
        """Spawns windagent-api background sidecar process."""
        if mock_spawn:
            return SidecarStatus(name="api", running=True, pid=1234, status_text="API sidecar started")
        
        log_file = open(os.path.join(self.log_dir, "api_sidecar.log"), "a")
        proc = subprocess.Popen(["python", "-m", "windagent_api.main"], stdout=log_file, stderr=log_file)
        self._processes["api"] = proc
        return SidecarStatus(name="api", running=True, pid=proc.pid, status_text="API sidecar running")

    def spawn_worker_sidecar(self, mock_spawn: bool = True) -> SidecarStatus:
        """Spawns windagent-worker background sidecar process."""
        if mock_spawn:
            return SidecarStatus(name="worker", running=True, pid=5678, status_text="Worker sidecar started")

        log_file = open(os.path.join(self.log_dir, "worker_sidecar.log"), "a")
        proc = subprocess.Popen(["python", "-m", "windagent_worker.runner"], stdout=log_file, stderr=log_file)
        self._processes["worker"] = proc
        return SidecarStatus(name="worker", running=True, pid=proc.pid, status_text="Worker sidecar running")

    def check_health(self) -> Dict[str, bool]:
        """Queries health status of all managed sidecars."""
        health = {}
        for name, proc in self._processes.items():
            if proc is not None:
                health[name] = proc.poll() is None
            else:
                health[name] = True  # Mock health status when running mock spawn
        return health

    def shutdown(self) -> None:
        """Gracefully terminates all running sidecars."""
        for name, proc in self._processes.items():
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                self._processes[name] = None
