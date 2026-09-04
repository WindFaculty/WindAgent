"""E2E Test: Agent Runtime sessions, DAG workflow transitions, and approvals."""

from __future__ import annotations

import pytest
from windagent.kernel.time import SystemClock
from windagent.modules.agent_runtime.application.runtime import (
    AgentRuntimeContainer,
    AgentRuntimeServices,
)
from windagent.modules.agent_runtime.infrastructure.memory import (
    InMemoryAgentRuntimeStore,
    memory_scope_factory,
)


@pytest.mark.asyncio
async def test_e2e_agent_workflow_and_approval_flow() -> None:
    store = InMemoryAgentRuntimeStore()
    clock = SystemClock()
    services = AgentRuntimeServices(
        scope_factory=memory_scope_factory(store),
        clock=clock,
    )
    container = AgentRuntimeContainer(services)

    # 1. Start Session
    sess_view = await container.agent_runtime.create_session(
        actor_id="user-engineer",
        title="Automated Refactoring Session",
    )
    assert sess_view is not None
    assert sess_view.session_id is not None
    assert sess_view.title == "Automated Refactoring Session"

    # 2. Create Run and Task
    run_view = await container.agent_runtime.create_run(
        session_id=sess_view.session_id,
    )
    assert run_view is not None

    task_view = await container.agent_runtime.create_task(
        session_id=sess_view.session_id,
        run_id=run_view.run_id,
        title="Execute deployment task",
    )
    assert task_view is not None

    # Transition task to RUNNING so it can request approval
    await container.agent_runtime.transition_task(
        task_id=task_view.task_id,
        target_state="RUNNING",
    )

    # 3. Handle Human-in-the-Loop Approval Gate
    appr_view = await container.agent_runtime.request_approval(
        task_id=task_view.task_id,
        requested_by="senior_lead",
        payload={"action": "deploy_to_staging"},
    )
    assert appr_view is not None
    assert appr_view.state == "PENDING"

    resolved_view = await container.agent_runtime.resolve_approval(
        approval_id=appr_view.approval_id,
        target_state="APPROVED",
    )
    assert resolved_view is not None
    assert resolved_view.state == "APPROVED"
