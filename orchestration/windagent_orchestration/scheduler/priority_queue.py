"""
Min-Heap Priority Queue for Orchestration V2 Task Scheduler.
Uses standard library heapq for O(log N) enqueue/pop operations and sequence counter for stability.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional


class TaskPriority(IntEnum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass(order=True)
class ScheduledTaskItem:
    priority: TaskPriority
    sequence: int  # Insertion sequence for FIFO stability within same priority
    task_id: str = field(compare=False)
    project_id: Optional[str] = field(default=None, compare=False)
    worktree_id: Optional[str] = field(default=None, compare=False)


class TaskPriorityHeap:
    def __init__(self):
        self._heap: List[ScheduledTaskItem] = []
        self._counter: int = 0

    def enqueue(
        self,
        task_id: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        project_id: Optional[str] = None,
        worktree_id: Optional[str] = None,
    ) -> ScheduledTaskItem:
        self._counter += 1
        item = ScheduledTaskItem(
            priority=priority,
            sequence=self._counter,
            task_id=task_id,
            project_id=project_id,
            worktree_id=worktree_id,
        )
        heapq.heappush(self._heap, item)
        return item

    def pop(self) -> Optional[ScheduledTaskItem]:
        if not self._heap:
            return None
        return heapq.heappop(self._heap)

    def peek(self) -> Optional[ScheduledTaskItem]:
        if not self._heap:
            return None
        return self._heap[0]

    def remove(self, task_id: str) -> bool:
        initial_len = len(self._heap)
        self._heap = [item for item in self._heap if item.task_id != task_id]
        if len(self._heap) != initial_len:
            heapq.heapify(self._heap)
            return True
        return False

    def __len__(self) -> int:
        return len(self._heap)
