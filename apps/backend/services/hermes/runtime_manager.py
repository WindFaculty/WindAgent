"""Supervisor for the local Hermes subprocess."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from services.hermes.config import HermesConfig

log = logging.getLogger(__name__)


class HermesRuntimeManager:
    """Manages the lifecycle, health checks, and process tree of the Hermes API Server."""

    def __init__(self, config: HermesConfig, event_bus: Any) -> None:
        self.config = config
        self.event_bus = event_bus
        self.process: Optional[subprocess.Popen] = None
        self.status = "disabled" if not config.enabled else "stopped"
        
        # Restart policy parameters
        self.restart_attempts = 0
        self.max_restart_attempts = 3
        self.last_crash_time = 0.0
        self.cooldown_period_s = 60.0
        self.backoff_delays = [1.0, 3.0, 10.0]
        
        self._probe_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the Hermes supervisor and background task."""
        if not self.config.enabled:
            self.status = "disabled"
            log.info("Hermes integration is disabled via configuration.")
            return

        self._shutdown_event.clear()
        self.status = "starting"
        
        # 1. Try to see if it is already running externally
        if await self.probe_health():
            self.status = "healthy"
            log.info("Hermes server is already running externally at %s", self.config.base_url)
            self._start_probe_loop()
            return

        # 2. Check if we should auto-start it
        if not self.config.auto_start:
            self.status = "failed"
            log.warning("Hermes server is offline and WINDAGENT_HERMES_AUTO_START is false.")
            return

        await self._spawn_process()
        self._start_probe_loop()

    def _start_probe_loop(self) -> None:
        """Start background health check loop."""
        if self._probe_task is None or self._probe_task.done():
            self._probe_task = asyncio.create_task(self._health_probe_loop(), name="hermes-supervisor-probe")

    async def stop(self) -> None:
        """Stop the supervised process and background tasks."""
        self._shutdown_event.set()
        if self._probe_task:
            self._probe_task.cancel()
            try:
                await self._probe_task
            except asyncio.CancelledError:
                pass
            self._probe_task = None

        await self._terminate_process()
        self.status = "stopped"
        log.info("Hermes supervisor stopped.")

    async def restart(self) -> None:
        """Restart the process."""
        self.status = "restarting"
        await self.stop()
        self.restart_attempts = 0
        await self.start()

    async def probe_health(self) -> bool:
        """Probe the server's liveness endpoint. Returns True if online."""
        url = f"{self.config.base_url}/health"
        async with httpx.AsyncClient(timeout=1.0) as client:
            try:
                resp = await client.get(url)
                return resp.status_code == 200
            except httpx.HTTPError:
                return False

    async def get_capabilities(self) -> Dict[str, Any]:
        """Fetch server capabilities from `/v1/capabilities` or fallback."""
        url = f"{self.config.base_url}/v1/capabilities"
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
        
        # Standard fallback capabilities
        return {
            "enabled": True,
            "version": "0.18.2",
            "api_server": True,
            "runs_api": True,
            "session_streaming": True,
            "approval": True,
            "stop": True,
            "pause": False,
        }

    async def _spawn_process(self) -> bool:
        """Launch the hermes serve subprocess."""
        self.status = "starting"
        
        # Ensure we have an API key configured so the client can authenticate.
        # If the key is not set, we generate a default fallback key.
        if not self.config.api_key:
            self.config.api_key = "my-secret-key-16-chars"
            log.info("No API key configured for Hermes; generated default fallback key.")

        # Extract port from base_url (default to 8642)
        from urllib.parse import urlparse
        try:
            parsed = urlparse(self.config.base_url)
            port = str(parsed.port) if parsed.port else "8642"
        except Exception:
            port = "8642"

        # Use 'gateway run' to start the Hermes gateway (which exposes Platform.API_SERVER)
        cmd = [self.config.executable, "gateway", "run"]
        
        # Ensure log dir exists
        log_dir = Path("artifacts/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "hermes_stdout.log"
        
        log.info("Spawning Hermes gateway: %s (logs redirected to %s)", " ".join(cmd), log_file)
        
        try:
            # Inject required environment variables to activate and authorize api_server
            env = os.environ.copy()
            env["API_SERVER_ENABLED"] = "1"
            env["API_SERVER_KEY"] = self.config.api_key
            env["API_SERVER_PORT"] = port
            
            # We open stdout/stderr in append/write mode
            stdout_handle = open(log_file, "a", encoding="utf-8")
            self.process = subprocess.Popen(
                cmd,
                stdout=stdout_handle,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
        except Exception:
            log.exception("Failed to launch Hermes subprocess")
            self.status = "failed"
            return False

        # Wait for the server to bind
        for attempt in range(15):
            if self._shutdown_event.is_set():
                return False
            # Check if process exited early
            if self.process.poll() is not None:
                log.error("Hermes subprocess exited early with code %s", self.process.returncode)
                self.status = "failed"
                return False
            
            if await self.probe_health():
                self.status = "healthy"
                self.restart_attempts = 0
                log.info("Hermes server successfully started and is healthy.")
                return True
            
            await asyncio.sleep(1.0)

        log.warning("Hermes server did not become healthy within 15 seconds.")
        self.status = "degraded"
        return False

    async def _terminate_process(self) -> None:
        """Kill the subprocess and all children safely on Windows."""
        if not self.process:
            return
            
        pid = self.process.pid
        log.info("Terminating Hermes subprocess PID %d", pid)
        
        # Check if process is still running
        if self.process.poll() is None:
            if os.name == "nt":
                # Use taskkill to kill the process tree (/T) forcefully (/F)
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False
                    )
                except Exception:
                    self.process.kill()
            else:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        
        self.process = None

    async def _health_probe_loop(self) -> None:
        """Background health check task."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(10.0)
            
            # Check if process died
            if self.process and self.process.poll() is not None:
                log.warning("Supervised Hermes process exited with code %s", self.process.returncode)
                self.process = None
                await self._handle_crash()
                continue

            healthy = await self.probe_health()
            if healthy:
                self.status = "healthy"
            else:
                if self.status == "healthy":
                    log.warning("Hermes liveness probe failed; status is now degraded.")
                    self.status = "degraded"

    async def _handle_crash(self) -> None:
        """Manage auto-restart with exponential backoff and crash cooldown."""
        now = time.time()
        
        # Check cooldown
        if now - self.last_crash_time > self.cooldown_period_s:
            # Reset attempts if it ran stable for a while
            self.restart_attempts = 0

        self.last_crash_time = now

        if self.restart_attempts >= self.max_restart_attempts:
            self.status = "failed"
            log.error("Hermes crashed repeatedly. Max restart attempts reached. Giving up.")
            return

        delay = self.backoff_delays[min(self.restart_attempts, len(self.backoff_delays) - 1)]
        self.restart_attempts += 1
        self.status = "restarting"
        
        log.info("Scheduling restart attempt %d/%d in %.1fs...", 
                 self.restart_attempts, self.max_restart_attempts, delay)
                 
        await asyncio.sleep(delay)
        if not self._shutdown_event.is_set() and self.config.auto_start:
            await self._spawn_process()
