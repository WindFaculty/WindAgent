"""
VP3D Phase 3 — Blender installation detection (plan Stage B §3 backlog item 1).

`BlenderInstallationDetector` resolves candidate `blender.exe` paths with
priority:

1. configured path (explicit config wins; NEVER a hard-coded per-machine path);
2. PATH (`shutil.which`);
3. Windows standard locations (`C:\\Program Files\\Blender Foundation\\Blender */blender.exe`),
   including paths that CONTAIN SPACES (argv-list safe);
4. Windows registry (best-effort `reg query`, skipped silently when registry
   tooling is unavailable).

Every candidate carries provenance (how it was found + the raw `--version`
first line) so downstream version validation and evidence can be audited.
Detection itself is read-only.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

BLENDER_FOUNDATION_DIRS = (
    "C:/Program Files/Blender Foundation",
    "D:/Program Files/Blender Foundation",
    "C:/Program Files (x86)/Blender Foundation",
)

VERSION_READ_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class BlenderInstallationCandidate:
    """One discovered blender executable with provenance."""

    executable_path: str
    version_line: str = ""  # first line of `blender --version`
    source: str = ""  # "configured" | "path" | "standard_location" | "registry"
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "executable_path": self.executable_path,
            "version_line": self.version_line,
            "source": self.source,
            "provenance": self.provenance,
        }


def _read_version_line(executable: str, timeout_seconds: float = VERSION_READ_TIMEOUT_SECONDS) -> str:
    """Read the first line of `blender --version` (read-only, bounded)."""
    try:
        proc = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    first_line = (proc.stdout or b"").splitlines()[:1]
    if not first_line:
        return ""
    return first_line[0].decode("utf-8", "replace").strip()


class BlenderInstallationDetector:
    """Finds blender.exe candidates with provenance, configured path first."""

    def __init__(
        self,
        *,
        configured_path: Optional[str] = None,
        version_reader=None,
        standard_locations: tuple = BLENDER_FOUNDATION_DIRS,
        extra_paths: Optional[List[str]] = None,
        use_registry: bool = True,
    ) -> None:
        self._configured_path = configured_path
        self._version_reader = version_reader or _read_version_line
        self._standard_locations = tuple(standard_locations)
        self._extra_paths = tuple(extra_paths or ())
        self._use_registry = use_registry

    # ------------------------------------------------------------------
    def detect(self) -> List[BlenderInstallationCandidate]:
        candidates: List[BlenderInstallationCandidate] = []
        seen: set = set()

        def add(path: str, source: str, note: str) -> None:
            if not path:
                return
            norm = str(Path(path))
            if norm in seen:
                return
            if not Path(norm).is_file():
                return
            seen.add(norm)
            version_line = self._version_reader(norm)
            candidates.append(
                BlenderInstallationCandidate(
                    executable_path=norm,
                    version_line=version_line,
                    source=source,
                    provenance={"note": note, "found_by": source},
                )
            )

        # 1. Configured path (highest priority).
        if self._configured_path:
            add(self._configured_path, "configured", "explicit configuration path")

        # 2. PATH.
        on_path = shutil.which("blender")
        if on_path:
            add(on_path, "path", "resolved via PATH")

        # 3. Extra explicit paths.
        for extra in self._extra_paths:
            add(extra, "configured", "additional configured path")

        # 4. Windows standard locations (handles spaces, e.g. "Blender 4.5").
        if sys.platform.startswith("win"):
            for foundation in self._standard_locations:
                base = Path(foundation)
                if not base.is_dir():
                    continue
                for child in sorted(base.iterdir()):
                    exe = child / "blender.exe"
                    if exe.is_file():
                        add(str(exe), "standard_location", f"scanned {foundation}")

        # 5. Windows registry (best effort).
        if self._use_registry and sys.platform.startswith("win"):
            registry_paths = self._registry_paths()
            for reg_path in registry_paths:
                add(reg_path, "registry", "queried HKLM Software Blender Foundation")

        return candidates

    # ------------------------------------------------------------------
    @staticmethod
    def _registry_paths() -> List[str]:
        """Best-effort registry query; returns [] on any failure."""
        if sys.platform != "win32":
            return []
        try:
            proc = subprocess.run(
                ["reg", "query", r"HKLM\SOFTWARE\Blender Foundation", "/s"],
                capture_output=True,
                timeout=5.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        if proc.returncode != 0:
            return []
        out = (proc.stdout or b"").decode("utf-8", "replace")
        paths: List[str] = []
        for line in out.splitlines():
            line = line.strip()
            if line.lower().endswith("blender.exe") and ":" in line:
                # lines look like '    blender.exe    REG_SZ    C:\...\blender.exe'
                parts = line.split()
                for part in parts:
                    if part.lower().endswith("blender.exe") and part != "blender.exe":
                        paths.append(part)
        return paths


__all__ = [
    "BLENDER_FOUNDATION_DIRS",
    "VERSION_READ_TIMEOUT_SECONDS",
    "BlenderInstallationCandidate",
    "BlenderInstallationDetector",
]
