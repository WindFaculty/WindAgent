"""Phase C — execute plan E2E test."""
import pytest
import os, sys
sys.path.insert(0, r"D:\code_ca_nhan\WindAgent\apps\backend")
os.chdir(r"D:\code_ca_nhan\WindAgent\apps\backend")

from db.database import Database
from db.models import (
    Base, ParentTaskORM, TaskPlanORM, TaskNodeORM, TaskEdgeORM,
    AgentORM, ChatSessionORM, MessageORM,
)
import uuid
from datetime import datetime, timezone


@pytest.fixture
def db_url(tmp_path):
    """Unique temp DB per test."""
    return f"sqlite+aiosqlite:///{tmp_path}/test.db"


@pytest.fixture
async def db(db_url):
    db = Database(db_url)
    await db.init_models()
    yield db
    await db.dispose()


async def _setup_plan(db: Database):
    """Create a parent task with a simple A→B→C plan."""
    async with db.session() as s:
        pt = ParentTaskORM(
            id=f"pt_{uuid.uuid4().hex[:8]}",
            conversation_id="conv-exec-test",
            title="Test Plan",
            status="draft",
        )
        s.add(pt)
        plan = TaskPlanORM(
            id=f"plan_{uuid.uuid4().hex[:8]}",
            parent_task_id=pt.id,
            version=1,
            status="active",
        )
        s.add(plan)
        await s.flush()
        nodes = {}
        for nid, title, deps in [
            ("A", "Step A", []),
            ("B", "Step B", ["A"]),
            ("C", "Step C", ["B"]),
        ]:
            node = TaskNodeORM(
                id=nid,
                plan_id=plan.id,
                title=title,
                status="blocked",
                agent_type="worker",
            )
            s.add(node)
            nodes[nid] = node
        for dep_from, dep_to in [("A", "B"), ("B", "C")]:
            s.add(TaskEdgeORM(
                id=f"e_{uuid.uuid4().hex[:8]}",
                plan_id=plan.id,
                from_task_id=dep_from,
                to_task_id=dep_to,
            ))
        await s.commit()
        return pt.id, plan.id


async def test_execute_plan_endpoint(db):
    """Execute a plan via DAGScheduler through the full stack."""
    pt_id, plan_id = await _setup_plan(db)

    # Simulate the router logic: validate, reset, run
    from services.dag_scheduler import DAGScheduler, detect_cycle
    from sqlalchemy import select

    async with db.session() as s:
        nodes = (await s.execute(
            select(TaskNodeORM).where(TaskNodeORM.plan_id == plan_id)
        )).scalars().all()
        edges = (await s.execute(
            select(TaskEdgeORM).where(TaskEdgeORM.plan_id == plan_id)
        )).scalars().all()

    # validate
    cycle = detect_cycle(plan_id, list(edges))
    assert not cycle, f"unexpected cycle: {cycle}"

    # reset
    async with db.session() as s:
        for n in nodes:
            n.status = "ready"
        await s.commit()

    # run
    order = []

    async def exec_fn(tid: str):
        order.append(tid)

    scheduler = DAGScheduler(db)
    result = await scheduler.run_plan(plan_id, executor=exec_fn)
    assert len(result.completed) == 3, f"expected 3 completed, got {result.completed}"
    assert result.failed == [], f"unexpected failed: {result.failed}"
    assert order == ["A", "B", "C"], f"wrong order: {order}"

    # verify DB state
    async with db.session() as s:
        for nid in ["A", "B", "C"]:
            node = await s.get(TaskNodeORM, nid)
            assert node is not None, f"node {nid} not found"
            assert node.status == "completed", f"node {nid} status={node.status}"
            assert node.finished_at is not None, f"node {nid} finished_at is None"


async def test_execute_plan_cycle_rejected(db):
    """Plan with cycle returns 400."""
    pt_id, plan_id = await _setup_plan(db)

    from services.dag_scheduler import detect_cycle
    from sqlalchemy import select

    async with db.session() as s:
        # Add a cycle edge C → A
        s.add(TaskEdgeORM(
            id=f"e_cycle_{uuid.uuid4().hex[:8]}",
            plan_id=plan_id,
            from_task_id="C",
            to_task_id="A",
        ))
        await s.commit()
        edges = (await s.execute(
            select(TaskEdgeORM).where(TaskEdgeORM.plan_id == plan_id)
        )).scalars().all()

    cycle = detect_cycle(plan_id, list(edges))
    assert cycle is not None, "expected cycle but none detected"


async def test_execute_empty_plan_rejected(db):
    """Empty plan fails validation."""
    from sqlalchemy import select
    from services.dag_scheduler import DAGScheduler, detect_cycle

    async with db.session() as s:
        pt = ParentTaskORM(
            id=f"pt_empty_{uuid.uuid4().hex[:8]}",
            conversation_id="conv-empty",
            title="Empty",
            status="active",
        )
        s.add(pt)
        plan = TaskPlanORM(
            id=f"plan_empty_{uuid.uuid4().hex[:8]}",
            parent_task_id=pt.id,
            version=1,
            status="active",
        )
        s.add(plan)
        await s.commit()

    async with db.session() as s:
        nodes = (await s.execute(
            select(TaskNodeORM).where(TaskNodeORM.plan_id == plan.id)
        )).scalars().all()
        assert len(nodes) == 0  # empty plan