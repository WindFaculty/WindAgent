"""Desktop platform configuration and local discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DesktopConfig:
    """Runtime configuration for the desktop supervisor."""

    api_port: int = 8000
    host: str = "127.0.0.1"
    headless: bool = False
    enable_tray: bool = True
    workspace_root: Path = field(default_factory=lambda: Path(os.environ.get("WINDAGENT_WORKSPACE_ROOT", "./workspace")).resolve())
    tokenized_recordings_dir: Path = field(default_factory=lambda: Path(os.environ.get("WINDAGENT_RECORDINGS_DIR", "./recordings")).resolve())
    ipc_socket_path: str = "ipc://windagent-desktop.sock"
    wgc_supported: bool = True
    nvenc_supported: bool = True

    @classmethod
    def from_env(cls) -> DesktopConfig:
        return cls(
            api_port=int(os.environ.get("WINDAGENT_API_PORT", "8000")),
            host=os.environ.get("WINDAGENT_HOST", "127.0.0.1"),
            headless=os.environ.get("WINDAGENT_HEADLESS", "0") == "1",
            enable_tray=os.environ.get("WINDAGENT_TRAY", "1") == "1",
        )
