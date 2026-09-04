"""Workspace sandbox isolation and path containment validator."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import WorkspacePathViolationError


class WorkspaceSandbox:
    """Enforces directory containment and prevents path traversal / symlink escapes."""

    def __init__(self, root_path: Path | str) -> None:
        self._root = Path(root_path).expanduser().resolve()

    @property
    def root(self) -> Path:
        return self._root

    def validate_path(self, target_path: Path | str) -> Path:
        """Resolve target_path and assert it is contained inside workspace root.

        Raises:
            WorkspacePathViolationError: If path escapes or is empty.
        """
        if not target_path or not str(target_path).strip():
            raise WorkspacePathViolationError(
                path=str(target_path),
                root=str(self._root),
                reason="Path must not be empty",
            )

        raw = str(target_path).strip()
        # Disallow null bytes
        if "\0" in raw:
            raise WorkspacePathViolationError(
                path=raw,
                root=str(self._root),
                reason="Path contains null bytes",
            )

        try:
            # If relative, anchor to root
            p = Path(raw)
            if not p.is_absolute():
                resolved = (self._root / p).resolve()
            else:
                resolved = p.resolve()
        except (OSError, RuntimeError) as exc:
            raise WorkspacePathViolationError(
                path=raw,
                root=str(self._root),
                reason=f"Path resolution failure: {exc}",
            ) from exc

        # Check containment
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise WorkspacePathViolationError(
                path=raw,
                root=str(self._root),
                reason="Path escapes workspace root directory boundary",
            ) from exc

        return resolved

    def relative_to_root(self, target_path: Path | str) -> str:
        """Return canonical POSIX relative path string."""
        resolved = self.validate_path(target_path)
        return resolved.relative_to(self._root).as_posix()

    def ensure_directory(self, subdir: str | None = None) -> Path:
        """Ensure root or safe subdirectory exists."""
        target = self.validate_path(subdir) if subdir else self._root
        os.makedirs(target, exist_ok=True)
        return target
