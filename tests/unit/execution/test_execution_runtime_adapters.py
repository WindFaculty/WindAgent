"""
Phase 3 Unit Tests: Execution Runtime Port and Adapters.
Verifies FakeRuntimeAdapter and HermesRuntimeAdapter conform to ExecutionRuntimePort.
"""

from __future__ import annotations

from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
for pkg in ["core", "storage", "orchestration", "execution", "workflows"]:
    p = str(root / pkg)

import pytest  # noqa: E402 - package paths are configured immediately above for standalone runs
from windagent_orchestration.ports import (  # noqa: E402 - see path bootstrap above
    ExecutionRuntimePort, ExecutionRequest, RuntimeStatusEnum
)
from windagent_execution import FakeRuntimeAdapter, HermesRuntimeAdapter  # noqa: E402


@pytest.mark.asyncio
async def test_fake_runtime_adapter_success():
    """Verify FakeRuntimeAdapter success dispatch and result lifecycle."""
    adapter: ExecutionRuntimePort = FakeRuntimeAdapter(default_mode="success")
    
    req = ExecutionRequest(
        step_run_id="step_101",
        workflow_run_id="wf_101",
        tool_name="read_file",
        parameters={"path": "/tmp/test"},
        attempt_id="att_1",
        fencing_token="fence_101",
    )

    handle = await adapter.dispatch(req)
    assert handle.step_run_id == "step_101"
    assert handle.fencing_token == "fence_101"

    status = await adapter.get_status(handle)
    assert status.status == RuntimeStatusEnum.COMPLETED

    res = await adapter.get_result(handle)
    assert res.status == RuntimeStatusEnum.COMPLETED
    assert res.result_data is not None

    reattached = await adapter.reattach(handle.runtime_run_id)
    assert reattached == handle


@pytest.mark.asyncio
async def test_fake_runtime_adapter_failure_and_cancel():
    """Verify FakeRuntimeAdapter failure and cancellation modes."""
    fail_adapter = FakeRuntimeAdapter(default_mode="failure")
    req = ExecutionRequest(
        step_run_id="step_102",
        workflow_run_id="wf_102",
        tool_name="run_command",
        attempt_id="att_1",
        fencing_token="fence_102",
    )
    h_fail = await fail_adapter.dispatch(req)
    res_fail = await fail_adapter.get_result(h_fail)
    assert res_fail.status == RuntimeStatusEnum.FAILED

    run_adapter = FakeRuntimeAdapter(default_mode="running")
    h_run = await run_adapter.dispatch(req)
    await run_adapter.cancel(h_run)
    status_c = await run_adapter.get_status(h_run)
    assert status_c.status == RuntimeStatusEnum.CANCELLED


@pytest.mark.asyncio
async def test_fake_runtime_adapter_controls_individual_steps_and_crash():
    """Phase 8: a chaos fake can isolate step behavior and refuse reattach after crash."""
    adapter = FakeRuntimeAdapter(default_mode="running")
    adapter.set_mode_for_step("step-fail", "failure")
    failing = await adapter.dispatch(
        ExecutionRequest(
            step_run_id="step-fail",
            workflow_run_id="wf-phase8",
            tool_name="agent_generalist",
            attempt_id="attempt-fail",
            fencing_token="fence-fail",
        )
    )
    live = await adapter.dispatch(
        ExecutionRequest(
            step_run_id="step-live",
            workflow_run_id="wf-phase8",
            tool_name="agent_generalist",
            attempt_id="attempt-live",
            fencing_token="fence-live",
        )
    )

    assert (await adapter.get_status(failing)).status == RuntimeStatusEnum.FAILED
    assert (await adapter.get_status(live)).status == RuntimeStatusEnum.RUNNING

    adapter.complete(live.runtime_run_id, {"checkpoint": "saved"})
    assert (await adapter.get_result(live)).result_data == {"checkpoint": "saved"}
    adapter.crash(live.runtime_run_id)
    assert (await adapter.get_status(live)).status == RuntimeStatusEnum.LOST
    assert await adapter.reattach(live.runtime_run_id) is None


@pytest.mark.asyncio
async def test_hermes_runtime_adapter_contract():
    """Verify HermesRuntimeAdapter conforms to ExecutionRuntimePort protocol."""
    class MockBridge:
        async def submit_message(self, **kwargs):
            return {"run_id": "hermes_real_123", "session_id": kwargs.get("windagent_session_id")}

    adapter: ExecutionRuntimePort = HermesRuntimeAdapter(bridge=MockBridge())
    req = ExecutionRequest(
        step_run_id="step_201",
        workflow_run_id="wf_201",
        tool_name="hermes_chat",
        attempt_id="att_1",
        fencing_token="fence_201",
    )

    handle = await adapter.dispatch(req)
    assert handle.runtime_run_id == "hermes_real_123"
    
    status = await adapter.get_status(handle)
    assert status.status in (RuntimeStatusEnum.RUNNING, RuntimeStatusEnum.UNKNOWN)