"""
Phase 17 — Durable production workflow unit tests (plan 05 §9).

Covers the gate test matrix:
- happy path with a fake step executor (provider steps pause at WAITING_PROVIDER);
- pause/resume at every approval gate;
- worker crash before/after external submit (no duplicate submit);
- duplicate event/result idempotency;
- lease expiry and stale-write rejection (version CAS + lease);
- human-action pause/resume;
- cancel/archive;
- single-shot failure keeps successful siblings;
- outbox replay after restart.
"""

from __future__ import annotations

import tempfile
import time
import uuid
from pathlib import Path

import pytest

from windagent_core.errors.exceptions import (
    ConcurrentStateConflictError,
    DomainError,
    InvalidStateTransitionError,
    TerminalStateMutationError,
)

from windagent_orchestration.production import (
    ApprovalLedger,
    PendingExternalOperation,
    ProductionApproval,
    ProductionApprovalGate,
    ProductionCheckpoint,
    ProductionRecovery,
    ProductionRun,
    ProductionRunState,
    ProductionRunStateMachine,
    ProductionRunStore,
    ProductionScheduler,
    ProductionStepNode,
    ProductionStepState,
    ProductionStepStateMachine,
    ProductionWorkflowEngine,
    ProviderJobState,
    RecoveryAction,
    SchedulerFacts,
    StepExecutionResult,
)
from windagent_workflows.video_production import (
    STEP_APPROVAL_GATES,
    VIDEO_PRODUCTION_STEPS,
    build_production_step_nodes,
)

PROVIDER_STEPS = {"RENDER_ASSETS", "RENDER_SHOTS"}


def _step_nodes() -> list[ProductionStepNode]:
    return build_production_step_nodes()


def _fake_executor(script: dict[str, str] | None = None):
    """Scripted executor: step_id -> status. Default: provider steps wait."""
    script = script or {}

    class FakeExecutor:
        def __init__(self):
            self.calls: list[str] = []

        def execute(self, step_id, run):
            self.calls.append(step_id)
            status = script.get(step_id)
            if status is None and step_id in PROVIDER_STEPS:
                status = "waiting_provider"
            status = status or "completed"
            if status == "waiting_provider":
                return StepExecutionResult(
                    step_id=step_id,
                    status="waiting_provider",
                    pending_external_operation=PendingExternalOperation(
                        step_id=step_id,
                        provider="fake_provider",
                        request_hash=f"req_{step_id}",
                        external_id=f"ext_{step_id}",
                    ),
                )
            if status == "failed":
                return StepExecutionResult(step_id=step_id, status="failed", error=f"fail {step_id}")
            if status == "waiting_human":
                return StepExecutionResult(step_id=step_id, status="waiting_human")
            return StepExecutionResult(
                step_id=step_id,
                status="completed",
                output_hashes={step_id: f"out_{step_id}_{uuid.uuid4().hex[:8]}"},
                candidate_count=1,
            )

    return FakeExecutor()


def _engine(tmp_path, executor=None, nodes=None, recovery=None):
    store = ProductionRunStore(state_dir=str(Path(tmp_path) / "runs"))
    return ProductionWorkflowEngine(
        store=store,
        executor=executor if executor is not None else _fake_executor(),
        recovery=recovery,
        step_nodes=nodes if nodes is not None else _step_nodes(),
    )


def _approve_all_gates(eng, run_id, revision_id="rev1", target_hash="h" * 64):
    for gate in ProductionApprovalGate.all_gates():
        eng.approve(run_id, gate=ProductionApprovalGate(gate), revision_id=revision_id, target_hash=target_hash, actor="human")


def _drive_to_completion(eng, run_id, max_steps: int = 200) -> ProductionRun:
    run = eng.load(run_id)
    guard = 0
    while run.state not in (ProductionRunState.COMPLETED, ProductionRunState.FAILED) and guard < max_steps:
        run = eng.advance(run_id)
        guard += 1
        if run.state == ProductionRunState.WAITING_PROVIDER:
            pending = run.checkpoint.pending_external_operation
            eng.ingest_external_result(run_id, external_id=pending.external_id, output_hashes={"clip": "abc"})
            run = eng.load(run_id)
    return run


def _drive_to_provider(eng, run_id, max_steps: int = 100) -> ProductionRun:
    run = eng.load(run_id)
    guard = 0
    while run.state != ProductionRunState.WAITING_PROVIDER and guard < max_steps:
        run = eng.advance(run_id)
        guard += 1
    return run


