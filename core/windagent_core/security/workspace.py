"""Workspace root validation (Phase 1 — G9.5).

Every user-supplied ``workspace_root`` must resolve to a directory **inside**
the repository root. Path traversal (``../../etc``) and symlink escapes are
rejected because ``Path.resolve()`` collapses ``..`` segments and follows
symlinks before the containment check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

_REPO_MARKERS = ("pyproject.toml", ".git")


class WorkspaceRootViolation(ValueError):
    """Raised when ``workspace_root`` escapes the repository root."""


def find_repository_root(start: Path) -> Path:
    """Walk up from ``start`` to the repository root.

    A directory containing ``.git`` wins (sub-packages like ``core/`` ship their
    own ``pyproject.toml`` and must not be mistaken for the workspace root).
    Without ``.git``, the topmost ancestor carrying a marker is used.
    """
    current = start.resolve()
    ancestors = [current, *current.parents]
    for candidate in ancestors:
        if (candidate / ".git").exists():
            return candidate
    for candidate in ancestors:
        if any((candidate / marker).exists() for marker in _REPO_MARKERS):
            return candidate
    return current


def validate_workspace_root(
    workspace_root: str,
    repo_root: Optional[Path] = None,
) -> Path:
    """Resolve and validate ``workspace_root`` stays inside ``repo_root``.

    Args:
        workspace_root: User-supplied path (relative or absolute).
        repo_root: Repository root; when omitted, discovered by walking up from
            this module (falls back to CWD).

    Returns:
        The resolved absolute ``Path``.

    Raises:
        WorkspaceRootViolation: when the path is empty, cannot be resolved, or
            escapes the repository root (traversal / symlink escape).
    """
    if not workspace_root or not workspace_root.strip():
        raise WorkspaceRootViolation("workspace_root must not be empty")

    root = (repo_root or find_repository_root(Path(__file__))).resolve()
    try:
        resolved = Path(workspace_root).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise WorkspaceRootViolation(
            f"workspace_root could not be resolved: {workspace_root!r}"
        ) from exc

    if not resolved.is_relative_to(root):
        raise WorkspaceRootViolation(
            f"workspace_root escapes repository root: {workspace_root!r} -> {resolved} "
            f"(repo root: {root})"
        )
    return resolved
