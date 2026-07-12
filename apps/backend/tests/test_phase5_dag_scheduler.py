"""Phase 5 gate (ban_ke_hoach §8): DAG validation, cycle, fan-out/fan-in, retry.

Verifies:
  - detect_cycle finds back-edge
  - validate raises on cycle + dangling edge
  - run_plan fan-out (A -> B,C) then fan-in (B,C -> D) completes D last
  - max_retries retries failed task then marks failed
  - parent progress aggregates to 1.0 on full completion
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from db.database import Database
from db.models import (
    ParentTaskORM, TaskPlanORM, TaskNodeORM, TaskEdgeORM,
)
from services.dag_scheduler import DAGScheduler, detect_cycle, DAGValidationError


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite+aiosqlite:///{tmp_path/'phase5.db'}?timeout=30"


async def _build(db, *, with_cycle=False, with_dangling=False):
    async with db.session() as s:
        parent = ParentTaskORM(id="pt1", conversation_id="c1", title="P", status="draft")
        s.add(parent)
        plan = TaskPlanORM(id="plan1", parent_task_id="pt1", version=1, status="active")
        s.add(plan)
        nodes = {}
        for nid, title in [("A","a"),("B","b"),("C","c"),("D","d")]:
            n = TaskNodeORM(id=nid, plan_id="plan1", title=title, status="blocked",
                            max_retries=0, retry_count=0)
            s.add(n); nodes[nid] = n
        s.add(TaskEdgeORM(id="e1", plan_id="plan1", from_task_id="A", to_task_id="B"))
        s.add(TaskEdgeORM(id="e2", plan_id="plan1", from_task_id="A", to_task_id="C"))
        s.add(TaskEdgeORM(id="e3", plan_id="plan1", from_task_id="B", to_task_id="D"))
        s.add(TaskEdgeORM(id="e4", plan_id="plan1", from_task_id="C", to_task_id="D"))
        if with_cycle:
            s.add(TaskEdgeORM(id="e5", plan_id="plan1", from_task_id="D", to_task_id="A"))
        if with_dangling:
            s.add(TaskEdgeORM(id="e6", plan_id="plan1", from_task_id="Z", to_task_id="A"))
        await s.commit()
    return nodes


async def test_cycle_detect(db_url):
    db = Database(db_url)
    await db.init_models()
    await _build(db, with_cycle=True)
    async with db.session() as s:
        edges = (await s.execute(select(TaskEdgeORM).where(TaskEdgeORM.plan_id=="plan1"))).scalars().all()
    cyc = detect_cycle("plan1", edges)
    assert cyc  # non-empty
    sch = DAGScheduler(db)
    with pytest.raises(DAGValidationError):
        await sch.validate("plan1")
    await db.dispose()


async def test_dangling_edge(db_url):
    db = Database(db_url)
    await db.init_models()
    await _build(db, with_dangling=True)
    sch = DAGScheduler(db)
    with pytest.raises(DAGValidationError):
        await sch.validate("plan1")
    await db.dispose()


async def test_fanout_fanin(db_url):
    db = Database(db_url)
    await db.init_models()
    await _build(db)
    order = []
    async def exec(tid):
        order.append(tid)
    sch = DAGScheduler(db, executor=exec)
    res = await sch.run_plan("plan1", executor=exec)
    # D must come after B and C, A before B/C.
    assert res.completed == ["A","B","C","D"] or set(res.completed)=={"A","B","C","D"}
    assert order.index("A") < order.index("B")
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")
    # parent progress complete
    async with db.session() as s:
        p = await s.get(ParentTaskORM, "pt1")
        assert p.progress == 1.0
        assert p.status == "completed"
    await db.dispose()


async def test_retry_then_fail(db_url):
    db = Database(db_url)
    await db.init_models()
    async with db.session() as s:
        parent = ParentTaskORM(id="pt2", conversation_id="c2", title="P", status="draft")
        s.add(parent)
        plan = TaskPlanORM(id="plan2", parent_task_id="pt2", version=1, status="active")
        s.add(plan)
        # single task, 2 retries, always fails
        s.add(TaskNodeORM(id="X", plan_id="plan2", title="x", status="blocked",
                          max_retries=2, retry_count=0))
        await s.commit()
    calls = {"n": 0}
    async def exec(tid):
        calls["n"] += 1
        raise RuntimeError("boom")
    sch = DAGScheduler(db, executor=exec)
    res = await sch.run_plan("plan2", executor=exec)
    assert res.failed == ["X"]
    assert calls["n"] == 3  # initial + 2 retries
    async with db.session() as s:
        n = await s.get(TaskNodeORM, "X")
        assert n.status == "failed"
        assert n.retry_count == 3
    await db.dispose()
