"""Phase 9 — Production Worker pipeline stage tests.

Independent tests for every stage (claim, lease guard, executor, result
validator, finalizer, reconciler) plus the full ``TaskExecutionPipeline``
sequence.  Includes the explicit takeover proof:

    claim A (fence_A) -> B takes over the durable lease -> A's post-execution
    authority probe rejects -> late result A (still fence_A) -> REJECT

proving no durable finalizer call / terminal mutation happens for A.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from windagent_core.contracts.execution import (
    ExecutionRequest,
    ExecutionResult,
    RuntimeStatusEnum,
)
from windagent_core.contracts.finalization import FinalizeTaskExecutionRequest

from windagent_worker.pipeline import (
    ClaimStage,
    ExecutorStage,
    FinalizeOutcome,
    FinalizerStage,
    LeaseGuardStage,
    ProposedOutcome,
    ReconcilerStage,
    ResultValidatorStage,
    TaskExecutionContext,
    TaskExecutionPipeline,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeClaim:
    task_id: str
    worker_id: str
    lease_id: str
    fencing_token: str
    lease_generation: int
    tool_name: str = "read_file"
    prompt: str = ""
    parameters: dict = field(default_factory=dict)
    acquired_at: Optional[datetime] = None


class FakeQueue:
    def __init__(
        self,
        claims=None,
        renew_result=True,
        release_result=True,
        renew_results=None,
        release_results=None,
    ):
        self.claims = list(claims or [])
        self.renew_result = renew_result
        self.release_result = release_result
        self.renew_results = list(renew_results) if renew_results is not None else None
        self.release_results = list(release_results) if release_results is not None else None
        self.renewed: list[tuple] = []
        self.released: list[tuple] = []

    async def claim_next(self, worker_id):
        if not self.claims:
            return None
        return self.claims.pop(0)

    async def renew(self, task_id, worker_id, fencing_token):
        self.renewed.append((task_id, worker_id, fencing_token))
        if self.renew_results is not None:
            if not self.renew_results:
                return self.renew_result
            return self.renew_results.pop(0)
        return self.renew_result

    async def release(self, task_id, worker_id, fencing_token):
        self.released.append((task_id, worker_id, fencing_token))
        if self.release_results is not None:
            if not self.release_results:
                return self.release_result
            return self.release_results.pop(0)
        return self.release_result


class FakeLeaseManager:
    def __init__(
        self,
        claims=None,
        renew_result=True,
        release_result=True,
        renew_results=None,
        release_results=None,
    ):
        self.claims = list(claims or [])
        self.renew_result = renew_result
        self.release_result = release_result
        self.renew_results = list(renew_results) if renew_results is not None else None
        self.release_results = list(release_results) if release_results is not None else None
        self.renewed: list[tuple] = []
        self.released: list[tuple] = []

    def claim_task(self, worker_id):
        if not self.claims:
            return None
        return self.claims.pop(0)

    def renew_lease(self, task_id, worker_id, fencing_token=None):
        self.renewed.append((task_id, worker_id, fencing_token))
        if self.renew_results is not None:
            if not self.renew_results:
                return self.renew_result
            return self.renew_results.pop(0)
        return self.renew_result

    def release_lease(self, task_id, worker_id, fencing_token=None):
        self.released.append((task_id, worker_id, fencing_token))
        if self.release_results is not None:
            if not self.release_results:
                return self.release_result
            return self.release_results.pop(0)
        return self.release_result


@dataclass
class FakeHandle:
    fencing_token: str
    handle_id: str = "h1"
    step_run_id: str = "task_1"


class FakeRegistry:
    def __init__(self, handle=None, result=None):
        self.handle = handle or FakeHandle(fencing_token="fence_1")
        self.result = result
        self.dispatched: list[ExecutionRequest] = []
        self.registered: list[tuple] = []

    async def dispatch(self, request):
        self.dispatched.append(request)
        return self.handle

    async def get_result(self, handle):
        return self.result


class FakeBroadcaster:
    def __init__(self):
        self.registered: list[tuple] = []

    def register_handle(self, handle, adapter):
        self.registered.append((handle, adapter))


class FakeUow:
    def __init__(self, finalize_result=None, existing=None):
        self.finalize_result = finalize_result or SimpleNamespace(
            status="COMPLETED",
            error_message=None,
            new_version=2,
            idempotency_key="key-1",
            already_finalized=False,
        )
        self.existing = existing or {"version": 1}
        self.requests: list[FinalizeTaskExecutionRequest] = []
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    @property
    def task_runs(self):
        return self

    async def get_by_id(self, task_id):
        return self.existing

    async def finalize_task_execution(self, request):
        self.calls += 1
        self.requests.append(request)
        return self.finalize_result


class FakeReconciler:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls: list[Any] = []

    async def reconcile(self, studio_result):
        self.calls.append(studio_result)
        if self.fail:
            raise RuntimeError("reconcile boom")


class RecordingFinalizer:
    def __init__(self):
        self.calls = 0
        self.ctx = None
        self.outcome = None

    async def finalize(self, ctx, outcome):
        self.calls += 1
        self.ctx = ctx
        self.outcome = outcome
        return FinalizeOutcome(finalized=True)


def _claim(task_id="task_1", token="fence_1", gen=1, lease_id="lease_1", **kw) -> FakeClaim:
    return FakeClaim(
        task_id=task_id,
        worker_id="wkr_test",
        lease_id=lease_id,
        fencing_token=token,
        lease_generation=gen,
        **kw,
    )


def _completed_result(step_run_id="task_1", token="fence_1", data=None) -> ExecutionResult:
    return ExecutionResult(
        handle_id="h1",
        step_run_id=step_run_id,
        status=RuntimeStatusEnum.COMPLETED,
        result_data=data or {"output": "ok"},
    )


def _make_pipeline(
    *,
    queue=None,
    lease_manager=None,
    registry=None,
    broadcaster=None,
    uow_factory=None,
    reconciler=None,
    cancellation=False,
    metrics=None,
):
    events: list[tuple] = []
    state = {
        "current_task_id": None,
        "current_fencing_token": None,
        "cancellation": cancellation,
    }
    pipeline = TaskExecutionPipeline(
        worker_id="wkr_test",
        task_queue=queue,
        lease_manager=lease_manager,
        execution_registry=registry or FakeRegistry(),
        cancellation_broadcaster=broadcaster or FakeBroadcaster(),
        uow_factory=uow_factory,
        studio_reconciler=reconciler,
        emit_event=lambda event_type, payload, aggregate_id="worker": events.append(
            (event_type, payload, aggregate_id)
        ),
        metrics=metrics if metrics is not None else {"tasks": {}, "totals": {"processed": 0, "failed": 0}},
        set_current_task=lambda tid, tok: state.update(current_task_id=tid, current_fencing_token=tok),
        clear_current_task=lambda: state.update(current_task_id=None, current_fencing_token=None),
        cancellation_requested=lambda: state["cancellation"],
        reset_cancellation=lambda: state.update(cancellation=False),
    )
    return pipeline, events, state


# ---------------------------------------------------------------------------
# Claim stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_stage_normalizes_object_claim():
    claim = _claim(
        task_id="task_obj",
        token="fence_obj_gen_2",
        gen=2,
        lease_id="lease_obj",
        tool_name="code_search",
        prompt="find bug",
        parameters={"attempt": 3, "query": "x"},
        acquired_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    queue = FakeQueue(claims=[claim])
    ctx = await ClaimStage().claim(task_queue=queue, lease_manager=None, worker_id="wkr_test")

    assert ctx is not None
    assert ctx.task_id == "task_obj"
    assert ctx.raw_task_id == "task_obj"
    assert ctx.worker_id == "wkr_test"
    assert ctx.fencing_token == "fence_obj_gen_2"
    assert ctx.lease_id == "lease_obj"
    assert ctx.lease_generation == 2
    assert ctx.tool_name == "code_search"
    assert ctx.prompt == "find bug"
    assert ctx.parameters == {"attempt": 3, "query": "x"}
    assert ctx.attempt == 3
    assert ctx.attempt_id == "att_1"
    assert ctx.claimed_at == datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_claim_stage_normalizes_legacy_dict_claim():
    claim = {
        "task_id": "task_dict",
        "prompt": "legacy prompt",
        "workflow_name": "bugfix",
    }
    mgr = FakeLeaseManager(claims=[claim])
    ctx = await ClaimStage().claim(task_queue=None, lease_manager=mgr, worker_id="wkr_test")

    assert ctx is not None
    assert ctx.task_id == "task_dict"
    assert ctx.raw_task_id == "task_dict"
    # Legacy dict claims fall back to deterministic task-ID-derived lease identity.
    assert ctx.fencing_token == "fence_task_dict_gen_1"
    assert ctx.lease_id == "lease_task_dict"
    assert ctx.lease_generation == 1
    assert ctx.tool_name == "read_file"
    assert ctx.prompt == "legacy prompt"
    assert ctx.parameters == {}
    assert ctx.attempt == 1


@pytest.mark.asyncio
async def test_claim_stage_idle_when_nothing_claimable():
    queue = FakeQueue(claims=[])
    ctx = await ClaimStage().claim(task_queue=queue, lease_manager=None, worker_id="wkr_test")
    assert ctx is None


# ---------------------------------------------------------------------------
# Lease guard stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lease_guard_renew_success_and_failure():
    ctx = TaskExecutionContext.from_claim(_claim(token="fence_1"), worker_id="wkr_test")
    queue = FakeQueue(renew_result=True)
    assert await LeaseGuardStage().renew(ctx, task_queue=queue, lease_manager=None) is True
    assert queue.renewed == [("task_1", "wkr_test", "fence_1")]

    queue_fail = FakeQueue(renew_result=False)
    assert await LeaseGuardStage().renew(ctx, task_queue=queue_fail, lease_manager=None) is False


@pytest.mark.asyncio
async def test_lease_guard_renew_sync_legacy_manager():
    ctx = TaskExecutionContext.from_claim(_claim(token="fence_1"), worker_id="wkr_test")
    mgr = FakeLeaseManager(renew_result=True)
    assert await LeaseGuardStage().renew(ctx, task_queue=None, lease_manager=mgr) is True
    assert mgr.renewed == [("task_1", "wkr_test", "fence_1")]


@pytest.mark.asyncio
async def test_lease_guard_release():
    ctx = TaskExecutionContext.from_claim(_claim(token="fence_1"), worker_id="wkr_test")
    queue = FakeQueue(release_result=True)
    assert await LeaseGuardStage().release(ctx, task_queue=queue, lease_manager=None) is True
    assert queue.released == [("task_1", "wkr_test", "fence_1")]

    mgr = FakeLeaseManager(release_result=True)
    assert await LeaseGuardStage().release(ctx, task_queue=None, lease_manager=mgr) is True
    assert mgr.released == [("task_1", "wkr_test", "fence_1")]


@pytest.mark.asyncio
async def test_lease_guard_authority_probe_rejects_after_takeover():
    """First renew succeeds; the post-execution authority probe fails after
    the durable lease was taken over by another worker."""
    ctx = TaskExecutionContext.from_claim(_claim(token="fence_A"), worker_id="wkr_test")
    queue = FakeQueue(renew_results=[True, False])
    guard = LeaseGuardStage()

    assert await guard.renew(ctx, task_queue=queue, lease_manager=None) is True
    assert await guard.check_authority(ctx, task_queue=queue, lease_manager=None) is False


@pytest.mark.asyncio
async def test_lease_guard_authority_probe_sync_legacy_manager():
    """The authority probe works through the sync legacy lease manager too."""
    ctx = TaskExecutionContext.from_claim(_claim(token="fence_A"), worker_id="wkr_test")
    mgr = FakeLeaseManager(renew_results=[True, False])
    guard = LeaseGuardStage()

    assert await guard.renew(ctx, task_queue=None, lease_manager=mgr) is True
    assert await guard.check_authority(ctx, task_queue=None, lease_manager=mgr) is False


# ---------------------------------------------------------------------------
# Executor stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_builds_request_and_registers_handle():
    ctx = TaskExecutionContext.from_claim(
        _claim(
            task_id="task_exec",
            token="fence_exec",
            tool_name="code_search",
            prompt="find it",
            parameters={"query": "q"},
        ),
        worker_id="wkr_test",
    )
    handle = FakeHandle(fencing_token="fence_exec", handle_id="h_exec", step_run_id="task_exec")
    registry = FakeRegistry(handle=handle, result=_completed_result("task_exec", "fence_exec"))
    broadcaster = FakeBroadcaster()

    await ExecutorStage().execute(
        ctx,
        execution_registry=registry,
        cancellation_broadcaster=broadcaster,
    )

    req = registry.dispatched[0]
    assert isinstance(req, ExecutionRequest)
    assert req.step_run_id == "task_exec"
    assert req.workflow_run_id == "wf_task_exec"
    assert req.tool_name == "code_search"
    assert req.parameters == {"query": "q", "task_id": "task_exec", "prompt": "find it"}
    assert req.attempt_id == "att_1"
    assert req.fencing_token == "fence_exec"
    assert broadcaster.registered == [(handle, registry)]
    assert ctx.handle is handle
    assert ctx.result is registry.result
    assert ctx.execution_finished_at is not None


# ---------------------------------------------------------------------------
# Result validator stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validator_successful_result():
    ctx = TaskExecutionContext.from_claim(_claim(token="fence_1"), worker_id="wkr_test")
    ctx.handle = FakeHandle(fencing_token="fence_1")
    ctx.result = _completed_result(data={"output": "ok"})

    outcome = await ResultValidatorStage().validate(ctx)
    assert outcome.fencing_rejected is False
    assert outcome.terminal_state == "completed"
    assert outcome.terminal_error is None
    assert outcome.result_payload == {"output": "ok"}
    assert outcome.studio_result is None


@pytest.mark.asyncio
async def test_validator_failed_result():
    ctx = TaskExecutionContext.from_claim(_claim(token="fence_1"), worker_id="wkr_test")
    ctx.handle = FakeHandle(fencing_token="fence_1")
    ctx.result = ExecutionResult(
        handle_id="h1",
        step_run_id="task_1",
        status=RuntimeStatusEnum.FAILED,
        result_data={"partial": True},
        error="boom",
    )

    outcome = await ResultValidatorStage().validate(ctx)
    assert outcome.fencing_rejected is False
    assert outcome.terminal_state == "failed"
    assert outcome.terminal_error == "boom"
    assert outcome.result_payload == {"partial": True}


@pytest.mark.asyncio
async def test_validator_malformed_studio_result():
    ctx = TaskExecutionContext.from_claim(
        _claim(token="fence_1", parameters={"studio_envelope": {"task_id": "task_1"}}),
        worker_id="wkr_test",
    )
    ctx.handle = FakeHandle(fencing_token="fence_1")
    ctx.result = _completed_result(data={"not": "a studio result"})

    outcome = await ResultValidatorStage().validate(ctx)
    assert outcome.fencing_rejected is False
    assert outcome.terminal_state == "failed"
    assert outcome.terminal_error.startswith("STUDIO_RESULT_INVALID")
    assert outcome.result_payload["error_code"] == "STUDIO_RESULT_INVALID"
    assert outcome.studio_result is None


@pytest.mark.asyncio
async def test_validator_fencing_rejection():
    ctx = TaskExecutionContext.from_claim(_claim(token="fence_A"), worker_id="wkr_test")
    # Lease takeover B: the handle/result carry the new owner's token.
    ctx.handle = FakeHandle(fencing_token="fence_B")
    ctx.result = _completed_result(data={"output": "late"})

    outcome = await ResultValidatorStage().validate(ctx)
    assert outcome.fencing_rejected is True
    assert outcome.rejection_error is not None
    assert "Fencing token mismatch" in outcome.rejection_error


# ---------------------------------------------------------------------------
# Finalizer stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalizer_exact_request_fields():
    uow = FakeUow()

    ctx = TaskExecutionContext(
        task_id="task_fin",
        raw_task_id="task_fin",
        worker_id="wkr_1",
        fencing_token="fence_1",
        lease_id="lease_1",
        lease_generation=3,
        attempt_id="att_1",
    )
    outcome = ProposedOutcome(
        terminal_state="completed",
        terminal_error=None,
        result_payload={"output": "x"},
    )

    stage = FinalizerStage(uow_factory=lambda: uow)
    result = await stage.finalize(ctx, outcome)

    assert result.finalized is True
    assert uow.calls == 1
    req = uow.requests[0]
    assert req.task_id == "task_fin"
    assert req.worker_id == "wkr_1"
    assert req.lease_id == "lease_1"
    assert req.fencing_token == "fence_1"
    assert req.fencing_generation == 3
    assert req.attempt_id == "att_1"
    assert req.terminal_state == "completed"
    assert req.execution_result == {"output": "x"}
    assert req.result_artifacts == []
    assert req.terminal_event["event_type"] == "task.completed"
    assert req.terminal_event["task_id"] == "task_fin"
    assert req.terminal_event["status"] == "completed"
    assert ctx.finalized_at is not None


@pytest.mark.asyncio
async def test_finalizer_rejection_propagates():
    uow = FakeUow(
        finalize_result=SimpleNamespace(
            status="REJECTED_STALE",
            error_message="STALE_RESULT_REJECTED",
            task_id="task_fin",
            new_version=1,
            idempotency_key="k",
            already_finalized=False,
        )
    )

    ctx = TaskExecutionContext(
        task_id="task_fin",
        raw_task_id="task_fin",
        worker_id="wkr_1",
        fencing_token="fence_1",
        lease_id="lease_1",
        lease_generation=1,
    )
    outcome = ProposedOutcome(terminal_state="completed", result_payload={})

    with pytest.raises(RuntimeError, match="Task finalization rejected"):
        await FinalizerStage(uow_factory=lambda: uow).finalize(ctx, outcome)


# ---------------------------------------------------------------------------
# Reconciler stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconciler_after_commit():
    reconciler = FakeReconciler()
    ctx = TaskExecutionContext.from_claim(_claim(), worker_id="wkr_test")
    outcome = ProposedOutcome(terminal_state="completed", studio_result=object())

    ok = await ReconcilerStage().reconcile(ctx, outcome, studio_reconciler=reconciler)
    assert ok is True
    assert len(reconciler.calls) == 1


@pytest.mark.asyncio
async def test_reconciler_recoverable_failure():
    reconciler = FakeReconciler(fail=True)
    ctx = TaskExecutionContext.from_claim(_claim(), worker_id="wkr_test")
    outcome = ProposedOutcome(terminal_state="completed", studio_result=object())

    ok = await ReconcilerStage().reconcile(ctx, outcome, studio_reconciler=reconciler)
    assert ok is False  # failure is swallowed; terminal persistence stays intact


@pytest.mark.asyncio
async def test_reconciler_skipped_without_studio_result():
    ctx = TaskExecutionContext.from_claim(_claim(), worker_id="wkr_test")
    outcome = ProposedOutcome(terminal_state="completed", studio_result=None)
    assert await ReconcilerStage().reconcile(ctx, outcome, studio_reconciler=FakeReconciler()) is False


# ---------------------------------------------------------------------------
# Pipeline sequence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_full_sequence_completed():
    queue = FakeQueue(claims=[_claim(task_id="task_seq", token="fence_seq", gen=2, lease_id="lease_seq")])
    registry = FakeRegistry(
        handle=FakeHandle(fencing_token="fence_seq", step_run_id="task_seq"),
        result=_completed_result("task_seq", "fence_seq", data={"output": "done"}),
    )
    metrics = {"tasks": {}, "totals": {"processed": 0, "failed": 0}}
    pipeline, events, state = _make_pipeline(
        queue=queue,
        registry=registry,
        uow_factory=object(),
        metrics=metrics,
    )
    pipeline.finalizer = RecordingFinalizer()

    response = await pipeline.run_tick()

    assert response == {"status": "completed", "task_id": "task_seq", "processed": 1}
    assert pipeline.finalizer.calls == 1
    assert pipeline.finalizer.ctx.task_id == "task_seq"
    assert pipeline.finalizer.ctx.lease_id == "lease_seq"
    assert pipeline.finalizer.ctx.lease_generation == 2
    assert pipeline.finalizer.outcome.terminal_state == "completed"
    assert metrics["tasks"]["task_seq"]["status"] == "completed"
    assert metrics["totals"]["processed"] == 1
    assert queue.released == []  # lease released atomically by the finalizer, not manually
    assert state["current_task_id"] is None
    assert state["current_fencing_token"] is None
    event_types = [e[0] for e in events]
    assert "task.created" in event_types
    assert "task.completed" in event_types


@pytest.mark.asyncio
async def test_pipeline_fallback_release_without_uow():
    queue = FakeQueue(claims=[_claim(task_id="task_fb", token="fence_fb")])
    registry = FakeRegistry(
        handle=FakeHandle(fencing_token="fence_fb", step_run_id="task_fb"),
        result=_completed_result("task_fb", "fence_fb"),
    )
    pipeline, events, state = _make_pipeline(queue=queue, registry=registry, uow_factory=None)

    response = await pipeline.run_tick()

    assert response == {"status": "completed", "task_id": "task_fb", "processed": 1}
    # No UoW -> manual fallback release of the exact lease.
    assert queue.released == [("task_fb", "wkr_test", "fence_fb")]


@pytest.mark.asyncio
async def test_pipeline_lease_error():
    queue = FakeQueue(claims=[_claim(task_id="task_le", token="fence_le")], renew_result=False)
    pipeline, events, state = _make_pipeline(queue=queue, uow_factory=None)

    response = await pipeline.run_tick()

    assert response == {"status": "lease_error", "task_id": "task_le"}
    assert state["current_task_id"] is None
    assert state["current_fencing_token"] is None


@pytest.mark.asyncio
async def test_pipeline_cancellation_releases_and_resets():
    queue = FakeQueue(claims=[_claim(task_id="task_cx", token="fence_cx")])
    pipeline, events, state = _make_pipeline(queue=queue, uow_factory=None, cancellation=True)

    response = await pipeline.run_tick()

    assert response == {"status": "cancelled", "task_id": "task_cx"}
    assert queue.released == [("task_cx", "wkr_test", "fence_cx")]
    assert state["cancellation"] is False  # reset after handling
    assert state["current_task_id"] is None
    event_types = [e[0] for e in events]
    assert "task.cancelled" in event_types


@pytest.mark.asyncio
async def test_pipeline_idle():
    queue = FakeQueue(claims=[])
    pipeline, events, state = _make_pipeline(queue=queue, uow_factory=None)
    assert await pipeline.run_tick() == {"status": "idle", "processed": 0}


# ---------------------------------------------------------------------------
# Takeover proof: claim A -> lease takeover B -> late result A -> REJECT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_takeover_late_result_rejected_without_finalization():
    """A late result after a durable lease takeover is rejected and never finalized.

    Worker A claims the task and renews with ``fence_A``.  Worker B takes over
    the durable lease before A returns, so A's post-execution authority probe
    (exact-token renew as the CAS probe) is rejected.  A's already-dispatched
    runtime handle/result still carry ``fence_A`` — the handle-token validator
    alone cannot detect the takeover — so the pipeline's current-lease authority
    check is what rejects the late result BEFORE any terminal event, validator,
    finalizer, reconciler, or terminal metric mutation.  The stale-token release
    attempt fails closed and never touches B's lease.
    """
    queue = FakeQueue(
        claims=[_claim(task_id="task_takeover", token="fence_A", gen=1, lease_id="lease_takeover")],
        renew_results=[True, False],  # heartbeat renew OK; authority probe rejects A
        release_results=[False],  # stale-token release attempt fails closed
    )
    registry = FakeRegistry(
        handle=FakeHandle(fencing_token="fence_A", handle_id="hA", step_run_id="task_takeover"),
        result=_completed_result("task_takeover", "fence_A", data={"output": "late"}),
    )
    metrics = {"tasks": {}, "totals": {"processed": 0, "failed": 0}}
    pipeline, events, state = _make_pipeline(
        queue=queue,
        registry=registry,
        uow_factory=object(),  # non-None: the finalize branch WOULD run if reached
        metrics=metrics,
    )
    pipeline.finalizer = RecordingFinalizer()

    response = await pipeline.run_tick()

    assert response["status"] == "fencing_violation"
    assert response["task_id"] == "task_takeover"
    assert "LEASE_TAKEOVER" in response["error"]
    assert "fence_A" in response["error"]

    # No durable finalizer call / terminal mutation for A.
    assert pipeline.finalizer.calls == 0
    assert metrics["tasks"] == {}
    assert metrics["totals"] == {"processed": 0, "failed": 0}

    # No terminal completed/failed diagnostic event was emitted for A.
    event_types = [e[0] for e in events]
    assert "task.created" in event_types
    assert "task.completed" not in event_types
    assert "task.failed" not in event_types

    # The stale-token release attempt happened but failed closed (returned
    # False) — it never released B's current lease.
    assert queue.released == [("task_takeover", "wkr_test", "fence_A")]
    assert state["current_task_id"] is None
    assert state["current_fencing_token"] is None


# ---------------------------------------------------------------------------
# Runner tick is a small delegate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_tick_is_a_small_delegate():
    source = open(
        __import__("pathlib").Path(__file__).resolve().parents[4]
        / "apps" / "worker" / "windagent_worker" / "runner.py",
        encoding="utf-8",
    ).read()
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "poll_and_execute_tick":
            body_lines = [n for n in node.body if not (
                isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
            )]
            assert len(body_lines) <= 4, (
                f"poll_and_execute_tick must be a small delegate, got {len(body_lines)} statements"
            )
            break
    else:
        raise AssertionError("poll_and_execute_tick not found in runner.py")

    # The delegate must route through the pipeline.
    assert "self._pipeline().run_tick()" in source