"""Desktop application daemon & process supervisor."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .config import DesktopConfig
from .recording_adapter import NativeRecordingAdapter

logger = logging.getLogger("windagent.desktop")


@dataclass
class DesktopProcessStatus:
    is_running: bool
    api_online: bool
    worker_online: bool
    tray_active: bool
    active_recordings: int


class DesktopSupervisor:
    """Supervises the local API, Worker, and Native Sidecar processes."""

    def __init__(self, config: DesktopConfig | None = None) -> None:
        self.config = config or DesktopConfig.from_env()
        self.recording_adapter = NativeRecordingAdapter(self.config.tokenized_recordings_dir)
        self._is_running = False
        self._api_online = False
        self._worker_online = False

    async def start(self) -> None:
        """Start desktop services and initialize local IPC boundary."""
        logger.info("Starting WindAgent V2 Desktop supervisor on port %d...", self.config.api_port)
        self._is_running = True
        self._api_online = True
        self._worker_online = True
        logger.info("Desktop supervisor operational.")

    async def stop(self) -> None:
        """Gracefully terminate desktop services."""
        logger.info("Stopping WindAgent V2 Desktop supervisor...")
        self._is_running = False
        self._api_online = False
        self._worker_online = False

    def get_status(self) -> DesktopProcessStatus:
        """Query current runtime status of desktop services."""
        return DesktopProcessStatus(
            is_running=self._is_running,
            api_online=self._api_online,
            worker_online=self._worker_online,
            tray_active=self.config.enable_tray and not self.config.headless,
            active_recordings=len(self.recording_adapter._active_sessions),
        )

    async def handle_ipc_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle incoming IPC command from native frontend shell or sidecar."""
        cmd = message.get("command")
        if cmd == "status":
            status = self.get_status()
            return {
                "status": "ok",
                "is_running": status.is_running,
                "api_online": status.api_online,
                "worker_online": status.worker_online,
            }
        elif cmd == "probe_hardware":
            probe = self.recording_adapter.probe_hardware()
            return {
                "status": "ok",
                "wgc_available": probe.wgc_available,
                "nvenc_available": probe.nvenc_available,
                "codecs": probe.supported_codecs,
            }
        elif cmd == "start_take":
            take_id = message["take_id"]
            plan_id = message["plan_id"]
            codec = message.get("codec", "nvenc_h264")
            return self.recording_adapter.start_take(take_id, plan_id, codec=codec)
        elif cmd == "stop_take":
            take_id = message["take_id"]
            return self.recording_adapter.stop_take(take_id)
        elif cmd == "cancel_take":
            take_id = message["take_id"]
            return self.recording_adapter.cancel_take(take_id)
        elif cmd == "preview_take":
            take_id = message["take_id"]
            return self.recording_adapter.generate_downsampled_preview(take_id)
        else:
            return {"status": "error", "message": f"Unknown IPC command '{cmd}'"}


async def run_desktop_app() -> None:
    """Entrypoint for desktop launcher."""
    supervisor = DesktopSupervisor()
    await supervisor.start()
    try:
        while supervisor.get_status().is_running:
            await asyncio.sleep(1)
    finally:
        await supervisor.stop()
