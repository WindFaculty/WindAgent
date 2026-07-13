"""Phase 8 backend surface (ban_ke_hoan §13): list conversation agents,
task graph, per-agent event replay.
"""
import pytest

from db.models import (
    AgentInstanceORM, AgentRunORM, ParentTaskORM, TaskPlanORM,
    TaskNodeORM, TaskEdgeORM,
)


async def test_conversation_agents_and_tasks(client, db):
    await db.init_models()
    cid = "conv8"

    async with db.session() as s:
        s.add(AgentInstanceORM(id="a1", conversation_id=cid, agent_type="coder", status="running"))
        s.add(AgentInstanceORM(id="a2", conversation_id=cid, agent_type="tester", status="idle"))
        await s.flush()
        s.add(AgentRunORM(id="r1", agent_instance_id="a1", hermes_session_id="sess_a1", status="running"))
        s.add(ParentTaskORM(id="pt", conversation_id=cid, title="P", status="running"))
        s.add(TaskPlanORM(id="pl", parent_task_id="pt", version=1, status="active"))
        s.add(TaskNodeORM(id="T1", plan_id="pl", title="code", status="running"))
        s.add(TaskNodeORM(id="T2", plan_id="pl", title="test", status="blocked", assigned_agent_instance_id="a2"))
        s.add(TaskEdgeORM(id="e1", plan_id="pl", from_task_id="T1", to_task_id="T2", edge_type="finish_to_start"))

    # endpoints live on the running app fixture's DB; point client at it
    resp = client.get(f"/api/v1/conversations/{cid}/agents")
    assert resp.status_code == 200
    agents = resp.json()
    by_id = {a["id"]: a for a in agents}
    assert by_id["a1"]["session_id"] == "sess_a1"
    assert by_id["a1"]["run_status"] == "running"

    g = client.get(f"/api/v1/conversations/{cid}/tasks").json()
    assert g["plan_id"] == "pl"
    assert {n["id"] for n in g["nodes"]} == {"T1", "T2"}
    assert g["edges"][0]["to"] == "T2"

    ev = client.get(f"/api/v1/agents/a1/events?after_seq=0")
    assert ev.status_code == 200
    assert ev.json()["session_id"] == "sess_a1"


async def test_agent_events_404(client):
    resp = client.get("/api/v1/agents/nope/events")
    assert resp.status_code == 404
