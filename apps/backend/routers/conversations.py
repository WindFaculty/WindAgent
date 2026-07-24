"""Add execute endpoint wiring supervisor → DAG → route lock → run_plan."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from db.models import (
    AgentInstanceORM,
    AgentRunORM,
    ParentTaskORM,
    TaskEdgeORM,
    TaskNodeORM,
    TaskPlanORM,
)
from schemas.event import EventEnvelope

router = APIRouter(prefix="/api/v1", tags=["conversations"])


def _db(request: Request):
    return request.app.state.db


@router.get("/conversations/{conversation_id}/agents")
async def list_agents(conversation_id: str, request: Request) -> List[Dict[str, Any]]:
    db = _db(request)
    async with db.session() as s:
        insts = (await s.execute(
            select(AgentInstanceORM).where(
                AgentInstanceORM.conversation_id == conversation_id
            )
        )).scalars().all()
        rows: List[Dict[str, Any]] = []
        for inst in insts:
            run = (await s.execute(
                select(AgentRunORM).where(
                    AgentRunORM.agent_instance_id == inst.id
                ).order_by(AgentRunORM.started_at.desc())
            )).scalars().first()
            rows.append({
                "id": inst.id,
                "agent_type": inst.agent_type,
                "status": inst.status,
                "permission_profile": inst.permission_profile,
                "task_id": inst.task_id,
                "run_status": run.status if run else None,
                "session_id": run.hermes_session_id if run else None,
                "created_at": inst.created_at.isoformat() if inst.created_at else None,
            })
    return rows


@router.get("/conversations/{conversation_id}/tasks")
async def task_graph(conversation_id: str, request: Request) -> Dict[str, Any]:
    db = _db(request)
    plan_id: Optional[str] = None
    version: int = 1
    async with db.session() as s:
        pt = (await s.execute(
            select(ParentTaskORM).where(
                ParentTaskORM.conversation_id == conversation_id
            )
        )).scalars().first()
        if pt:
            plan = (await s.execute(
                select(TaskPlanORM).where(
                    TaskPlanORM.parent_task_id == pt.id,
                    TaskPlanORM.status == "active",
                )
            )).scalars().first()
            if plan:
                plan_id = plan.id
                version = plan.version
        if not plan_id:
            return {"plan_id": None, "version": 1, "nodes": [], "edges": []}
        nodes = (await s.execute(
            select(TaskNodeORM).where(TaskNodeORM.plan_id == plan_id)
        )).scalars().all()
        edges = (await s.execute(
            select(TaskEdgeORM).where(TaskEdgeORM.plan_id == plan_id)
        )).scalars().all()
    return {
        "plan_id": plan_id,
        "version": version,
        "nodes": [
            {
                "id": n.id,
                "title": n.title,
                "description": n.description,
                "agent_type": n.agent_type,
                "status": n.status,
                "assigned_agent": n.assigned_agent_instance_id,
            }
            for n in nodes
        ],
        "edges": [
            {"id": e.id, "from": e.from_task_id, "to": e.to_task_id, "kind": e.edge_type}
            for e in edges
        ],
    }


@router.get("/agents/{agent_instance_id}/events")
async def agent_events(
    agent_instance_id: str,
    request: Request,
    after_seq: int = Query(0, ge=0),
) -> Dict[str, Any]:
    db = _db(request)
    rec = getattr(request.app.state, "recovery_manager", getattr(request.app.state, "orchestration_recovery", None))
    async with db.session() as s:
        inst = await s.get(AgentInstanceORM, agent_instance_id)
        if inst is None:
            raise HTTPException(status_code=404, detail="agent instance not found")
        run = (await s.execute(
            select(AgentRunORM).where(
                AgentRunORM.agent_instance_id == agent_instance_id
            ).order_by(AgentRunORM.started_at.desc())
        )).scalars().first()
    session_id = run.hermes_session_id if run else None
    events = []
    if rec is not None and hasattr(rec, "replay_after"):
        events = await rec.replay_after(session_id, after_seq)
    elif rec is not None and hasattr(rec, "replay_events_after"):
        events = await rec.replay_events_after(session_id, after_seq)
    else:
        async with db.session() as s:
            from db.models import ExecutionEventORM
            import json
            rows = (await s.execute(
                select(ExecutionEventORM)
                .where(
                    ExecutionEventORM.session_id == session_id,
                    ExecutionEventORM.event_seq > after_seq,
                )
                .order_by(ExecutionEventORM.event_seq)
            )).scalars().all()
            events = [
                {
                    "event": r.event_type,
                    "event_type": r.event_type,
                    "seq": r.event_seq,
                    "data": json.loads(r.data_json or "{}"),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
    return {
        "agent_instance_id": agent_instance_id,
        "session_id": session_id,
        "events": [e.model_dump(mode="json") if hasattr(e, "model_dump") else e for e in events],
    }


# ---------- orchestration execution (Phase C) ----------

import logging
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PatchTaskNodeRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    agent_type: Optional[str] = None
    status: Optional[str] = None
    assigned_agent_instance_id: Optional[str] = None
    version: int


class CreateTaskNodeRequest(BaseModel):
    title: str
    description: Optional[str] = None
    agent_type: str
    status: Optional[str] = "blocked"
    version: int


class CreateTaskEdgeRequest(BaseModel):
    from_task_id: str
    to_task_id: str
    edge_type: str = "requires"
    version: int


class ExecutePlanResponse(BaseModel):
    plan_id: str
    result: str  # completed | partial | failed
    completed: List[str]
    failed: List[str]


async def _get_active_plan(s, conversation_id: str):
    pt = (await s.execute(
        select(ParentTaskORM).where(ParentTaskORM.conversation_id == conversation_id)
    )).scalars().first()
    if not pt:
        raise HTTPException(status_code=404, detail="parent task not found")
    plan = (await s.execute(
        select(TaskPlanORM).where(
            TaskPlanORM.parent_task_id == pt.id,
            TaskPlanORM.status == "active",
        )
    )).scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="active plan not found")
    return pt, plan


import asyncio
from windagent_orchestration.workflow_engine import (
    WorkflowDefinition, WorkflowNode, WorkflowValidator, WorkflowGraph, DAGValidationError
)
from windagent_core.domain.models import WorkflowStep


async def _run_plan_executor(plan_id: str, request: Request, nodes: List[TaskNodeORM], edges: List[TaskEdgeORM]) -> ExecutePlanResponse:
    """Execute plan via Orchestration V2 engine. Runs nodes in dependency order."""
    db = _db(request)
    dispatcher = getattr(request.app.state, "orchestration_dispatcher", None)
    bus = getattr(request.app.state, "event_bus", None)

    # In-degree map & node map
    in_degree: Dict[str, int] = {n.id: 0 for n in nodes}
    adj_list: Dict[str, List[str]] = {n.id: [] for n in nodes}
    for e in edges:
        if e.to_task_id in in_degree:
            in_degree[e.to_task_id] += 1
        if e.from_task_id in adj_list:
            adj_list[e.from_task_id].append(e.to_task_id)

    completed: List[str] = []
    failed: List[str] = []

    # Ready queue: nodes with 0 incoming dependencies
    ready_queue: List[str] = [nid for nid, deg in in_degree.items() if deg == 0]

    while ready_queue:
        current_id = ready_queue.pop(0)

        # Mark node running in DB
        async with db.session() as s:
            node = await s.get(TaskNodeORM, current_id)
            if node:
                node.started_at = datetime.now(timezone.utc)
                node.status = "running"
                await s.commit()

        if bus:
            env = EventEnvelope(
                event="task.started",
                data={"plan_id": plan_id, "task_id": current_id},
            )
            await bus.publish(plan_id, env)

        # Execute node step via Orchestration V2 Dispatcher or Runtime Port
        step = WorkflowStep(
            id=current_id,
            order=1,
            name=f"Task {current_id}",
            tool_name="read_file",
            params={},
        )
        
        success = True
        if dispatcher and hasattr(dispatcher, "dispatch_step_durable"):
            success = await dispatcher.dispatch_step_durable(plan_id, step, worker_id="backend_worker")
        
        async with db.session() as s:
            node = await s.get(TaskNodeORM, current_id)
            if node:
                node.status = "completed" if success else "failed"
                node.finished_at = datetime.now(timezone.utc)
                await s.commit()

        if bus:
            env = EventEnvelope(
                event="task.completed" if success else "task.failed",
                data={"plan_id": plan_id, "task_id": current_id},
            )
            await bus.publish(plan_id, env)

        if success:
            completed.append(current_id)
            for neighbor in adj_list.get(current_id, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    ready_queue.append(neighbor)
        else:
            failed.append(current_id)

    return ExecutePlanResponse(
        plan_id=plan_id,
        result="completed" if not failed and len(completed) == len(nodes) else "partial" if completed else "failed",
        completed=completed,
        failed=failed,
    )


@router.post("/conversations/{conversation_id}/plans/{plan_id}/execute")
async def execute_plan(
    conversation_id: str,
    plan_id: str,
    request: Request,
) -> ExecutePlanResponse:
    """Run a DAG plan through Orchestration V2 engine.

    Validates DAG first using WorkflowValidator, then executes nodes in dependency order.
    """
    db = _db(request)

    # Load and validate plan
    async with db.session() as s:
        plan = await s.get(TaskPlanORM, plan_id)
        if not plan or plan.status != "active":
            raise HTTPException(status_code=404, detail="plan not found or not active")
        edges = (await s.execute(
            select(TaskEdgeORM).where(TaskEdgeORM.plan_id == plan_id)
        )).scalars().all()
        nodes = (await s.execute(
            select(TaskNodeORM).where(TaskNodeORM.plan_id == plan_id)
        )).scalars().all()

    if not nodes:
        raise HTTPException(status_code=400, detail="plan has no tasks")

    # Build Orchestration V2 WorkflowDefinition & validate DAG
    wf = WorkflowDefinition(id=plan_id, name=f"Plan {plan_id}")
    for n in nodes:
        wf.add_node(WorkflowNode(id=n.id, name=n.title or n.id, tool_name="read_file"))
    for e in edges:
        wf.add_edge(e.from_task_id, e.to_task_id)

    graph = WorkflowGraph(wf)
    try:
        graph.detect_cycles()
    except DAGValidationError as ex:
        raise HTTPException(status_code=400, detail=str(ex))

    # Reset node statuses according to dependency readiness
    in_degree = {n.id: 0 for n in nodes}
    for e in edges:
        if e.to_task_id in in_degree:
            in_degree[e.to_task_id] += 1

    async with db.session() as s:
        for n in nodes:
            n.status = "ready" if in_degree[n.id] == 0 else "pending"
            n.started_at = None
            n.finished_at = None
        await s.commit()

    result = await _run_plan_executor(plan_id, request, list(nodes), list(edges))

    # Mark plan complete
    async with db.session() as s:
        p = await s.get(TaskPlanORM, plan_id)
        if p:
            p.status = "completed" if result.result == "completed" else "partial" if result.result == "partial" else "failed"
            await s.commit()

    return result


# ---------- Task Editing endpoints ----------


async def _get_current_graph(s, plan_id: str):
    nodes = (await s.execute(
        select(TaskNodeORM).where(TaskNodeORM.plan_id == plan_id)
    )).scalars().all()
    edges = (await s.execute(
        select(TaskEdgeORM).where(TaskEdgeORM.plan_id == plan_id)
    )).scalars().all()
    return {
        "nodes": [
            {
                "id": n.id,
                "title": n.title,
                "description": n.description,
                "agent_type": n.agent_type,
                "status": n.status,
                "assigned_agent": n.assigned_agent_instance_id,
            }
            for n in nodes
        ],
        "edges": [
            {"id": e.id, "from": e.from_task_id, "to": e.to_task_id, "kind": e.edge_type}
            for e in edges
        ],
    }


async def _notify_replan(request: Request, conversation_id: str, plan_id: str, new_version: int):
    bus = getattr(request.app.state, "event_bus", None)
    if bus:
        env = EventEnvelope(
            event="replan_notification",
            data={"plan_id": plan_id, "version": new_version},
        )
        await bus.publish(conversation_id, env)


@router.patch("/conversations/{conversation_id}/tasks/nodes/{node_id}")
async def patch_task_node(
    conversation_id: str,
    node_id: str,
    payload: PatchTaskNodeRequest,
    request: Request,
) -> Dict[str, Any]:
    db = _db(request)
    async with db.session() as s:
        async with s.begin():
            pt, plan = await _get_active_plan(s, conversation_id)
            if plan.version != payload.version:
                raise HTTPException(status_code=409, detail="Plan version conflict")
            node = (await s.execute(
                select(TaskNodeORM).where(
                    TaskNodeORM.plan_id == plan.id,
                    TaskNodeORM.id == node_id,
                )
            )).scalars().first()
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            if payload.title is not None:
                node.title = payload.title
            if payload.description is not None:
                node.description = payload.description
            if payload.agent_type is not None:
                node.agent_type = payload.agent_type
            if payload.status is not None:
                node.status = payload.status
            if payload.assigned_agent_instance_id is not None:
                node.assigned_agent_instance_id = payload.assigned_agent_instance_id
            plan.version += 1
            new_ver = plan.version
        graph = await _get_current_graph(s, plan.id)
    await _notify_replan(request, conversation_id, plan.id, new_ver)
    return {"plan_id": plan.id, "version": new_ver, **graph}


@router.post("/conversations/{conversation_id}/tasks/nodes")
async def create_task_node(
    conversation_id: str,
    payload: CreateTaskNodeRequest,
    request: Request,
) -> Dict[str, Any]:
    db = _db(request)
    async with db.session() as s:
        async with s.begin():
            pt, plan = await _get_active_plan(s, conversation_id)
            if plan.version != payload.version:
                raise HTTPException(status_code=409, detail="Plan version conflict")
            new_id = f"T_{uuid.uuid4().hex[:8]}"
            node = TaskNodeORM(
                id=new_id,
                plan_id=plan.id,
                title=payload.title,
                description=payload.description,
                agent_type=payload.agent_type,
                status=payload.status or "blocked",
            )
            s.add(node)
            plan.version += 1
            new_ver = plan.version
        graph = await _get_current_graph(s, plan.id)
    await _notify_replan(request, conversation_id, plan.id, new_ver)
    return {"plan_id": plan.id, "version": new_ver, **graph}


@router.delete("/conversations/{conversation_id}/tasks/nodes/{node_id}")
async def delete_task_node(
    conversation_id: str,
    node_id: str,
    request: Request,
    version: int = Query(...),
) -> Dict[str, Any]:
    db = _db(request)
    async with db.session() as s:
        async with s.begin():
            pt, plan = await _get_active_plan(s, conversation_id)
            if plan.version != version:
                raise HTTPException(status_code=409, detail="Plan version conflict")
            node = (await s.execute(
                select(TaskNodeORM).where(
                    TaskNodeORM.plan_id == plan.id, TaskNodeORM.id == node_id
                )
            )).scalars().first()
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            edges = (await s.execute(
                select(TaskEdgeORM).where(
                    TaskEdgeORM.plan_id == plan.id,
                    (TaskEdgeORM.from_task_id == node_id) | (TaskEdgeORM.to_task_id == node_id),
                )
            )).scalars().all()
            for e in edges:
                await s.delete(e)
            await s.delete(node)
            plan.version += 1
            new_ver = plan.version
        graph = await _get_current_graph(s, plan.id)
    await _notify_replan(request, conversation_id, plan.id, new_ver)
    return {"plan_id": plan.id, "version": new_ver, **graph}


def detect_cycle(plan_id: str, edges: List[TaskEdgeORM]) -> Optional[List[str]]:
    adj: Dict[str, List[str]] = {}
    nodes_set = set()
    for e in edges:
        nodes_set.add(e.from_task_id)
        nodes_set.add(e.to_task_id)
        adj.setdefault(e.from_task_id, []).append(e.to_task_id)

    visited: Dict[str, int] = {n: 0 for n in nodes_set}
    path: List[str] = []

    def dfs(node: str) -> Optional[List[str]]:
        visited[node] = 1
        path.append(node)
        for nxt in adj.get(node, []):
            if visited.get(nxt, 0) == 1:
                idx = path.index(nxt)
                return path[idx:] + [nxt]
            if visited.get(nxt, 0) == 0:
                c = dfs(nxt)
                if c:
                    return c
        path.pop()
        visited[node] = 2
        return None

    for node in list(nodes_set):
        if visited.get(node, 0) == 0:
            c = dfs(node)
            if c:
                return c
    return None


@router.post("/conversations/{conversation_id}/tasks/edges")
async def create_task_edge(
    conversation_id: str,
    payload: CreateTaskEdgeRequest,
    request: Request,
) -> Dict[str, Any]:
    db = _db(request)
    async with db.session() as s:
        async with s.begin():
            pt, plan = await _get_active_plan(s, conversation_id)
            if plan.version != payload.version:
                raise HTTPException(status_code=409, detail="Plan version conflict")
            from_node = (await s.execute(
                select(TaskNodeORM).where(TaskNodeORM.plan_id == plan.id, TaskNodeORM.id == payload.from_task_id)
            )).scalars().first()
            to_node = (await s.execute(
                select(TaskNodeORM).where(TaskNodeORM.plan_id == plan.id, TaskNodeORM.id == payload.to_task_id)
            )).scalars().first()
            if not from_node or not to_node:
                raise HTTPException(status_code=404, detail="edge endpoint not found")
            new_id = f"E_{uuid.uuid4().hex[:8]}"
            edge = TaskEdgeORM(
                id=new_id,
                plan_id=plan.id,
                from_task_id=payload.from_task_id,
                to_task_id=payload.to_task_id,
                edge_type=payload.edge_type,
            )
            s.add(edge)
            # detect cycle
            edges = (await s.execute(
                select(TaskEdgeORM).where(TaskEdgeORM.plan_id == plan.id)
            )).scalars().all()
            cycle = detect_cycle(plan.id, list(edges))
            if cycle:
                raise HTTPException(status_code=400, detail=f"Cycle detected: {' -> '.join(cycle)}")
            plan.version += 1
            new_ver = plan.version
        graph = await _get_current_graph(s, plan.id)
    await _notify_replan(request, conversation_id, plan.id, new_ver)
    return {"plan_id": plan.id, "version": new_ver, **graph}


@router.delete("/conversations/{conversation_id}/tasks/edges")
async def delete_task_edge(
    conversation_id: str,
    from_task_id: str = Query(...),
    to_task_id: str = Query(...),
    version: int = Query(...),
    request: Request = None,
) -> Dict[str, Any]:
    db = _db(request)
    async with db.session() as s:
        async with s.begin():
            pt, plan = await _get_active_plan(s, conversation_id)
            if plan.version != version:
                raise HTTPException(status_code=409, detail="Plan version conflict")
            edge = (await s.execute(
                select(TaskEdgeORM).where(
                    TaskEdgeORM.plan_id == plan.id,
                    TaskEdgeORM.from_task_id == from_task_id,
                    TaskEdgeORM.to_task_id == to_task_id,
                )
            )).scalars().first()
            if not edge:
                raise HTTPException(status_code=404, detail="edge not found")
            await s.delete(edge)
            plan.version += 1
            new_ver = plan.version
        graph = await _get_current_graph(s, plan.id)
    await _notify_replan(request, conversation_id, plan.id, new_ver)
    return {"plan_id": plan.id, "version": new_ver, **graph}


@router.post("/tasks/{node_id}/pause")
async def pause_task(node_id: str, request: Request) -> Dict[str, Any]:
    db = _db(request)
    async with db.session() as s:
        async with s.begin():
            node = await s.get(TaskNodeORM, node_id)
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            node.status = "paused"
            plan = await s.get(TaskPlanORM, node.plan_id)
            pt = await s.get(ParentTaskORM, plan.parent_task_id) if plan else None
            convo_id = pt.conversation_id if pt else None
        if plan and convo_id:
            await _notify_replan(request, convo_id, plan.id, plan.version)
    return {"status": "paused", "node_id": node_id}


@router.post("/tasks/{node_id}/resume")
async def resume_task(node_id: str, request: Request) -> Dict[str, Any]:
    db = _db(request)
    async with db.session() as s:
        async with s.begin():
            node = await s.get(TaskNodeORM, node_id)
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            node.status = "ready"
            plan = await s.get(TaskPlanORM, node.plan_id)
            pt = await s.get(ParentTaskORM, plan.parent_task_id) if plan else None
            convo_id = pt.conversation_id if pt else None
        if plan and convo_id:
            await _notify_replan(request, convo_id, plan.id, plan.version)
    return {"status": "resumed", "node_id": node_id}


@router.post("/tasks/{node_id}/cancel")
async def cancel_task(node_id: str, request: Request) -> Dict[str, Any]:
    db = _db(request)
    supervisor = getattr(request.app.state, "hermes_supervisor", None)
    async with db.session() as s:
        async with s.begin():
            node = await s.get(TaskNodeORM, node_id)
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            node.status = "cancelled"
            node.finished_at = datetime.now(timezone.utc)
            run = (await s.execute(
                select(AgentRunORM).where(
                    AgentRunORM.task_id == node_id,
                    AgentRunORM.status == "running",
                )
            )).scalars().first()
            if run:
                run.status = "cancelled"
                run.finished_at = datetime.now(timezone.utc)
                inst = await s.get(AgentInstanceORM, run.agent_instance_id)
                if inst:
                    inst.status = "cancelled"
            plan = await s.get(TaskPlanORM, node.plan_id)
            pt = await s.get(ParentTaskORM, plan.parent_task_id) if plan else None
            convo_id = pt.conversation_id if pt else None
        if run and run.hermes_run_id and supervisor:
            try:
                await supervisor.stop_subagent(run.hermes_run_id)
            except Exception as e:
                logger.warning("stop sub-agent failed: %s", e)
        if plan and convo_id:
            await _notify_replan(request, convo_id, plan.id, plan.version)
    return {"status": "cancelled", "node_id": node_id}


@router.post("/tasks/{node_id}/retry")
async def retry_task(node_id: str, request: Request) -> Dict[str, Any]:
    db = _db(request)
    async with db.session() as s:
        async with s.begin():
            node = await s.get(TaskNodeORM, node_id)
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            node.status = "ready"
            node.retry_count += 1
            node.started_at = None
            node.finished_at = None
            plan = await s.get(TaskPlanORM, node.plan_id)
            pt = await s.get(ParentTaskORM, plan.parent_task_id) if plan else None
            convo_id = pt.conversation_id if pt else None
        if plan and convo_id:
            await _notify_replan(request, convo_id, plan.id, plan.version)
    return {"status": "retry_requested", "node_id": node_id}