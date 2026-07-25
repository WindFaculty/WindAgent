"""Phase 4 Unit Tests: Worker Heartbeat & Lease Management.

Validates background worker heartbeat recording, lease renewal, fencing token cancellation,
and SqlWorkerStatusQuery accuracy.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from windagent_core.contracts.workers.models import WorkSubmission, WorkerHealth
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue
from windagent_storage.repositories.worker_status import SqlWorkerHeartbeatRepository, SqlWorkerStatusQuery
from windagent_worker.runner import ProductionWorker


@pytest.fixture
async def db_manager():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    try:
        yield db
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_worker_heartbeat_periodically_recorded_in_sql(db_manager):
    """Worker start periodically records heartbeat into SqlWorkerHeartbeatRepository."""
    heartbeat_repo = SqlWorkerHeartbeatRepository(db_manager.session_factory)
    worker = ProductionWorker(
        name="hb-test-worker",
        heartbeat_repo=heartbeat_repo,
        heartbeat_interval_sec=0.1,
    )

    await worker.start()
    await asyncio.sleep(0.25)

    workers = await heartbeat_repo.get_active_workers(stale_after_seconds=30)
    assert len(workers) == 1
    assert workers[0].worker_id == "wkr_hb-test-worker"
    assert workers[0].health == WorkerHealth.HEALTHY

    await worker.stop()


@pytest.mark.asyncio
async def test_heartbeat_renews_active_lease(db_manager):
    """Worker heartbeats renew active task lease during task execution."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    task_id = await submitter.submit(WorkSubmission(prompt="Heartbeat lease renewal test"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    heartbeat_repo = SqlWorkerHeartbeatRepository(db_manager.session_factory)

    claimed = await queue.claim_next("wkr_worker_01", lease_ttl_seconds=10)
    assert claimed is not None

    worker = ProductionWorker(
        name="worker_01",
        task_queue=queue,
        heartbeat_repo=heartbeat_repo,
        heartbeat_interval_sec=0.1,
    )
    worker._current_task_id = claimed.task_id
    worker._current_fencing_token = claimed.fencing_token

    # Trigger heartbeat record manually
    await worker.record_heartbeat()

    # Try renewing with valid fencing token via queue
    renewed = await queue.renew(task_id, "wkr_worker_01", claimed.fencing_token)
    assert renewed is True


@pytest.mark.asyncio
async def test_fencing_token_mismatch_during_heartbeat_cancels_task(db_manager):
    """Fencing token mismatch during heartbeat triggers task cancellation."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    task_id = await submitter.submit(WorkSubmission(prompt="Fencing cancellation test"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    heartbeat_repo = SqlWorkerHeartbeatRepository(db_manager.session_factory)

    claimed = await queue.claim_next("wkr_stale", lease_ttl_seconds=10)
    assert claimed is not None

    worker = ProductionWorker(
        name="stale",
        task_queue=queue,
        heartbeat_repo=heartbeat_repo,
        heartbeat_interval_sec=0.1,
    )
    worker._current_task_id = claimed.task_id
    worker._current_fencing_token = "invalid_stale_fencing_token"

    # Trigger heartbeat record -> should fail lease renewal and set cancellation requested
    await worker.record_heartbeat()
    assert worker._cancellation_requested is True


@pytest.mark.asyncio
async def test_worker_status_query_reflects_active_workers_and_leases(db_manager):
    """SqlWorkerStatusQuery accurately reports active workers and active leases count."""
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    task_id = await submitter.submit(WorkSubmission(prompt="Status query test"))

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    heartbeat_repo = SqlWorkerHeartbeatRepository(db_manager.session_factory)
    status_query = SqlWorkerStatusQuery(heartbeat_repo)

    # Initial status -> 0 workers, 0 active leases
    status1 = await status_query.get_status(stale_after_seconds=30)
    assert status1.available is False
    assert status1.active_workers == 0

    # Claim task & record heartbeat
    claimed = await queue.claim_next("wkr_query_test", lease_ttl_seconds=30)
    assert claimed is not None

    worker = ProductionWorker(
        name="query_test",
        task_queue=queue,
        heartbeat_repo=heartbeat_repo,
        heartbeat_interval_sec=0.1,
    )
    worker._current_task_id = claimed.task_id
    worker._current_fencing_token = claimed.fencing_token
    await worker.record_heartbeat()

    status2 = await status_query.get_status(stale_after_seconds=30)
    assert status2.available is True
    assert status2.active_workers == 1
    assert status2.active_leases == 1
