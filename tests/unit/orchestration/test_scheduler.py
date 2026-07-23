"""
Unit Tests for TaskScheduler Priority Heap, Project Lock, Event-Driven Wakeup, and Performance Gates (Phase E).
"""

import pytest
import asyncio
import time
from windagent_orchestration.scheduler import TaskScheduler, TaskPriority, EventDrivenWakeup


def test_scheduler_heap_order():
    scheduler = TaskScheduler(max_concurrency=2)
    scheduler.enqueue("task_low", priority=TaskPriority.LOW)
    scheduler.enqueue("task_high", priority=TaskPriority.HIGH)
    scheduler.enqueue("task_med", priority=TaskPriority.MEDIUM)

    peeked = scheduler.heap.peek()
    assert peeked is not None
    assert peeked.task_id == "task_high"

    popped = scheduler.heap.pop()
    assert popped is not None
    assert popped.task_id == "task_high"

    popped2 = scheduler.heap.pop()
    assert popped2 is not None
    assert popped2.task_id == "task_med"


def test_scheduler_project_lock():
    scheduler = TaskScheduler(max_concurrency=5)

    assert scheduler.acquire_slot("t1", project_id="proj_alpha")
    assert not scheduler.acquire_slot("t2", project_id="proj_alpha")

    scheduler.release_slot("t1", project_id="proj_alpha")
    assert scheduler.acquire_slot("t2", project_id="proj_alpha")


@pytest.mark.asyncio
async def test_event_driven_wakeup():
    wakeup = EventDrivenWakeup()

    async def trigger():
        await asyncio.sleep(0.01)
        wakeup.notify()

    asyncio.create_task(trigger())
    t0 = time.perf_counter()
    woken = await wakeup.wait(timeout=1.0)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert woken is True
    assert duration_ms < 50.0
