"""
Bounded Concurrency & Priority Task Scheduler for WindAgent Architecture V2.
Manages run slots, priority ordering, and per-project/worktree concurrency locks.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Set


logger = logging.getLogger("windagent.orchestration.scheduler")


class TaskPriority(IntEnum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass(order=True)
class ScheduledTaskItem:
    priority: TaskPriority
    task_id: str = field(compare=False)
    project_id: Optional[str] = field(default=None, compare=False)


class TaskScheduler:
    def __init__(self, max_concurrency: int = 5):
        self.max_concurrency = max_concurrency
        self._active_runs: Set[str] = set()
        self._project_locks: Set[str] = set()
        self._queue: List[ScheduledTaskItem] = []

    @property
    def active_count(self) -> int:
        return len(self._active_runs)

    def enqueue(self, task_id: str, priority: TaskPriority = TaskPriority.MEDIUM, project_id: Optional[str] = None) -> None:
        item = ScheduledTaskItem(priority=priority, task_id=task_id, project_id=project_id)
        self._queue.append(item)
        self._queue.sort()  # Sort by priority
        logger.info(f"Enqueued task [{task_id}] with priority [{priority.name}]")

    def acquire_slot(self, task_id: str, project_id: Optional[str] = None) -> bool:
        """Attempts to acquire an execution slot under concurrency and project lock boundaries."""
        if len(self._active_runs) >= self.max_concurrency:
            logger.info(f"Scheduler capacity full ({len(self._active_runs)}/{self.max_concurrency}). Cannot acquire slot for [{task_id}].")
            return False

        if project_id and project_id in self._project_locks:
            logger.info(f"Project [{project_id}] is currently locked by another active run. Cannot acquire slot for [{task_id}].")
            return False

        self._active_runs.add(task_id)
        if project_id:
            self._project_locks.add(project_id)

        # Remove from queue if present
        self._queue = [item for item in self._queue if item.task_id != task_id]
        logger.info(f"Acquired execution slot for task [{task_id}] ({len(self._active_runs)}/{self.max_concurrency} active)")
        return True

    def release_slot(self, task_id: str, project_id: Optional[str] = None) -> None:
        if task_id in self._active_runs:
            self._active_runs.remove(task_id)
        if project_id and project_id in self._project_locks:
            self._project_locks.remove(project_id)
        logger.info(f"Released execution slot for task [{task_id}]")
