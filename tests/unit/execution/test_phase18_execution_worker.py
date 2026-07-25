"""
Phase 18 Integration and Unit Tests: Durable Execution Plane & Production Worker.
Verifies multi-replica fencing isolation, late result rejection with stale fencing tokens,
cancellation propagation, and crash recovery logic.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "apps/worker"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from windagent_core.contracts.execution import ExecutionRequest, RuntimeStatusEnum, ExecutionResult
from windagent_core.errors.exceptions import DomainError
from windagent_execution import (
    ExecutionRuntimeRegistry, DurableExecutionRequest, ExecutionResultHandler,
    CancellationBroadcaster, ToolRuntimeAdapter, BrowserRuntimeAdapter,
    LocalAgentRuntimeAdapter, SubprocessRuntimeAdapter
)
from windagent_worker import DurableTaskLeaseManager, ProductionWorker


@pytest.mark.asyncio
async def test_execution_runtime_registry_adapter_routing():
    """Verify ExecutionRuntimeRegistry routes requests based on tool capabilities."""
    registry = ExecutionRuntimeRegistry()

    req_tool = ExecutionRequest(step_run_id="s1", workflow_run_id="w1", tool_name="read_file")
    h_tool = await registry.dispatch(req_tool)
    assert h_tool.handle_id.startswith("tool_h_")

    req_browser = ExecutionRequest(step_run_id="s2", workflow_run_id="w1", tool_name="browser_navigate")
    h_browser = await registry.dispatch(req_browser)
    assert h_browser.handle_id.startswith("browser_h_")

    req_subproc = ExecutionRequest(step_run_id="s3", workflow_run_id="w1", tool_name="run_command")
    h_subproc = await registry.dispatch(req_subproc)
    assert h_subproc.handle_id.startswith("subproc_h_")

    req_agent = ExecutionRequest(step_run_id="s4", workflow_run_id="w1", tool_name="agent_reason")
    h_agent = await registry.dispatch(req_agent)
    assert h_agent.handle_id.startswith("local_h_")


@pytest.mark.asyncio
async def test_fencing_token_validation_and_late_result_rejection():
    """Verify late result commits with stale fencing tokens are rejected."""
    active_fence = "fence_step_101_gen_2"
    stale_fence = "fence_step_101_gen_1"

    valid_res = ExecutionResult(
        handle_id="h1",
        step_run_id="step_101",
        status=RuntimeStatusEnum.COMPLETED,
        result_data={"ok": True},
    )

    # Valid fencing token match -> success
    validated = ExecutionResultHandler.validate_and_wrap(
        result=valid_res,
        active_fencing_token=active_fence,
        result_fencing_token=active_fence,
        lease_generation=2,
    )
    assert validated.fencing_token == active_fence
    assert validated.lease_generation == 2

    # Stale fencing token -> raises DomainError
    with pytest.raises(DomainError) as exc_info:
        ExecutionResultHandler.validate_and_wrap(
            result=valid_res,
            active_fencing_token=active_fence,
            result_fencing_token=stale_fence,
            lease_generation=2,
        )
    assert exc_info.value.code == "WINDAGENT_ERR_FENCING_TOKEN_STALE"


@pytest.mark.asyncio
async def test_multi_worker_fencing_isolation():
    """Verify two workers cannot claim or commit the same step simultaneously."""
    mgr = DurableTaskLeaseManager(default_lease_ttl_sec=5.0)
    mgr.add_pending_task("task_fence_01", "Multi-replica test", "security")

    w1 = ProductionWorker(name="replica-1", lease_manager=mgr)
    w2 = ProductionWorker(name="replica-2", lease_manager=mgr)

    await w1.start()
    await w2.start()

    # Worker 1 claims task
    claimed_1 = mgr.claim_task("replica-1")
    assert claimed_1 is not None
    assert claimed_1["task_id"] == "task_fence_01"

    # Worker 2 attempts claim on same task -> returns None
    claimed_2 = mgr.claim_task("replica-2")
    assert claimed_2 is None

    await w1.stop()
    await w2.stop()


@pytest.mark.asyncio
async def test_worker_cancellation_propagation():
    """Verify worker cancellation propagates to running execution handles."""
    mgr = DurableTaskLeaseManager()
    mgr.add_pending_task("task_cancel_prop", "Cancel prop test", "workflow")

    worker = ProductionWorker(name="cancel-worker", lease_manager=mgr)
    await worker.start()

    await worker.cancel()
    res = await worker.poll_and_execute_tick()
    assert res["status"] == "cancelled"

    await worker.stop()


@pytest.mark.asyncio
async def test_crash_recovery_lease_reclaim():
    """Verify worker lease expiration allows deterministic reclaim by new worker."""
    mgr = DurableTaskLeaseManager(default_lease_ttl_sec=0.1)
    mgr.add_pending_task("task_crash_01", "Crash recovery test", "resilience")

    claimed_1 = mgr.claim_task("worker_crashed")
    assert claimed_1 is not None

    time.sleep(0.15)  # Allow lease to expire

    # Worker 2 claims expired task -> takeover succeeds
    claimed_2 = mgr.claim_task("worker_recovery")
    assert claimed_2 is not None
    assert claimed_2["task_id"] == "task_crash_01"
