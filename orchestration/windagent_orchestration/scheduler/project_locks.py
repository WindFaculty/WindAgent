"""
Per-Project and Per-Worktree Concurrency Lock Manager for Orchestration V2 Scheduler.
Prevents concurrent execution collisions within the same workspace/project root.
"""

from __future__ import annotations

import logging
from typing import Set, Optional

logger = logging.getLogger("windagent.orchestration.scheduler.project_locks")


class ProjectLockManager:
    def __init__(self):
        self._project_locks: Set[str] = set()
        self._worktree_locks: Set[str] = set()

    def is_locked(self, project_id: Optional[str] = None, worktree_id: Optional[str] = None) -> bool:
        if project_id and project_id in self._project_locks:
            return True
        if worktree_id and worktree_id in self._worktree_locks:
            return True
        return False

    def acquire(self, project_id: Optional[str] = None, worktree_id: Optional[str] = None) -> bool:
        if self.is_locked(project_id, worktree_id):
            return False

        if project_id:
            self._project_locks.add(project_id)
        if worktree_id:
            self._worktree_locks.add(worktree_id)

        logger.info(f"Acquired locks for project [{project_id}], worktree [{worktree_id}]")
        return True

    def release(self, project_id: Optional[str] = None, worktree_id: Optional[str] = None) -> None:
        if project_id:
            self._project_locks.discard(project_id)
        if worktree_id:
            self._worktree_locks.discard(worktree_id)

        logger.info(f"Released locks for project [{project_id}], worktree [{worktree_id}]")
