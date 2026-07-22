"""
Filesystem Path Sandbox for WindAgent Tool Platform.
Protects against path traversal attacks, symlink escapes outside workspace root, and excessive file sizes.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Union

from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError


class PathSandbox:
    def __init__(self, workspace_root: Union[str, Path], max_file_size_bytes: int = 10 * 1024 * 1024):
        self.workspace_root = Path(workspace_root).resolve()
        self.max_file_size_bytes = max_file_size_bytes

    def resolve_safe_path(self, relative_or_absolute_path: Union[str, Path]) -> Path:
        """Resolves target path and verifies it remains strictly inside workspace_root."""
        raw_path = Path(relative_or_absolute_path)

        # 1. Reject path traversal markers before resolution if malicious
        path_str = str(relative_or_absolute_path).replace("\\", "/")
        if "/../" in path_str or path_str.startswith("../") or path_str == "..":
            # Attempting escape via relative traversal
            pass

        # If path is relative, join with workspace root
        if not raw_path.is_absolute():
            candidate = (self.workspace_root / raw_path).resolve()
        else:
            candidate = raw_path.resolve()

        # Check symlink escape
        try:
            real_path = candidate.resolve(strict=False)
        except Exception as e:
            raise ValidationError(f"Invalid filesystem path: {e}")

        # Enforce boundary: real_path must start with workspace_root
        try:
            real_path.relative_to(self.workspace_root)
        except ValueError:
            raise PermissionDeniedError(
                message=f"Path traversal denied: Access to '{relative_or_absolute_path}' outside workspace root '{self.workspace_root}' is forbidden.",
                code="WINDAGENT_ERR_PATH_TRAVERSAL_DENIED",
                details={"requested_path": str(relative_or_absolute_path), "workspace_root": str(self.workspace_root)},
            )

        return real_path

    def check_file_size(self, file_path: Path) -> None:
        if file_path.exists() and file_path.is_file():
            size = file_path.stat().st_size
            if size > self.max_file_size_bytes:
                raise ValidationError(
                    f"File size {size} bytes exceeds maximum allowed limit of {self.max_file_size_bytes} bytes."
                )
