"""Additional compatibility tests for the Phase 3 stateful-runtime contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


root = Path(__file__).resolve().parents[3]
for package in ("core", "storage", "orchestration", "execution", "workflows"):
    package_path = str(root / package)
    if package_path not in sys.path:
        sys.path.insert(0, package_path)

from windagent_core.contracts.stateful_execution import (  # noqa: E402
    AttachSessionRequest,
    CheckpointRequest,
    CreateSessionRequest,
    InspectRequest,
    RestoreRequest,
    StatefulExecuteRequest,
    StatefulSessionStatus,
)
from windagent_execution.stateful_runtime import StatefulExecutionRuntime  # noqa: E402


@pytest.mark.asyncio
async def test_contract_session_can_reattach_from_shared_runtime_store() -> None:
    shared_store: dict = {}
    first_runtime = StatefulExecutionRuntime(store=shared_store)
    created = await first_runtime.create_session(
        CreateSessionRequest(
            workflow_run_id="wf_reattach",
            session_id="sess_reattach",
        )
    )
    handle = await first_runtime.execute(
        StatefulExecuteRequest(
            session_id=created.session_id,
            step_run_id="step_1",
            tool_name="echo",
            parameters={"message": "hello"},
        )
    )

    second_runtime = StatefulExecutionRuntime(store=shared_store)
    attached = await second_runtime.attach_session(
        AttachSessionRequest(session_id=created.session_id)
    )
    inspection = await second_runtime.inspect(
        InspectRequest(session_id=created.session_id)
    )

    assert attached.status is StatefulSessionStatus.ACTIVE
    assert handle.handle_id in inspection.active_handle_ids
    assert inspection.runtime_state_summary["execution_count"] == 1


@pytest.mark.asyncio
async def test_contract_checkpoint_restore_and_host_authority_guard() -> None:
    runtime = StatefulExecutionRuntime()
    session = await runtime.create_session(
        CreateSessionRequest(workflow_run_id="wf_checkpoint", session_id="sess_checkpoint")
    )
    await runtime.execute(
        StatefulExecuteRequest(
            session_id=session.session_id,
            step_run_id="step_1",
            tool_name="echo",
            parameters={"value": 42},
        )
    )
    checkpoint = await runtime.checkpoint(CheckpointRequest(session_id=session.session_id))
    restored = await runtime.restore(
        RestoreRequest(
            checkpoint_id=checkpoint.checkpoint_id,
            target_session_id="sess_restored",
        )
    )

    assert restored.session_id == "sess_restored"
    inspection = await runtime.inspect(InspectRequest(session_id=restored.session_id))
    assert inspection.runtime_state_summary["execution_count"] == 1
    with pytest.raises(ValueError, match="Host authority"):
        await runtime.execute(
            StatefulExecuteRequest(
                session_id=session.session_id,
                step_run_id="forbidden",
                tool_name="echo",
                parameters={"api_key": "not-allowed"},
            )
        )
