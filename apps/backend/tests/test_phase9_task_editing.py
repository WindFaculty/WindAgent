import pytest
from db.models import (
    AgentInstanceORM, AgentRunORM, ParentTaskORM, TaskPlanORM,
    TaskNodeORM, TaskEdgeORM,
)


@pytest.fixture
async def setup_dag(db):
    await db.init_models()
    cid = "conv9"
    async with db.session() as s:
        s.add(AgentInstanceORM(id="a1", conversation_id=cid, agent_type="coder", status="running"))
        s.add(AgentInstanceORM(id="a2", conversation_id=cid, agent_type="tester", status="idle"))
        await s.flush()
        s.add(AgentRunORM(id="r1", agent_instance_id="a1", hermes_session_id="sess_a1", status="running"))
        s.add(ParentTaskORM(id="pt", conversation_id=cid, title="P", status="running"))
        s.add(TaskPlanORM(id="pl", parent_task_id="pt", version=1, status="active"))
        s.add(TaskNodeORM(id="T1", plan_id="pl", title="code", description="coding task", agent_type="coder", status="running"))
        s.add(TaskNodeORM(id="T2", plan_id="pl", title="test", description="testing task", agent_type="tester", status="blocked", assigned_agent_instance_id="a2"))
        s.add(TaskEdgeORM(id="e1", plan_id="pl", from_task_id="T1", to_task_id="T2", edge_type="requires"))
        await s.commit()
    return cid


async def test_get_task_graph(client, setup_dag):
    cid = setup_dag
    resp = client.get(f"/api/v1/conversations/{cid}/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan_id"] == "pl"
    assert data["version"] == 1
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["nodes"][0]["description"] == "coding task"


async def test_patch_task_node_success_and_conflict(client, setup_dag):
    cid = setup_dag
    
    # 1. Patch success
    resp = client.patch(
        f"/api/v1/conversations/{cid}/tasks/nodes/T1",
        json={"title": "new code", "version": 1}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 2
    assert any(n["id"] == "T1" and n["title"] == "new code" for n in data["nodes"])

    # 2. Patch conflict (using old version 1)
    resp_conflict = client.patch(
        f"/api/v1/conversations/{cid}/tasks/nodes/T1",
        json={"title": "conflicted", "version": 1}
    )
    assert resp_conflict.status_code == 409
    assert resp_conflict.json()["detail"] == "Plan version conflict"


async def test_create_and_delete_node(client, setup_dag):
    cid = setup_dag
    
    # 1. Create task node
    resp = client.post(
        f"/api/v1/conversations/{cid}/tasks/nodes",
        json={"title": "deploy", "agent_type": "deployer", "version": 1}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 2
    assert len(data["nodes"]) == 3
    new_node = [n for n in data["nodes"] if n["title"] == "deploy"][0]
    new_id = new_node["id"]

    # 2. Delete task node
    resp_del = client.delete(
        f"/api/v1/conversations/{cid}/tasks/nodes/{new_id}?version=2"
    )
    assert resp_del.status_code == 200
    data_del = resp_del.json()
    assert data_del["version"] == 3
    assert len(data_del["nodes"]) == 2
    assert not any(n["id"] == new_id for n in data_del["nodes"])


async def test_create_edge_success_and_cycle(client, setup_dag):
    cid = setup_dag
    
    # Add T3 node first
    resp = client.post(
        f"/api/v1/conversations/{cid}/tasks/nodes",
        json={"title": "T3", "agent_type": "coder", "version": 1}
    )
    assert resp.status_code == 200
    t3_id = [n for n in resp.json()["nodes"] if n["title"] == "T3"][0]["id"]
    
    # Current edges: T1 -> T2
    # 1. Add valid edge: T2 -> T3
    resp_edge = client.post(
        f"/api/v1/conversations/{cid}/tasks/edges",
        json={"from_task_id": "T2", "to_task_id": t3_id, "version": 2}
    )
    assert resp_edge.status_code == 200
    assert resp_edge.json()["version"] == 3
    assert len(resp_edge.json()["edges"]) == 2

    # 2. Add cyclic edge: T3 -> T1 (Cycle: T1 -> T2 -> T3 -> T1)
    resp_cycle = client.post(
        f"/api/v1/conversations/{cid}/tasks/edges",
        json={"from_task_id": t3_id, "to_task_id": "T1", "version": 3}
    )
    assert resp_cycle.status_code == 400
    assert "Cycle detected" in resp_cycle.json()["detail"]


async def test_control_endpoints(client, setup_dag):
    cid = setup_dag
    
    # 1. Pause task
    resp = client.post("/api/v1/tasks/T1/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"
    
    # 2. Resume task
    resp = client.post("/api/v1/tasks/T1/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "resumed"

    # 3. Retry task
    resp = client.post("/api/v1/tasks/T1/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] == "retry_requested"

    # 4. Cancel task
    resp = client.post("/api/v1/tasks/T1/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
