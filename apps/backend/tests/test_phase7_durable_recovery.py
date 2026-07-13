"""Phase 7 gate (ban_ke_hoach §11-12 / Giai đoạn 7):

  - EventBus stamps a monotonic per-session seq.
  - Persist-before-broadcast: subscriber never sees an event the DB hook
    hasn't written.
  - Seq resumes from DB after a "restart" (fresh bus, same DB).
  - replay_after returns exactly the events past a given seq.
  - recover(): a running AgentRun whose Hermes run is gone -> interrupted,
    its task -> retryable (never silently completed).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from db.database import Database
from db.models import (
    AgentInstanceORM, AgentRunORM, ExecutionEventORM,
    ParentTaskORM, TaskPlanORM, TaskNodeORM,
)
from schemas.event import EventEnvelope
from services.event_bus import EventBus
from services.event_hooks import make_execution_event_hook
from services.recovery_service import RecoveryManager


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite+aiosqlite:///{tmp_path/'phase7.db'}?timeout=30"


def _env(name="terminal_output"):
    return EventEnvelope(event=name, data={"x": 1})


async def _bus_with_db(db):
    bus = EventBus()
    bus.add_publisher_hook(make_execution_event_hook(db))
    rec = RecoveryManager(db)
    bus.set_seq_seed(rec.seed_seq)
    return bus, rec


async def test_seq_monotonic_and_persisted(db_url):
    db = Database(db_url)
    await db.init_models()
    bus, rec = await _bus_with_db(db)
    for _ in range(3):
        await bus.publish("s1", _env())
    async with db.session() as s:
        rows = (await s.execute(
            select(ExecutionEventORM).where(ExecutionEventORM.session_id == "s1")
            .order_by(ExecutionEventORM.event_seq)
        )).scalars().all()
    assert [r.event_seq for r in rows] == [1, 2, 3]
    await db.dispose()


async def test_persist_before_broadcast(db_url):
    """When a subscriber receives an event, it is already in the DB."""
    db = Database(db_url)
    await db.init_models()
    bus, rec = await _bus_with_db(db)
    q = await bus.subscribe("s1")
    await bus.publish("s1", _env())
    env = q.get_nowait()
    # The event the subscriber holds must already be persisted.
    async with db.session() as s:
        row = (await s.execute(
            select(ExecutionEventORM).where(
                ExecutionEventORM.session_id == "s1",
                ExecutionEventORM.event_seq == env.seq,
            )
        )).scalar_one_or_none()
    assert row is not None
    await db.dispose()


async def test_seq_resumes_after_restart(db_url):
    db = Database(db_url)
    await db.init_models()
    bus1, _ = await _bus_with_db(db)
    await bus1.publish("s1", _env())
    await bus1.publish("s1", _env())
    # Simulate restart: brand-new bus, same DB.
    bus2, _ = await _bus_with_db(db)
    await bus2.publish("s1", _env())
    async with db.session() as s:
        seqs = (await s.execute(
            select(ExecutionEventORM.event_seq)
            .where(ExecutionEventORM.session_id == "s1")
            .order_by(ExecutionEventORM.event_seq)
        )).scalars().all()
    assert seqs == [1, 2, 3]  # no reset to 1
    await db.dispose()


async def test_replay_after(db_url):
    db = Database(db_url)
    await db.init_models()
    bus, rec = await _bus_with_db(db)
    for _ in range(5):
        await bus.publish("s1", _env())
    missed = await rec.replay_after("s1", after_seq=2)
    assert [e.seq for e in missed] == [3, 4, 5]
    assert await rec.seed_seq("s1") == 5
    await db.dispose()


class _DeadClient:
    async def get_run(self, run_id):
        return {"status": "not_found"}


async def test_recover_marks_dead_run_interrupted(db_url):
    db = Database(db_url)
    await db.init_models()
    async with db.session() as s:
        s.add(ParentTaskORM(id="pt", conversation_id="c", title="P", status="running"))
        s.add(TaskPlanORM(id="pl", parent_task_id="pt", version=1, status="active"))
        s.add(TaskNodeORM(id="T", plan_id="pl", title="t", status="running"))
        s.add(AgentInstanceORM(id="inst", conversation_id="c",
                               agent_type="coder", status="running"))
        await s.flush()
        s.add(AgentRunORM(id="r", agent_instance_id="inst",
                          hermes_run_id="hr", task_id="T", status="running"))

    rec = RecoveryManager(db, hermes_api_client=_DeadClient())
    summary = await rec.recover()
    assert summary == {"reattached": 0, "interrupted": 1}
    async with db.session() as s:
        run = await s.get(AgentRunORM, "r")
        task = await s.get(TaskNodeORM, "T")
        inst = await s.get(AgentInstanceORM, "inst")
    assert run.status == "interrupted"
    assert task.status == "retryable"      # never silently completed
    assert inst.status == "interrupted"
    await db.dispose()


class _AliveClient:
    async def get_run(self, run_id):
        return {"status": "running"}


async def test_recover_keeps_alive_run(db_url):
    db = Database(db_url)
    await db.init_models()
    async with db.session() as s:
        s.add(AgentInstanceORM(id="inst", conversation_id="c",
                               agent_type="coder", status="running"))
        await s.flush()
        s.add(AgentRunORM(id="r", agent_instance_id="inst",
                          hermes_run_id="hr", status="running"))
    rec = RecoveryManager(db, hermes_api_client=_AliveClient())
    summary = await rec.recover()
    assert summary == {"reattached": 1, "interrupted": 0}
    async with db.session() as s:
        assert (await s.get(AgentRunORM, "r")).status == "running"
    await db.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
