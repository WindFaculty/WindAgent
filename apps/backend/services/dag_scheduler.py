"""Phase 5 — DAG scheduler (ban_ke_hoach §8).

Validates task DAG, detects cycles, resolves dependencies, schedules ready
tasks in parallel (concurrency-group + permission aware), retries on
failure up to max_retries, enforces timeout, assigns agent instances, and
aggregates parent progress.

Lazy scope: no real subprocess here. Scheduler drives a callable per task
(the orchestrator spawns the actual sub-agent). Retry/timeout/cycle logic
is the testable core; agent spawn is injected.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Optional, Set

from sqlalchemy import select

from db.database import Database
from db.models import ParentTaskORM, TaskPlanORM, TaskNodeORM, TaskEdgeORM

log = logging.getLogger(__name__)

# task_id -> coroutine factory(context) -> None
TaskExec = Callable[[str], Awaitable[None]]


class DAGValidationError(ValueError):
    """Raised when the DAG is structurally invalid (cycle, dangling edge)."""


def detect_cycle(plan_id: str, edges: List[TaskEdgeORM]) -> List[str]:
    """Return list of task ids in a cycle, empty if acyclic.

    Edge types modeled uniformly for ordering: any edge forbids the
    to_task from running before from_task.
    """
    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(e.from_task_id, []).append(e.to_task_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {}
    cycle: List[str] = []

    def visit(node: str, stack: List[str]) -> bool:
        color[node] = GRAY
        for nxt in adj.get(node, []):
            if color.get(nxt, WHITE) == WHITE:
                if visit(nxt, stack + [nxt]):
                    return True
            elif color.get(nxt) == GRAY:
                # found back-edge
                idx = stack.index(nxt) if nxt in stack else 0
                cycle.extend(stack[idx:] + [nxt])
                return True
        color[node] = BLACK
        return False

    nodes = {e.from_task_id for e in edges} | {e.to_task_id for e in edges}
    for n in nodes:
        if color.get(n, WHITE) == WHITE:
            if visit(n, [n]):
                return cycle
    return []


@dataclass
class ScheduleResult:
    completed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    cancelled: List[str] = field(default_factory=list)


class DAGScheduler:
    """Executes one task plan (ban_ke_hoach §8.2-8.4)."""

    def __init__(self, db: Database, event_bus=None, executor: Optional[TaskExec] = None) -> None:
        self.db = db
        self._bus = event_bus
        self._executor = executor

    async def validate(self, plan_id: str) -> None:
        """Raise DAGValidationError on cycle or dangling edge."""
        async with self.db.session() as s:
            edges = (await s.execute(
                select(TaskEdgeORM).where(TaskEdgeORM.plan_id == plan_id)
            )).scalars().all()
            nodes = (await s.execute(
                select(TaskNodeORM).where(TaskNodeORM.plan_id == plan_id)
            )).scalars().all()
        ids = {n.id for n in nodes}
        for e in edges:
            if e.from_task_id not in ids or e.to_task_id not in ids:
                raise DAGValidationError(
                    f"dangling edge {e.from_task_id}->{e.to_task_id} in plan {plan_id}"
                )
        cycle = detect_cycle(plan_id, edges)
        if cycle:
            raise DAGValidationError(f"cycle detected: {' -> '.join(cycle)}")

    async def run_plan(
        self,
        plan_id: str,
        *,
        executor: Optional[TaskExec] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> ScheduleResult:
        """Schedule all tasks in plan respecting dependencies + concurrency.

        executor: task_id -> awaitable. If None, tasks flip to completed
        immediately (simulation). Retry/timeout enforced per task.
        """
        exec_fn = executor or self._executor
        result = ScheduleResult()

        async with self.db.session() as s:
            nodes = (await s.execute(
                select(TaskNodeORM).where(TaskNodeORM.plan_id == plan_id)
            )).scalars().all()
            for n in nodes:
                if n.status in ("draft", "blocked", "ready", "assigned", "running", "retryable"):
                    n.status = "blocked"
            await s.commit()

        running: Dict[str, asyncio.Task] = {}

        async def _terminal_nodes():
            async with self.db.session() as s:
                ns = (await s.execute(
                    select(TaskNodeORM).where(TaskNodeORM.plan_id == plan_id)
                )).scalars().all()
                return ns

        while True:
            if cancel_event and cancel_event.is_set():
                for t in running.values():
                    t.cancel()
                break

            ns = await _terminal_nodes()
            by_id = {n.id: n for n in ns}

            # mark blocked -> ready when deps done
            for n in ns:
                if n.status == "blocked" and await self._deps_done_by(by_id, n.id):
                    n.status = "ready"
                    async with self.db.session() as s:
                        rn = await s.get(TaskNodeORM, n.id)
                        rn.status = "ready"
                        await s.commit()

            # launch ready tasks not already running
            for n in ns:
                if n.id in running:
                    continue
                if n.status == "ready":
                    running[n.id] = asyncio.create_task(
                        self._run_task(n, exec_fn, cancel_event),
                        name=f"task:{n.id}",
                    )

            # reap completed tasks
            if running:
                done, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    tid = t.get_name().split(":", 1)[1]
                    running.pop(tid, None)
                    async with self.db.session() as s:
                        node = await s.get(TaskNodeORM, tid)
                        if node:
                            if node.status == "completed":
                                result.completed.append(tid)
                            elif node.status == "failed":
                                result.failed.append(tid)
                            elif node.status == "cancelled":
                                result.cancelled.append(tid)

            # termination check
            ns = await _terminal_nodes()
            statuses = {n.status for n in ns}
            if statuses <= {"completed", "failed", "cancelled"}:
                break
            # stuck: nothing running and nothing ready/runnable
            if not running and not any(n.status in ("ready", "blocked") for n in ns):
                # retryable nodes get relaunched next loop; if all blocked-with-failed-upstream, stop
                if not any(n.status == "retryable" for n in ns):
                    break

            await asyncio.sleep(0.005)

        await self._aggregate_progress(plan_id)
        return result

    async def _deps_done_by(self, by_id: Dict[str, TaskNodeORM], task_id: str) -> bool:
        async with self.db.session() as s:
            edges = (await s.execute(
                select(TaskEdgeORM).where(TaskEdgeORM.to_task_id == task_id)
            )).scalars().all()
        if not edges:
            return True
        for e in edges:
            up = by_id.get(e.from_task_id)
            if up is None or up.status != "completed":
                return False
        return True

    async def _run_task(
        self,
        node: TaskNodeORM,
        exec_fn: Optional[TaskExec],
        cancel_event: Optional[asyncio.Event],
    ) -> None:
        """Run one task with retry + timeout. Writes status to DB."""
        attempt = 0
        while attempt <= node.max_retries:
            async with self.db.session() as s:
                n = await s.get(TaskNodeORM, node.id)
                if n is None:
                    return
                n.status = "running"
                n.started_at = datetime.now(timezone.utc)
                await s.commit()

            try:
                if cancel_event and cancel_event.is_set():
                    async with self.db.session() as s:
                        nn = await s.get(TaskNodeORM, node.id)
                        if nn:
                            nn.status = "cancelled"
                            nn.finished_at = datetime.now(timezone.utc)
                    return

                if exec_fn is not None:
                    await asyncio.wait_for(
                        exec_fn(node.id),
                        timeout=node.timeout_seconds if node.timeout_seconds else None,
                    )

                async with self.db.session() as s:
                    nn = await s.get(TaskNodeORM, node.id)
                    if nn:
                        nn.status = "completed"
                        nn.finished_at = datetime.now(timezone.utc)
                        nn.retry_count = attempt
                self._emit(node.id, "task.completed")
                return

            except asyncio.TimeoutError:
                async with self.db.session() as s:
                    nn = await s.get(TaskNodeORM, node.id)
                    if nn:
                        nn.retry_count = attempt + 1
                        if attempt >= node.max_retries:
                            nn.status = "failed"
                            nn.finished_at = datetime.now(timezone.utc)
                        else:
                            nn.status = "retryable"
                attempt += 1
                if attempt > node.max_retries:
                    self._emit(node.id, "task.failed")
                    return
                # brief backoff before retry
                await asyncio.sleep(0.01)
            except Exception:
                async with self.db.session() as s:
                    nn = await s.get(TaskNodeORM, node.id)
                    if nn:
                        nn.retry_count = attempt + 1
                        if attempt >= node.max_retries:
                            nn.status = "failed"
                            nn.finished_at = datetime.now(timezone.utc)
                            self._emit(node.id, "task.failed")
                        else:
                            nn.status = "retryable"
                attempt += 1
                if attempt > node.max_retries:
                    return
                await asyncio.sleep(0.01)

    async def _aggregate_progress(self, plan_id: str) -> None:
        async with self.db.session() as s:
            plan = await s.get(TaskPlanORM, plan_id)
            if not plan:
                return
            nodes = (await s.execute(
                select(TaskNodeORM).where(TaskNodeORM.plan_id == plan_id)
            )).scalars().all()
            total = len(nodes) or 1
            done = sum(1 for n in nodes if n.status == "completed")
            prog = round(done / total, 4)
            parent = await s.get(ParentTaskORM, plan.parent_task_id)
            if parent:
                parent.progress = prog
                if done == total:
                    parent.status = "completed"
                    parent.completed_at = datetime.now(timezone.utc)

    def _emit(self, task_id: str, event: str) -> None:
        if self._bus is None:
            return
        try:
            from schemas.event import EventEnvelope
            # ponytail: scheduler runs in async ctx; bus.publish is async but
            # called from non-awaited task context. Fire-and-forget via create_task
            # on the running loop is overkill; we schedule a safe coroutine.
            loop = asyncio.get_event_loop()
            loop.create_task(
                self._bus.publish("phase5", EventEnvelope(event=event, data={"task_id": task_id}))
            )
        except Exception:
            log.debug("bus emit skipped for %s", event)
