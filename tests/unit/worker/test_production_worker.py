"""
Unit tests for WindAgent Production Worker and TaskLeaseManager (Phase 12).
Tests task claims, heartbeat lease renewal, multi-worker lock safety, task cancellation, and abandoned task recovery.
"""

import time
import pytest
from windagent_worker import TaskLeaseManager, ProductionWorker


def test_task_lease_manager_claims_and_renewals():
    mgr = TaskLeaseManager(default_lease_ttl_sec=5.0)
    mgr.add_pending_task("task_01", "Fix bug", "bugfix")

    # Worker 1 claims task
    claimed = mgr.claim_task("worker_1")
    assert claimed is not None
    assert claimed["task_id"] == "task_01"

    # Multi-worker lock safety: Worker 2 attempts to claim task_01 -> must get None
    claimed_w2 = mgr.claim_task("worker_2")
    assert claimed_w2 is None

    # Lease renewal heartbeat
    renewed = mgr.renew_lease("task_01", "worker_1")
    assert renewed is True

    # Release lease
    released = mgr.release_lease("task_01", "worker_1")
    assert released is True


def test_abandoned_task_recovery():
    # Very short TTL of 0.1 sec
    mgr = TaskLeaseManager(default_lease_ttl_sec=0.1)
    mgr.add_pending_task("task_abandoned", "Abandoned task test", "ci_fix")

    # Worker 1 claims task
    claimed = mgr.claim_task("worker_1")
    assert claimed is not None

    # Sleep to allow lease to expire
    time.sleep(0.15)

    # Worker 2 claims -> lease expired -> abandoned task recovered and assigned to Worker 2
    claimed_w2 = mgr.claim_task("worker_2")
    assert claimed_w2 is not None
    assert claimed_w2["task_id"] == "task_abandoned"


@pytest.mark.asyncio
async def test_production_worker_lifecycle_and_tick():
    mgr = TaskLeaseManager()
    mgr.add_pending_task("task_tick", "Tick test", "feature")

    worker = ProductionWorker(name="unit-worker-1", lease_manager=mgr)
    await worker.start()
    assert worker.is_running is True
    assert worker.is_ready is True

    # Poll and execute tick
    tick_result = await worker.poll_and_execute_tick()
    assert tick_result["status"] == "completed"
    assert tick_result["task_id"] == "task_tick"

    await worker.stop()
    assert worker.is_running is False


@pytest.mark.asyncio
async def test_production_worker_cancellation():
    mgr = TaskLeaseManager()
    mgr.add_pending_task("task_cancel", "Cancel test", "refactor")

    worker = ProductionWorker(name="unit-worker-2", lease_manager=mgr)
    await worker.start()

    # Request cancellation
    await worker.cancel()

    tick_result = await worker.poll_and_execute_tick()
    assert tick_result["status"] == "cancelled"

    await worker.stop()
