"""Path sandbox helper — pure domain logic for filesystem tool safety.

Extracted from frozen ``windagent_tools.filesystem.sandbox.PathSandbox`` and
``windagent_tools.security.permission_engine.normalize_and_validate_path``.
The frozen behavior is: resolve both ``target`` and ``workspace_root`` and
require ``target`` to be inside ``workspace_root`` via ``relative_to``.
Symlinks are followed because ``resolve()`` is used — this matches the old
semantics and keeps the security property (escape via ``..`` is denied).
"""

from __future__ import annotations

from pathlib import Path


def is_within_workspace(target_path: str, workspace_root: str) -> bool:
    """Return ``True`` iff ``target_path`` resolves inside ``workspace_root``."""
    if not target_path or not workspace_root:
        return False
    try:
        norm_root = Path(workspace_root).resolve()
        norm_target = Path(target_path).resolve()
        # Also handle case where target_path is relative: resolve against root first
        if not Path(target_path).is_absolute():
            norm_target = (norm_root / target_path).resolve()
        norm_target.relative_to(norm_root)
        return True
    except (ValueError, RuntimeError, TypeError):
        return False


def resolve_safe_path(target_path: str, workspace_root: str) -> Path:
    """Resolve ``target_path`` against ``workspace_root`` and assert containment.

    Raises ``ValueError`` when the path escapes the sandbox.
    """
    if not target_path.strip():
        raise ValueError("file_path cannot be empty")
    if not workspace_root.strip():
        raise ValueError("workspace_root cannot be empty")
    norm_root = Path(workspace_root).resolve()
    # Join relative paths onto root before resolve to avoid cwd leakage
    candidate = Path(target_path)
    if not candidate.is_absolute():
        candidate = norm_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(norm_root)
    except ValueError as exc:
        raise ValueError(
            f"path [{target_path}] escapes workspace root [{workspace_root}]"
        ) from exc
    return resolved


__all__ = ["is_within_workspace", "resolve_safe_path"]
