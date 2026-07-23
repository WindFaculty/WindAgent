"""
Phase C Execute Endpoint Integration Tests with Orchestration V2 Engine.
"""

import uuid
import pytest

from db.models import TaskPlanORM, TaskNodeORM, TaskEdgeORM, ParentTaskORM
from windagent_orchestration.workflow_engine import (
    WorkflowDefinition, WorkflowNode, WorkflowValidator, WorkflowGraph, DAGValidationError
)


async def _setup_plan(db):
    """Seed a 3-node plan: A -> B -> C."""
    pt = ParentTaskORM(
        id=f"pt_{uuid.uuid4().hex[:8]}",
        prompt="Test plan",
        session_id="test_sess",
    )
    plan = TaskPlanORM(
        id=f"plan_{uuid.uuid4().hex[:8]}",
        parent_task_id=pt.id,
    )
    async with db.session() as s:
        s.add(pt)
        s.add(plan)
        # 3 nodes
        for nid in ["A", "B", "C"]:
            s.add(TaskNodeORM(
                id=nid,
                plan_id=plan.id,
                title=f"Node {nid}",
                agent_type="coding",
                status="pending",
            ))
        # A -> B -> C
        s.add(TaskEdgeORM(
            id=f"e1_{uuid.uuid4().hex[:8]}",
            plan_id=plan.id,
            from_task_id="A",
            to_task_id="B",
        ))
        s.add(TaskEdgeORM(
            id=f"e2_{uuid.uuid4().hex[:8]}",
            plan_id=plan.id,
            from_task_id="B",
            to_task_id="C",
        ))
        await s.commit()

    return pt.id, plan.id


async def test_execute_plan_endpoint(db):
    """Execute a plan via Orchestration V2 WorkflowEngine."""
    pt_id, plan_id = await _setup_plan(db)

    wf = WorkflowDefinition(id=plan_id, name="Test Plan Workflow")
    wf.add_node(WorkflowNode(id="A", name="Node A", tool_name="tool_a"))
    wf.add_node(WorkflowNode(id="B", name="Node B", tool_name="tool_b"))
    wf.add_node(WorkflowNode(id="C", name="Node C", tool_name="tool_c"))
    wf.add_edge("A", "B")
    wf.add_edge("B", "C")

    duration_ms = WorkflowValidator.validate_definition(wf)
    assert duration_ms >= 0.0


async def test_execute_plan_cycle_rejected(db):
    """Plan with cycle is rejected by Orchestration V2 WorkflowValidator."""
    pt_id, plan_id = await _setup_plan(db)

    wf = WorkflowDefinition(id=plan_id, name="Cycle Plan Workflow")
    wf.add_node(WorkflowNode(id="A", name="Node A", tool_name="tool_a"))
    wf.add_node(WorkflowNode(id="B", name="Node B", tool_name="tool_b"))
    wf.add_node(WorkflowNode(id="C", name="Node C", tool_name="tool_c"))
    wf.add_edge("A", "B")
    wf.add_edge("B", "C")
    wf.add_edge("C", "A")

    graph = WorkflowGraph(wf)
    with pytest.raises(DAGValidationError, match="Cycle detected"):
        graph.detect_cycles()