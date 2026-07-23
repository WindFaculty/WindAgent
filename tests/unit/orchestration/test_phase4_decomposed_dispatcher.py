"""
Phase 4 Unit Tests: Decomposed Dispatcher Architecture.
Verifies StepClaimService, StepDispatchService, ResultIngestionService, LeaseFinalizerService, and StepDispatcher pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "apps/backend"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from windagent_storage.orm.v2_orchestration_models import BaseORM as V2BaseORM
from windagent_orchestration.dispatcher import (
    StepDispatcher, StepClaimService, StepDispatchService,
    ResultIngestionService, LeaseFinalizerService, LeaseManager
)
from windagent_orchestration.ports import ExecutionHandle, ExecutionResult, RuntimeStatusEnum
from windagent_execution import FakeRuntimeAdapter
from windagent_core.domain.models import WorkflowStep
from windagent_core.errors.exceptions import DomainError


@pytest_asyncio.fixture
async def db_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(V2BaseORM.metadata.create_all)
    
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_step_claim_service(db_factory):
    """Verify StepClaimService acquires atomic lease with fencing token."""
    lease_mgr = LeaseManager(uow_factory=db_factory)
    claim_svc = StepClaimService(lease_mgr)

    lease1 = await claim_svc.claim_step("step_1", "run_1", "w1")
    assert lease1 is not None
    assert lease1.step_run_id == "step_1"

    # Concurrent claim on active lease returns None
    lease2 = await claim_svc.claim_step("step_1", "run_1", "w2")
    assert lease2 is None


@pytest.mark.asyncio
async def test_step_dispatch_and_ingestion_services(db_factory):
    """Verify StepDispatchService and ResultIngestionService with fencing token validation."""
    fake_runtime = FakeRuntimeAdapter(default_mode="success")
    lease_mgr = LeaseManager(uow_factory=db_factory)
    claim_svc = StepClaimService(lease_mgr)
    dispatch_svc = StepDispatchService(fake_runtime, uow_factory=db_factory)
    ingest_svc = ResultIngestionService(fake_runtime, uow_factory=db_factory)

    lease = await claim_svc.claim_step("step_10", "run_10", "w1")
    assert lease is not None

    handle = await dispatch_svc.dispatch_to_runtime(lease, "read_file", {"path": "test.txt"})
    assert handle.fencing_token == lease.fencing_token

    res = await ingest_svc.ingest_result(handle)
    assert res.status == RuntimeStatusEnum.COMPLETED

    # Stale handle submission with invalid fencing token is rejected
    stale_handle = ExecutionHandle(
        handle_id="stale_h",
        runtime_run_id="stale_run",
        step_run_id="step_10",
        attempt_id="att_old",
        fencing_token="stale_token_123",
    )
    stale_res = ExecutionResult(
        handle_id="stale_h",
        step_run_id="step_10",
        status=RuntimeStatusEnum.COMPLETED,
    )
    with pytest.raises(DomainError) as exc_info:
        await ingest_svc.ingest_result(stale_handle, stale_res)
    assert exc_info.value.code == "WINDAGENT_ERR_STALE_FENCING_TOKEN"


@pytest.mark.asyncio
async def test_step_dispatcher_end_to_end(db_factory):
    """Verify StepDispatcher pipeline end-to-end."""
    fake_runtime = FakeRuntimeAdapter(default_mode="success")
    dispatcher = StepDispatcher(runtime_port=fake_runtime, uow_factory=db_factory)

    step = type("MockStep", (), {
        "id": "step_20",
        "name": "Step 20",
        "tool_name": "write_file",
        "parameters": {"file": "a.txt"},
    })()

    ok = await dispatcher.dispatch_step_durable("run_20", step, worker_id="w1")
    assert ok is True
