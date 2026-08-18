"""
Isolated Tutorial Workspace and Sandbox Management.

Ensures tutorial code (agentic-studio) is built and executed strictly inside
an isolated workspace directory (e.g. .tmp/code_video/video_02/agentic-studio),
reusing canonical PathSandbox and SafeShellRunner tooling.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Dict, List, Optional, Tuple, Union

from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError
from windagent_tools.filesystem.sandbox import PathSandbox
from windagent_tools.shell.runner import SafeShellRunner


class TutorialWorkspace:
    """
    Manages an isolated tutorial workspace with sandbox boundaries,
    safe shell command execution, and file operations.
    """

    def __init__(
        self,
        workspace_root: Union[str, Path],
        host_repo_root: Optional[Union[str, Path]] = None,
        default_timeout_seconds: float = 30.0,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.host_repo_root = Path(host_repo_root).resolve() if host_repo_root else Path.cwd().resolve()
        self.default_timeout_seconds = default_timeout_seconds

        # Enforce that tutorial workspace is NEVER inside host source packages
        self._validate_isolation_boundary()

        self.sandbox = PathSandbox(self.workspace_root)
        self.shell_runner = SafeShellRunner(str(self.workspace_root), default_timeout_seconds=default_timeout_seconds)

    def _validate_isolation_boundary(self) -> None:
        """Ensure tutorial workspace is isolated from critical host code directories."""
        forbidden_host_subdirs = ["src", "workflows", "tools", "frontend", "core", "tests"]
        for subdir in forbidden_host_subdirs:
            protected_path = (self.host_repo_root / subdir).resolve()
            if protected_path.exists() and protected_path in self.workspace_root.parents:
                raise PermissionDeniedError(
                    message=f"Tutorial workspace '{self.workspace_root}' cannot be placed inside protected host directory '{protected_path}'.",
                    code="WINDAGENT_ERR_SANDBOX_ISOLATION_VIOLATION",
                    details={"workspace_root": str(self.workspace_root), "protected_path": str(protected_path)},
                )

    def create(self) -> Path:
        """Create workspace directory if it doesn't exist."""
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        return self.workspace_root

    def exists(self) -> bool:
        """Check if workspace root exists on filesystem."""
        return self.workspace_root.exists() and self.workspace_root.is_dir()

    def clean(self) -> None:
        """Remove all files and directories inside workspace root."""
        if self.workspace_root.exists():
            for item in self.workspace_root.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

    def resolve_safe_path(self, relative_path: Union[str, Path]) -> Path:
        """Resolve path within workspace, strictly enforcing sandbox boundaries."""
        return self.sandbox.resolve_safe_path(relative_path)

    def write_file(self, relative_path: Union[str, Path], content: str, encoding: str = "utf-8") -> Path:
        """Write content to a file inside the sandboxed workspace."""
        safe_path = self.resolve_safe_path(relative_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding=encoding)
        return safe_path

    def read_file(self, relative_path: Union[str, Path], encoding: str = "utf-8") -> str:
        """Read content of a file from the sandboxed workspace."""
        safe_path = self.resolve_safe_path(relative_path)
        if not safe_path.exists() or not safe_path.is_file():
            raise ValidationError(f"File '{relative_path}' does not exist in workspace '{self.workspace_root}'.")
        self.sandbox.check_file_size(safe_path)
        return safe_path.read_text(encoding=encoding)

    def file_exists(self, relative_path: Union[str, Path]) -> bool:
        """Check if relative file path exists inside workspace."""
        try:
            safe_path = self.resolve_safe_path(relative_path)
            return safe_path.exists()
        except PermissionDeniedError:
            return False

    def list_files(self, exclude_git: bool = True) -> List[str]:
        """List all relative file paths within the workspace."""
        if not self.workspace_root.exists():
            return []
        files: List[str] = []
        for root, dirs, filenames in os.walk(self.workspace_root):
            if exclude_git and ".git" in dirs:
                dirs.remove(".git")
            if ".checkpoints" in dirs:
                dirs.remove(".checkpoints")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            if ".pytest_cache" in dirs:
                dirs.remove(".pytest_cache")

            rel_dir = Path(root).relative_to(self.workspace_root)
            for f in filenames:
                rel_file = (rel_dir / f).as_posix()
                if rel_file.startswith("./"):
                    rel_file = rel_file[2:]
                files.append(rel_file)
        return sorted(files)

    async def run_command(
        self,
        command_line: str,
        timeout_seconds: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str]:
        """Execute a shell command inside the workspace using SafeShellRunner."""
        return await self.shell_runner.execute_command(
            command_line=command_line,
            cwd=str(self.workspace_root),
            timeout_seconds=timeout_seconds or self.default_timeout_seconds,
            env=env,
        )


__all__ = ["TutorialWorkspace"]