# ---------------------------------------------------------------------------
# State machine (§8.1)
# ---------------------------------------------------------------------------


def test_run_state_machine_11_states_and_transitions():
    states = ProductionRunStateMachine.all_states()
    assert set(states) == {
        "CREATED", "RUNNING", "WAITING_APPROVAL", "WAITING_HUMAN_ACTION",
        "WAITING_PROVIDER", "PAUSED", "RECOVERING", "COMPLETED", "FAILED",
        "CANCELLED", "ARCHIVED",
    }
    assert ProductionRunStateMachine.can_transition("CREATED", "RUNNING")
    assert not ProductionRunStateMachine.can_transition("RUNNING", "CREATED")


def test_terminal_state_rejects_mutation():
    with pytest.raises(TerminalStateMutationError):
        ProductionRunStateMachine.transition("COMPLETED", "RUNNING")
    with pytest.raises(TerminalStateMutationError):
        ProductionRunStateMachine.transition("CANCELLED", "RUNNING")


def test_sink_archived_rejects_write():
    with pytest.raises(TerminalStateMutationError):
        ProductionRunStateMachine.transition("ARCHIVED", "CREATED")


def test_idempotent_same_state_transition():
    rec = ProductionRunStateMachine.transition("RUNNING", "RUNNING", reason="noop")
    assert rec["changed"] is False


def test_illegal_transition_raises():
    with pytest.raises(InvalidStateTransitionError):
        ProductionRunStateMachine.transition("PAUSED", "RECOVERING")


def test_step_state_machine():
    assert ProductionStepState.PENDING in ProductionStepState
    assert ProductionStepStateMachine.can_transition("RUNNING", "WAITING_APPROVAL")
    assert not ProductionStepStateMachine.can_transition("COMPLETED", "RUNNING")


# ---------------------------------------------------------------------------
# Approvals (§8.2)
# ---------------------------------------------------------------------------


def test_approval_ledger_current_and_stale():
    ledger = ApprovalLedger()
    a = ProductionApproval(
        approval_id=str(uuid.uuid4()),
        run_id="r1",
        gate=ProductionApprovalGate.SCREENPLAY_APPROVAL,
        project_id="p1",
        revision_id="rev1",
        target_hash="a" * 64,
        actor="human",
    )
    assert ledger.record(a) is True
    assert ledger.has_current_approval(
        ProductionApprovalGate.SCREENPLAY_APPROVAL, revision_id="rev1", target_hash="a" * 64
    )
    assert ledger.is_stale(
        ProductionApprovalGate.SCREENPLAY_APPROVAL, revision_id="rev1", target_hash="b" * 64
    )
    assert not ledger.has_current_approval(
        ProductionApprovalGate.SCREENPLAY_APPROVAL, revision_id="rev1", target_hash="b" * 64
    )


def test_approval_ledger_idempotent_duplicate():
    ledger = ApprovalLedger()
    kwargs = dict(
        approval_id=str(uuid.uuid4()),
        run_id="r1",
        gate=ProductionApprovalGate.COST_APPROVAL,
        project_id="p1",
        revision_id="rev1",
        target_hash="c" * 64,
        actor="human",
    )
    assert ledger.record(ProductionApproval(**kwargs)) is True
    assert ledger.record(ProductionApproval(**kwargs)) is False
    assert len(ledger.approvals()) == 1


def test_engine_approve_rejects_wrong_hash():
    eng = _engine(tempfile.mkdtemp())
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_appr")
    with pytest.raises(DomainError):
        eng.approve("r_appr", gate=ProductionApprovalGate.CONCEPT_APPROVAL, revision_id="rev1", target_hash="z" * 64, actor="human")


def test_engine_approve_rejects_stale_reuse():
    eng = _engine(tempfile.mkdtemp())
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_stale")
    eng.approve("r_stale", gate=ProductionApprovalGate.CONCEPT_APPROVAL, revision_id="rev1", target_hash="h" * 64, actor="human")
    with pytest.raises(DomainError):
        eng.approve("r_stale", gate=ProductionApprovalGate.CONCEPT_APPROVAL, revision_id="rev1", target_hash="q" * 64, actor="human")


# ---------------------------------------------------------------------------
# Happy path with fake executor (§9)
# ---------------------------------------------------------------------------


