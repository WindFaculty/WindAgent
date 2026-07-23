"""
High-Performance Bounded Concurrency & Priority Task Scheduler for WindAgent Architecture V2.
Coordinates TaskPriorityHeap, ProjectLockManager, and EventDrivenWakeup.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Set

from windagent_orchestration.scheduler.priority_queue import TaskPriorityHeap, TaskPriority, ScheduledTaskItem
from windagent_orchestration.scheduler.project_locks import ProjectLockManager
from windagent_orchestration.scheduler.wakeup import EventDrivenWakeup
from windagent_orchestration.metrics import metrics

logger = logging.getLogger("windagent.orchestration.scheduler")


class TaskScheduler:
    def __init__(self, max_concurrency: int = 5):
        self.max_concurrency = max_concurrency
        self.heap = TaskPriorityHeap()
        self.lock_manager = ProjectLockManager()
        self.wakeup = EventDrivenWakeup()
        self._active_runs: Set[str] = set()

    @property
    def _queue(self) -> List[ScheduledTaskItem]:
        """Adapter property for legacy test compatibility."""
        return sorted(self.heap._heap)

    @property
    def active_count(self) -> int:
        return len(self._active_runs)

    def enqueue(
        self,
        task_id: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        project_id: Optional[str] = None,
        worktree_id: Optional[str] = None,
    ) -> None:
        t0 = time.perf_counter()
        self.heap.enqueue(task_id, priority=priority, project_id=project_id, worktree_id=worktree_id)
        self.wakeup.notify()
        duration_ms = (time.perf_counter() - t0) * 1000.0
        metrics.record_enqueue(duration_ms)
        logger.info(f"Enqueued task [{task_id}] with priority [{priority.name}] in {duration_ms:.2f} ms")

    def acquire_slot(
        self,
        task_id: str,
        project_id: Optional[str] = None,
        worktree_id: Optional[str] = None,
    ) -> bool:
        t0 = time.perf_counter()

        if len(self._active_runs) >= self.max_concurrency:
            logger.info(f"Capacity full ({len(self._active_runs)}/{self.max_concurrency}). Cannot acquire slot for [{task_id}].")
            duration_ms = (time.perf_counter() - t0) * 1000.0
            metrics.record_scheduling(duration_ms)
            return False

        if not self.lock_manager.acquire(project_id, worktree_id):
            logger.info(f"Project/worktree locked for [{task_id}]. Slot acquisition denied.")
            duration_ms = (time.perf_counter() - t0) * 1000.0
            metrics.record_scheduling(duration_ms)
            return False

        self._active_runs.add(task_id)
        self.heap.remove(task_id)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        metrics.record_scheduling(duration_ms)
        logger.info(f"Acquired execution slot for [{task_id}] ({len(self._active_runs)}/{self.max_concurrency} active) in {duration_ms:.2f} ms")
        return True

    def release_slot(
        self,
        task_id: str,
        project_id: Optional[str] = None,
        worktree_id: Optional[str] = None,
    ) -> None:
        if task_id in self._active_runs:
            self._active_runs.remove(task_id)
        self.lock_manager.release(project_id, worktree_id)
        self.wakeup.notify()
        logger.info(f"Released execution slot for task [{task_id}]")
