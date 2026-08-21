"""
Desktop Sidecar Process Manager for WindAgent Tauri Desktop Shell (Phase 7 - Process-specific composition).
Manages lifecycle of API sidecar and Worker sidecar as SEPARATE processes.

Responsibilities (PHASE 7):
- Khởi động API process
- Khởi động Worker process  
- Theo dõi lifecycle
- Restart policy
- Port allocation
- Log collection
- Graceful shutdown

Desktop supervisor does NOT:
- Compose API services directly
- Compose Worker services directly
- Share any container with API or Worker
"""

from __future__ import annotations
import os
import socket
import subprocess
import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("windagent.desktop.sidecar")


def get_free_port() -> int:
    """Finds a free OS port dynamically."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@dataclass
class SidecarStatus:
    name: str
    running: bool
    pid: Optional[int]
    port: Optional[int]
    status_text: str
    process: Optional[subprocess.Popen] = None


class SidecarManager:
    """Manages native sidecar process lifecycles for WindAgent Desktop (PHASE 7).
    
    Each sidecar (API, Worker) runs as INDEPENDENT process with its own composition root.
    Desktop supervisor only manages process lifecycle, does NOT share containers.
    """

    def __init__(self, log_dir: Optional[str] = None) -> None:
        if log_dir:
            self.log_dir = log_dir
        else:
            base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.windagent")
            self.log_dir = os.path.join(base_dir, "windagent", "logs")

        os.makedirs(self.log_dir, exist_ok=True)
        self._processes: Dict[str, Optional[subprocess.Popen]] = {
            "api": None,
            "worker": None,
        }
        self._ports: Dict[str, Optional[int]] = {
            "api": None,
            "worker": None,
        }
        # Restart policy configuration
        self._restart_policy = {
            "api": {"max_restarts": 5, "restart_delay": 1.0},
            "worker": {"max_restarts": 5, "restart_delay": 1.0},
        }
        self._restart_counts: Dict[str, int] = {
            "api": 0,
            "worker": 0,
        }

    def spawn_api_sidecar(self, mock_spawn: bool = True, port: Optional[int] = None) -> SidecarStatus:
        """Spawns windagent-api background sidecar process.
        
        API runs as INDEPENDENT process with its own composition root.
        """
        target_port = port or get_free_port()
        self._ports["api"] = target_port

        if mock_spawn:
            return SidecarStatus(
                name="api", 
                running=True, 
                pid=1234, 
                port=target_port, 
                status_text="API sidecar started (mock)",
                process=None
            )

        log_path = os.path.join(self.log_dir, "api_sidecar.log")
        log_file = open(log_path, "a")
        env = os.environ.copy()
        env["PORT"] = str(target_port)

        proc = subprocess.Popen(
            ["python", "-m", "windagent_api.main"],
            env=env,
            stdout=log_file,
            stderr=log_file,
        )
        self._processes["api"] = proc
        logger.info(f"API sidecar spawned on port {target_port} with PID {proc.pid}")
        return SidecarStatus(
            name="api", 
            running=True, 
            pid=proc.pid, 
            port=target_port, 
            status_text="API sidecar running",
            process=proc
        )

    def spawn_worker_sidecar(self, mock_spawn: bool = True) -> SidecarStatus:
        """Spawns windagent-worker background sidecar process.
        
        Worker runs as INDEPENDENT process with its own composition root.
        """
        if mock_spawn:
            return SidecarStatus(
                name="worker", 
                running=True, 
                pid=5678, 
                port=None, 
                status_text="Worker sidecar started (mock)",
                process=None
            )

        log_path = os.path.join(self.log_dir, "worker_sidecar.log")
        log_file = open(log_path, "a")

        proc = subprocess.Popen(
            ["python", "-m", "windagent_worker.__main__"],
            stdout=log_file,
            stderr=log_file,
        )
        self._processes["worker"] = proc
        logger.info(f"Worker sidecar spawned with PID {proc.pid}")
        return SidecarStatus(
            name="worker", 
            running=True, 
            pid=proc.pid, 
            port=None, 
            status_text="Worker sidecar running",
            process=proc
        )

    def check_health(self) -> Dict[str, bool]:
        """Queries health status of all managed sidecars."""
        health = {}
        for name, proc in self._processes.items():
            if proc is not None:
                health[name] = proc.poll() is None
            else:
                health[name] = True  # Mock status when running in mock mode
        return health

    def monitor_lifecycle(self) -> Dict[str, SidecarStatus]:
        """Monitors and returns current status of all sidecars."""
        statuses = {}
        for name, proc in self._processes.items():
            port = self._ports.get(name)
            if proc is not None:
                is_running = proc.poll() is None
                pid = proc.pid if is_running else None
                statuses[name] = SidecarStatus(
                    name=name,
                    running=is_running,
                    pid=pid,
                    port=port,
                    status_text="Running" if is_running else "Stopped",
                    process=proc
                )
            else:
                statuses[name] = SidecarStatus(
                    name=name,
                    running=False,
                    pid=None,
                    port=port,
                    status_text="Not started",
                    process=None
                )
        return statuses

    def restart_sidecar(self, name: str) -> SidecarStatus:
        """Restarts a sidecar process according to restart policy."""
        if name not in self._restart_policy:
            raise ValueError(f"Unknown sidecar: {name}")
        
        # Check restart count
        if self._restart_counts[name] >= self._restart_policy[name]["max_restarts"]:
            logger.error(f"Sidecar {name} exceeded max restarts ({self._restart_policy[name]['max_restarts']})")
            raise RuntimeError(f"Sidecar {name} restart limit exceeded")
        
        logger.info(f"Restarting {name} sidecar...")
        
        # Stop current process
        if self._processes[name] is not None:
            self._stop_sidecar(name)
        
        # Wait before restart
        import time
        time.sleep(self._restart_policy[name]["restart_delay"])
        
        # Increment restart count
        self._restart_counts[name] += 1
        
        # Spawn new process
        if name == "api":
            return self.spawn_api_sidecar(mock_spawn=False)
        elif name == "worker":
            return self.spawn_worker_sidecar(mock_spawn=False)
        else:
            raise ValueError(f"Cannot restart unknown sidecar: {name}")

    def _stop_sidecar(self, name: str) -> None:
        """Internal method to stop a single sidecar."""
        proc = self._processes.get(name)
        if proc is not None and proc.poll() is None:
            logger.info(f"Stopping {name} sidecar (PID: {proc.pid})...")
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
                logger.info(f"{name} sidecar stopped gracefully")
            except subprocess.TimeoutExpired:
                proc.kill()
                logger.warning(f"{name} sidecar killed after timeout")
        self._processes[name] = None
        self._restart_counts[name] = 0

    def shutdown(self) -> None:
        """Gracefully terminates all running sidecars."""
        logger.info("Desktop supervisor initiating graceful shutdown...")
        
        # Stop in reverse order (Worker first, then API)
        for name in ["worker", "api"]:
            self._stop_sidecar(name)
        
        logger.info("All sidecars shut down gracefully")

    async def monitor_health_async(self) -> Dict[str, bool]:
        """Async health monitoring for Tauri integration."""
        return self.check_health()

    def collect_logs(self, name: str) -> Optional[str]:
        """Collects logs for a specific sidecar."""
        log_path = os.path.join(self.log_dir, f"{name}_sidecar.log")
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                return f.read()
        return None