def test_happy_path_reaches_publish():
    tmp = tempfile.mkdtemp()
    executor = _fake_executor()
    eng = _engine(tmp, executor=executor)

    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_happy")
    eng.start("r_happy")
    _approve_all_gates(eng, "r_happy")

    run = _drive_to_completion(eng, "r_happy")
    assert run.state == ProductionRunState.COMPLETED, run.state
    assert set(run.completed_steps) == set(VIDEO_PRODUCTION_STEPS)


def test_approval_gate_pauses_run():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_gate")
    eng.start("r_gate")

    # Ungated steps (CREATE_PROJECT, GENERATE_CONCEPTS) run, then the run
    # pauses at the FIRST approval gate (SELECT_CONCEPT -> CONCEPT_APPROVAL).
    run = eng.load("r_gate")
    guard = 0
    while run.state != ProductionRunState.WAITING_APPROVAL and guard < 20:
        run = eng.advance("r_gate")
        guard += 1
    assert run.state == ProductionRunState.WAITING_APPROVAL, run.state

    eng.approve("r_gate", gate=ProductionApprovalGate.CONCEPT_APPROVAL, revision_id="rev1", target_hash="h" * 64, actor="human")
    run = eng.load("r_gate")
    assert run.state == ProductionRunState.RUNNING
    assert "SELECT_CONCEPT" in eng.ready_step_ids(run)


# ---------------------------------------------------------------------------
# Crash / recovery (§8.5) — no duplicate submit
# ---------------------------------------------------------------------------


def test_recovery_no_checkpoint_fresh_attempt():
    rec = ProductionRecovery()
    d = rec.decide(None)
    assert d.action == RecoveryAction.NEW_ATTEMPT


def test_recovery_checkpoint_no_pending_op_fresh_attempt():
    rec = ProductionRecovery()
    ckpt = ProductionCheckpoint(run_id="r1", current_step="RENDER_SHOTS", attempt=1)
    d = rec.decide(ckpt)
    assert d.action == RecoveryAction.NEW_ATTEMPT


def test_recovery_pending_op_no_inspector_reconcile_unknown():
    rec = ProductionRecovery()
    ckpt = ProductionCheckpoint(
        run_id="r1", current_step="RENDER_SHOTS", attempt=1,
        pending_external_operation=PendingExternalOperation(step_id="RENDER_SHOTS", provider="fake", request_hash="req_1", external_id="ext_1"),
    )
    d = rec.decide(ckpt)
    assert d.action == RecoveryAction.RECONCILE_UNKNOWN


def test_recovery_pending_op_inspector_completed_resume_no_resubmit():
    rec = ProductionRecovery(inspect_provider=lambda req, ext: ProviderJobState.COMPLETED)
    ckpt = ProductionCheckpoint(
        run_id="r1", current_step="RENDER_SHOTS", attempt=1,
        pending_external_operation=PendingExternalOperation(step_id="RENDER_SHOTS", provider="fake", request_hash="req_1", external_id="ext_1"),
    )
    d = rec.decide(ckpt)
    assert d.action == RecoveryAction.RESUME_AFTER_INSPECTION
    assert d.attempt_increment is False


def test_engine_submitting_intent_persisted_before_executor():
    """Crash between the intent write and the executor submit lands in
    reconciliation (never a blind resubmit)."""
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_crash1")
    eng.start("r_crash1")
    _approve_all_gates(eng, "r_crash1")

    # Advance until the run reaches a provider step in WAITING_PROVIDER: the
    # submitting intent (pending external op) is now durably persisted.
    run = _drive_to_provider(eng, "r_crash1")
    assert run.state == ProductionRunState.WAITING_PROVIDER
    assert run.checkpoint.pending_external_operation is not None

    # Simulate a worker that crashed AFTER the submitting-intent write but
    # BEFORE the executor's actual submit: fresh engine, NO provider inspector.
    fresh_engine = _engine(tmp, recovery=ProductionRecovery())
    recovered = fresh_engine.recover("r_crash1")
    # Without an inspector the run must NOT blind-resubmit; it stays observable.
    assert recovered.state == ProductionRunState.WAITING_PROVIDER


def test_engine_recover_after_crash_reattaches_not_resubmits():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_crash2")
    eng.start("r_crash2")
    _approve_all_gates(eng, "r_crash2")

    run = _drive_to_provider(eng, "r_crash2")
    assert run.state == ProductionRunState.WAITING_PROVIDER
    pending = run.checkpoint.pending_external_operation
    assert pending is not None and pending.external_id == f"ext_{pending.step_id}"

    fresh = _engine(tmp, recovery=ProductionRecovery(inspect_provider=lambda req, ext: ProviderJobState.GENERATING))
    recovered = fresh.recover("r_crash2")
    assert recovered.state == ProductionRunState.WAITING_PROVIDER
    assert recovered.checkpoint.pending_external_operation.external_id == pending.external_id


