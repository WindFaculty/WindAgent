"""
Unit Tests for Workflow Engine, DAG Validation, Fan-Out/Fan-In, Checkpoint/Resume, and Performance Gates (Phase D).
"""

import pytest
from windagent_orchestration.workflow_engine import (
    WorkflowDefinition, WorkflowNode, WorkflowEngine, WorkflowValidator, WorkflowGraph, DAGValidationError
)


def test_dag_cycle_detection():
    wf = WorkflowDefinition(id="wf_cycle", name="Cycle Workflow")
    wf.add_node(WorkflowNode(id="A", name="Node A", tool_name="tool_a"))
    wf.add_node(WorkflowNode(id="B", name="Node B", tool_name="tool_b"))
    wf.add_node(WorkflowNode(id="C", name="Node C", tool_name="tool_c"))

    wf.add_edge("A", "B")
    wf.add_edge("B", "C")
    wf.add_edge("C", "A")  # Cycle A -> B -> C -> A

    graph = WorkflowGraph(wf)
    with pytest.raises(DAGValidationError, match="Cycle detected"):
        graph.detect_cycles()


def test_workflow_fan_out_fan_in():
    wf = WorkflowDefinition(id="wf_fan", name="Fan Out Fan In Workflow")
    wf.add_node(WorkflowNode(id="root", name="Root", tool_name="init"))
    wf.add_node(WorkflowNode(id="branch_1", name="Branch 1", tool_name="work1"))
    wf.add_node(WorkflowNode(id="branch_2", name="Branch 2", tool_name="work2"))
    wf.add_node(WorkflowNode(id="join", name="Join", tool_name="aggregate"))

    wf.add_edge("root", "branch_1")
    wf.add_edge("root", "branch_2")
    wf.add_edge("branch_1", "join")
    wf.add_edge("branch_2", "join")

    engine = WorkflowEngine()
    engine.initialize_run("run_fan", wf)

    assert engine.get_ready_nodes("run_fan") == ["root"]

    # Mark root dispatched & completed
    engine.mark_node_dispatched("run_fan", "root")
    pytest.helpers.async_run(engine.complete_node("run_fan", "root", {"status": "success"})) if hasattr(pytest, "helpers") else None


@pytest.mark.asyncio
async def test_workflow_fan_out_fan_in_async():
    wf = WorkflowDefinition(id="wf_fan_async", name="Fan Out Fan In Workflow")
    wf.add_node(WorkflowNode(id="root", name="Root", tool_name="init"))
    wf.add_node(WorkflowNode(id="b1", name="B1", tool_name="work1"))
    wf.add_node(WorkflowNode(id="b2", name="B2", tool_name="work2"))
    wf.add_node(WorkflowNode(id="join", name="Join", tool_name="aggregate"))

    wf.add_edge("root", "b1")
    wf.add_edge("root", "b2")
    wf.add_edge("b1", "join")
    wf.add_edge("b2", "join")

    engine = WorkflowEngine()
    engine.initialize_run("run_fan_async", wf)

    assert engine.get_ready_nodes("run_fan_async") == ["root"]

    # Complete root -> b1 & b2 become ready
    newly_ready = await engine.complete_node("run_fan_async", "root", {"status": "success"})
    assert set(newly_ready) == {"b1", "b2"}

    # Complete b1 -> join is NOT ready yet (b2 still pending)
    ready_b1 = await engine.complete_node("run_fan_async", "b1", {"status": "success"})
    assert ready_b1 == []

    # Complete b2 -> join IS ready now (fan-in gate satisfied)
    ready_b2 = await engine.complete_node("run_fan_async", "b2", {"status": "success"})
    assert ready_b2 == ["join"]


def test_dag_1k_validation_performance_gate():
    wf = WorkflowDefinition(id="wf_1k", name="1K Node Workflow")
    for i in range(1000):
        wf.add_node(WorkflowNode(id=f"node_{i}", name=f"Node {i}", tool_name="noop"))
        if i > 0:
            wf.add_edge(f"node_{i-1}", f"node_{i}")

    duration_ms = WorkflowValidator.validate_definition(wf)
    print(f"1,000 node DAG validation duration: {duration_ms:.2f} ms")
    assert duration_ms <= 200.0, f"1k DAG validation gate failed: {duration_ms:.2f} ms > 200 ms"


def test_dag_10k_validation_performance_gate():
    wf = WorkflowDefinition(id="wf_10k", name="10K Node Workflow")
    for i in range(10000):
        wf.add_node(WorkflowNode(id=f"n_{i}", name=f"Node {i}", tool_name="noop"))
        if i > 0:
            wf.add_edge(f"n_{i-1}", f"n_{i}")

    duration_ms = WorkflowValidator.validate_definition(wf)
    print(f"10,000 node DAG validation duration: {duration_ms:.2f} ms")
    assert duration_ms <= 500.0, f"10k DAG validation gate failed: {duration_ms:.2f} ms > 500 ms"


def test_workflow_engine_rejects_story_node_tool_name():
    wf = WorkflowDefinition(id="wf_story", name="Story Workflow")
    wf.add_node(WorkflowNode(id="node_1", name="Idea", tool_name="studio.story.idea.generate"))
    engine = WorkflowEngine()
    with pytest.raises(ValueError, match="Story task rejected"):
        engine.initialize_run("run_story", wf)


def test_workflow_engine_rejects_story_node_id():
    wf = WorkflowDefinition(id="wf_story_2", name="Story Workflow 2")
    wf.add_node(WorkflowNode(id="studio.story.bible.generate", name="Bible", tool_name="noop"))
    engine = WorkflowEngine()
    with pytest.raises(ValueError, match="Story task rejected"):
        engine.initialize_run("run_story_2", wf)


def test_workflow_engine_rejects_story_params_reference():
    wf = WorkflowDefinition(id="wf_story_3", name="Story Workflow 3")
    wf.add_node(
        WorkflowNode(
            id="node_3",
            name="Review",
            tool_name="noop",
            params={"task_type": "studio.story.review"},
        )
    )
    engine = WorkflowEngine()
    with pytest.raises(ValueError, match="Story task rejected"):
        engine.initialize_run("run_story_3", wf)


def test_workflow_engine_accepts_legacy_nodes():
    wf = WorkflowDefinition(id="wf_legacy", name="Legacy Workflow")
    wf.add_node(WorkflowNode(id="root", name="Root", tool_name="init"))
    engine = WorkflowEngine()
    state = engine.initialize_run("run_legacy", wf)
    assert state["run_id"] == "run_legacy"
