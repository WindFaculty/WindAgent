"""
Sandbox Isolation and Execution Environment Context for WindAgent V2 (Phase 18).
"""

from __future__ import annotations
import os
import tempfile
from dataclasses import dataclass
from typing import Optional


@dataclass
class SandboxConfig:
    enabled: bool = True
    timeout_sec: float = 300.0
    memory_limit_mb: int = 512
    allow_network: bool = True
    workdir: Optional[str] = None


class ExecutionSandbox:
    """Manages isolated execution parameters and workspace directory context."""

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._temp_dir: Optional[str] = None

    def __enter__(self) -> str:
        if self.config.workdir and os.path.exists(self.config.workdir):
            return self.config.workdir
        self._temp_dir = tempfile.mkdtemp(prefix="windagent_sandbox_")
        return self._temp_dir

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                import shutil
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