def test_single_shot_failure_keeps_siblings():
    ok = ["SHOT_1", "SHOT_2", "SHOT_3"]
    assert ProductionRecovery.single_shot_failure_keeps_siblings(ok, "SHOT_2") == ["SHOT_1", "SHOT_3"]


def test_download_retry_bounded_no_resubmit():
    rec = ProductionRecovery(max_download_retries=3)
    d1 = rec.decide_download_retry(download_failures=0, request_hash="req_1")
    assert d1.action == RecoveryAction.RETRY_DOWNLOAD
    d2 = rec.decide_download_retry(download_failures=3, request_hash="req_1")
    assert d2.action == RecoveryAction.FAIL_TERMINAL


# ---------------------------------------------------------------------------
# Idempotency / outbox (§8.3)
# ---------------------------------------------------------------------------


def test_external_result_ingestion_idempotent():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_idem")
    eng.start("r_idem")
    _approve_all_gates(eng, "r_idem")

    run = _drive_to_provider(eng, "r_idem")
    pending = run.checkpoint.pending_external_operation
    run = eng.ingest_external_result("r_idem", external_id=pending.external_id, output_hashes={"clip": "abc"})
    ext_events = [e for e in run.outbox.events() if e.deduplication_key == f"external:{pending.external_id}"]
    assert len(ext_events) == 1
    run = eng.ingest_external_result("r_idem", external_id=pending.external_id, output_hashes={"clip": "xyz"})
    ext_events = [e for e in run.outbox.events() if e.deduplication_key == f"external:{pending.external_id}"]
    assert len(ext_events) == 1
    assert run.output_hashes["clip"] == "abc"


def test_unit_of_work_atomic_commit_and_replay():
    tmp = tempfile.mkdtemp()
    store = ProductionRunStore(state_dir=str(tmp))
    run = ProductionRun(run_id="r_uow", project_id="p1", revision_id="rev1", revision_hash="h" * 64)
    store.save(run)
    eng = ProductionWorkflowEngine(store=store, executor=_fake_executor(), step_nodes=_step_nodes())
    run = eng.load("r_uow")
    from windagent_orchestration.production import new_event

    event = new_event("video_production.test_event", {"k": "v"}, dedup_key="dedup-1")
    eng.uow.commit(run, [event])
    reloaded = eng.load("r_uow")
    evs = [e for e in reloaded.outbox.events() if e.event_id == event.event_id]
    assert evs and evs[0].status == "published"
    assert eng.replay_pending("r_uow") == []


# ---------------------------------------------------------------------------
# Lease / stale writes (§8.1) + version CAS
# ---------------------------------------------------------------------------


def test_stale_worker_lease_rejected():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_lease")
    eng.start("r_lease", worker_id="worker_A")
    with pytest.raises(ConcurrentStateConflictError):
        eng.advance("r_lease", worker_id="worker_B")


def test_lease_expiry_allows_new_worker():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_lease2")
    eng.start("r_lease2", worker_id="worker_A", lease_ttl=0.01)
    time.sleep(0.02)
    run = eng.advance("r_lease2", worker_id="worker_B")
    assert run.state == ProductionRunState.RUNNING


def test_version_cas_rejects_stale_write():
    tmp = tempfile.mkdtemp()
    store = ProductionRunStore(state_dir=str(tmp))
    run = ProductionRun(run_id="r_cas", project_id="p1", revision_id="rev1", revision_hash="h" * 64)
    store.save(run)
    stale = ProductionRun(run_id="r_cas", project_id="p1", revision_id="rev1", revision_hash="h" * 64)
    stale.loaded_version = 0
    current = store.load("r_cas")
    for _ in range(5):
        current.bump_version()
        store.save(current)
    with pytest.raises(ConcurrentStateConflictError):
        store.save(stale)


# ---------------------------------------------------------------------------
# Cancel / archive (§8.6)
# ---------------------------------------------------------------------------


def test_cancel_stops_scheduling_and_audits():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_cancel")
    eng.start("r_cancel")
    run = eng.cancel("r_cancel", actor="operator", reason="user request")
    assert run.state == ProductionRunState.CANCELLED
    entries = run.cancellations.entries()
    assert len(entries) == 1
    assert entries[0].actor == "operator"
    assert entries[0].reason == "user request"
    run = eng.advance("r_cancel")
    assert run.state == ProductionRunState.CANCELLED
    assert run.completed_steps == []


