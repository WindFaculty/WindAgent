"""
Worktree Isolation and Workspace Context Management for WindAgent V2 (Phase 18).
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional


class WorktreeContextManager:
    """Provides isolated workspace directory paths and file system boundaries for step execution."""

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd()

    def get_isolated_path(self, relative_path: str) -> Path:
        target = (self.root_dir / relative_path).resolve()
        if not str(target).startswith(str(self.root_dir)):
            raise ValueError(f"Path traversal detected outside workspace root: {relative_path}")
        return target

    def ensure_worktree_dir(self, worktree_id: str) -> Path:
        wt_dir = self.root_dir / ".worktrees" / worktree_id
        wt_dir.mkdir(parents=True, exist_ok=True)
        return wt_dir