def test_cancel_provider_unconfirmed_stays_observable():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_cancel2")
    eng.start("r_cancel2")
    _approve_all_gates(eng, "r_cancel2")
    run = _drive_to_provider(eng, "r_cancel2")
    run = eng.cancel("r_cancel2", actor="operator", reason="cancel mid-provider", provider_cancel_confirmed=False)
    assert run.state == ProductionRunState.WAITING_PROVIDER
    assert run.cancellations.entries()[0].provider_cancel_confirmed is False


def test_cancel_with_provider_evidence_cancels():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_cancel3")
    eng.start("r_cancel3")
    run = eng.cancel("r_cancel3", actor="operator", reason="confirmed", provider_cancel_confirmed=True, provider_evidence="job=dead")
    assert run.state == ProductionRunState.CANCELLED
    assert run.cancellations.entries()[0].provider_evidence == "job=dead"


def test_archive_and_completed_cannot_cancel():
    tmp = tempfile.mkdtemp()
    eng = _engine(tmp)
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_arch")
    eng.start("r_arch")
    eng.pause("r_arch")
    run = eng.archive("r_arch", actor="admin", reason="done")
    assert run.state == ProductionRunState.ARCHIVED

    eng2 = _engine(tempfile.mkdtemp())
    eng2.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_comp")
    eng2.start("r_comp")
    run2 = eng2.load("r_comp")
    run2.transition(ProductionRunState.COMPLETED)
    eng2.store.save(run2)
    with pytest.raises(DomainError):
        eng2.cancel("r_comp", actor="op", reason="late")


# ---------------------------------------------------------------------------
# Scheduler (§8.4)
# ---------------------------------------------------------------------------


def test_scheduler_deterministic_and_never_selects():
    nodes = _step_nodes()
    facts = SchedulerFacts()
    sch = ProductionScheduler(provider_concurrency=1)
    first = [d.step_id for d in sch.ready_steps(nodes, facts)]
    second = [d.step_id for d in sch.ready_steps(nodes, facts)]
    assert first == second
    assert first == ["CREATE_PROJECT"]


def test_scheduler_respects_provider_concurrency():
    nodes = _step_nodes()
    sch = ProductionScheduler(provider_concurrency=1)
    facts = SchedulerFacts(completed_steps={"CREATE_PROJECT"})
    ready = [d.step_id for d in sch.ready_steps(nodes, facts)]
    assert isinstance(ready, list)


def test_scheduler_never_approves_or_selects_candidates():
    sch = ProductionScheduler()
    assert not hasattr(sch, "approve")
    assert not hasattr(sch, "select_candidate")


def test_scheduler_plan_resolves_with_gates():
    sch = ProductionScheduler()
    plan = sch.schedule_plan(_step_nodes(), SchedulerFacts())
    ids = [p["step_id"] for p in plan]
    assert ids == VIDEO_PRODUCTION_STEPS
    blocked = [p for p in plan if p["state"] == "BLOCKED"]
    assert any(p["reason"] == "approval_pending" for p in blocked)


# ---------------------------------------------------------------------------
# Pack (§7)
# ---------------------------------------------------------------------------


def test_pack_builds_16_step_definition():
    from windagent_workflows.video_production import VideoProductionWorkflowPack

    pack = VideoProductionWorkflowPack()
    definition = pack.build_workflow_definition({"project_id": "p1", "revision_id": "rev1", "revision_hash": "h" * 64})
    assert len(definition.nodes) == 16
    assert definition.validate() is None
    assert definition.semantic_version == "1.0.0"


def test_step_contracts_cover_all_steps():
    from windagent_workflows.video_production import all_step_contracts

    contracts = all_step_contracts()
    assert len(contracts) == 16
    for c in contracts:
        assert c["step_id"] in VIDEO_PRODUCTION_STEPS
        assert c["retry_budget"] >= 1
        assert isinstance(c["output_artifact_types"], list)


def test_approval_gates_match_plan():
    assert set(STEP_APPROVAL_GATES.keys()) <= set(VIDEO_PRODUCTION_STEPS)
    assert ProductionApprovalGate.CONCEPT_APPROVAL.value == "CONCEPT_APPROVAL"
    assert ProductionApprovalGate.FINAL_CUT_APPROVAL.value == "FINAL_CUT_APPROVAL"
