#!/usr/bin/env python3
"""
Phase 17 verification — VP17_DURABLE_WORKFLOW_VERIFIED (plan 05 §6–§10).

Verifies the durable production workflow
(`orchestration/windagent_orchestration/production/` +
`workflows/windagent_workflows/video_production/`) against the contracts in
`docs/video_production/durable_workflow/`:

  artifacts/video_production/phase_17/
  ├── workflow_definition_receipt.json   (16-step definition + pack DAG)
  ├── state_machine_receipt.json         (11 run states, transitions, terminal/sink, stale write)
  ├── approval_gate_receipt.json         (7 gates, revision/hash binding, staleness, idempotency)
  ├── checkpoint_outbox_receipt.json     (atomic commit, outbox replay, idempotent ingestion)
  ├── recovery_receipt.json              (failure matrix, no duplicate submit)
  ├── cancellation_receipt.json          (audit, provider honesty, scheduling stop)
  └── phase_verdict.json

Gate conditions (plan 05 §10):
  1. workflow recovers from durable state;
  2. approvals point at the correct revision/hash (stale approvals never reused);
  3. duplicate/stale writes cause no side effects (version CAS + lease + idempotency);
  4. failure matrix never creates a duplicate submit.

Supports --no-write / --verify-only.
"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_17"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_orchestration.production import (  # noqa: E402
    ApprovalLedger,
    PendingExternalOperation,
    ProductionApproval,
    ProductionApprovalGate,
    ProductionCancellation,
    ProductionCheckpoint,
    ProductionRecovery,
    ProductionRun,
    ProductionRunState,
    ProductionRunStateMachine,
    ProductionRunStore,
    ProductionScheduler,
    ProductionWorkflowEngine,
    ProviderJobState,
    RecoveryAction,
    SchedulerFacts,
    StepExecutionResult,
)
from windagent_workflows.video_production import (  # noqa: E402
    STEP_APPROVAL_GATES,
    VIDEO_PRODUCTION_STEPS,
    VideoProductionWorkflowPack,
    all_step_contracts,
    build_production_step_nodes,
)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _record(checks: list[dict], check: str, ok: bool, detail: str) -> None:
    checks.append({"check": check, "ok": bool(ok), "detail": detail})


PROVIDER_STEPS = {"RENDER_ASSETS", "RENDER_SHOTS"}


def _fake_executor(script: dict[str, str]):
    class FakeExecutor:
        def execute(self, step_id, run):
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
                output_hashes={step_id: f"out_{step_id}"},
                candidate_count=1,
            )

    return FakeExecutor()


def _run_to_completion(eng: ProductionWorkflowEngine, run_id: str, max_steps: int = 200) -> dict:
    """Drive a run to COMPLETED with a fake provider that completes instantly."""
    steps_driven = 0
    while steps_driven < max_steps:
        run = eng.advance(run_id)
        steps_driven += 1
        if run.state == ProductionRunState.WAITING_PROVIDER and run.checkpoint and run.checkpoint.pending_external_operation:
            pending = run.checkpoint.pending_external_operation
            eng.ingest_external_result(run_id, external_id=pending.external_id, output_hashes={"clip": "abc"})
        if run.state in (ProductionRunState.COMPLETED, ProductionRunState.FAILED):
            break
    return {
        "final_state": run.state.value,
        "completed_steps": sorted(run.completed_steps),
        "steps_driven": steps_driven,
    }


# ---------------------------------------------------------------------------
# Receipt 1 — workflow definition (plan 05 §7)
# ---------------------------------------------------------------------------


def verify_workflow_definition() -> dict:
    checks = []
    contracts = all_step_contracts()
    _record(checks, "16_steps_defined", len(contracts) == 16, f"contracts={len(contracts)}")
    expected = [
        "CREATE_PROJECT", "GENERATE_CONCEPTS", "SELECT_CONCEPT", "GENERATE_SCREENPLAY",
        "LOCK_SCREENPLAY", "BUILD_CHARACTER_AND_LOCATION_BIBLES", "APPROVE_REFERENCES",
        "CREATE_CINEMATIC_PLAN", "LOCK_SHOT_PLAN", "ESTIMATE_COST", "RENDER_ASSETS",
        "RENDER_SHOTS", "REVIEW_CANDIDATES", "POST_PRODUCTION", "FINAL_VERIFICATION",
        "PUBLISH",
    ]
    _record(checks, "steps_in_correct_order", [c["step_id"] for c in contracts] == expected, "order matches plan §7")

    every_contract_complete = all(
        c["step_id"] and c["version"] >= 1 and c["retry_budget"] >= 1
        and isinstance(c["output_artifact_types"], list) and c["output_artifact_types"]
        and c["expected_events"] for c in contracts
    )
    _record(checks, "every_step_contract_complete", every_contract_complete, "step_id/version/budget/artifacts/events present")

    gates_on_steps = set(STEP_APPROVAL_GATES.keys())
    _record(checks, "approval_gates_map_to_steps", gates_on_steps <= set(VIDEO_PRODUCTION_STEPS), f"gated={sorted(gates_on_steps)}")

    pack = VideoProductionWorkflowPack()
    definition = pack.build_workflow_definition({"project_id": "p1", "revision_id": "rev1", "revision_hash": "h" * 64})
    _record(checks, "pack_definition_16_nodes", len(definition.nodes) == 16, f"nodes={len(definition.nodes)}")
    _record(checks, "pack_definition_valid", definition.validate() is None, "immutable definition valid")
    _record(checks, "pack_semantic_version", definition.semantic_version == "1.0.0", definition.semantic_version)

    nodes = build_production_step_nodes()
    first = [d.step_id for d in ProductionScheduler(provider_concurrency=1).ready_steps(nodes, SchedulerFacts())]
    _record(checks, "scheduler_root_is_create_project", first == ["CREATE_PROJECT"], f"ready={first}")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP17_DURABLE_WORKFLOW_VERIFIED",
        "workstream": "workflow_definition",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "steps": [c["step_id"] for c in contracts],
    }


# ---------------------------------------------------------------------------
# Receipt 2 — state machine (plan 05 §8.1)
# ---------------------------------------------------------------------------


def verify_state_machine() -> dict:
    checks = []
    states = ProductionRunStateMachine.all_states()
    expected_states = {
        "CREATED", "RUNNING", "WAITING_APPROVAL", "WAITING_HUMAN_ACTION",
        "WAITING_PROVIDER", "PAUSED", "RECOVERING", "COMPLETED", "FAILED",
        "CANCELLED", "ARCHIVED",
    }
    _record(checks, "all_11_states", set(states) == expected_states, f"states={sorted(states)}")

    legal = ProductionRunStateMachine.can_transition("RUNNING", "WAITING_APPROVAL") \
        and ProductionRunStateMachine.can_transition("WAITING_APPROVAL", "RUNNING") \
        and ProductionRunStateMachine.can_transition("RUNNING", "WAITING_PROVIDER") \
        and ProductionRunStateMachine.can_transition("WAITING_PROVIDER", "RECOVERING")
    _record(checks, "key_transitions_legal", legal, "approval/provider/recovery edges")

    illegal = not ProductionRunStateMachine.can_transition("RUNNING", "CREATED") \
        and not ProductionRunStateMachine.can_transition("COMPLETED", "RUNNING")
    _record(checks, "illegal_transitions_rejected", illegal, "no reverse/terminal escape")

    terminal_blocked = False
    try:
        ProductionRunStateMachine.transition("COMPLETED", "RUNNING")
    except Exception:
        terminal_blocked = True
    _record(checks, "terminal_state_rejects_write", terminal_blocked, "COMPLETED -> RUNNING blocked")

    sink_blocked = False
    try:
        ProductionRunStateMachine.transition("ARCHIVED", "CREATED")
    except Exception:
        sink_blocked = True
    _record(checks, "archived_sink_rejects_write", sink_blocked, "ARCHIVED -> CREATED blocked")

    idem = ProductionRunStateMachine.transition("RUNNING", "RUNNING", reason="noop")
    _record(checks, "duplicate_transition_idempotent", idem["changed"] is False, "same-state no-op")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP17_DURABLE_WORKFLOW_VERIFIED",
        "workstream": "state_machine",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "states": sorted(states),
    }


# ---------------------------------------------------------------------------
# Receipt 3 — approval gates (plan 05 §8.2)
# ---------------------------------------------------------------------------


def verify_approval_gates() -> dict:
    checks = []
    expected_gates = {
        "CONCEPT_APPROVAL", "SCREENPLAY_APPROVAL", "CHARACTER_APPROVAL",
        "LOCATION_APPROVAL", "SHOT_PLAN_APPROVAL", "COST_APPROVAL", "FINAL_CUT_APPROVAL",
    }
    actual_gates = set(ProductionApprovalGate.all_gates())
    _record(checks, "all_7_gates", actual_gates == expected_gates, f"gates={sorted(actual_gates)}")

    ledger = ApprovalLedger()
    h64 = "a" * 64
    appr = ProductionApproval(
        approval_id=str(uuid.uuid4()),
        run_id="r1",
        gate=ProductionApprovalGate.SCREENPLAY_APPROVAL,
        project_id="p1",
        revision_id="rev1",
        target_hash=h64,
        actor="human",
    )
    _record(checks, "approval_recorded", ledger.record(appr) is True, "first record added")
    _record(checks, "approval_idempotent", ledger.record(appr) is False, "duplicate not re-added")
    _record(checks, "current_hash_satisfied", ledger.has_current_approval(
        ProductionApprovalGate.SCREENPLAY_APPROVAL, revision_id="rev1", target_hash=h64
    ), "exact hash satisfied")
    _record(checks, "stale_detected", ledger.is_stale(
        ProductionApprovalGate.SCREENPLAY_APPROVAL, revision_id="rev1", target_hash="b" * 64
    ), "different hash -> stale")
    _record(checks, "different_hash_not_satisfied", not ledger.has_current_approval(
        ProductionApprovalGate.SCREENPLAY_APPROVAL, revision_id="rev1", target_hash="b" * 64
    ), "stale approval never satisfies current target")

    # engine-level target binding
    tmp = tempfile.mkdtemp()
    eng = ProductionWorkflowEngine(
        store=ProductionRunStore(state_dir=str(tmp)),
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
    )
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash=h64, run_id="r_gate_v")
    wrong_hash_rejected = False
    try:
        eng.approve("r_gate_v", gate=ProductionApprovalGate.CONCEPT_APPROVAL, revision_id="rev1", target_hash="z" * 64, actor="human")
    except Exception:
        wrong_hash_rejected = True
    _record(checks, "engine_rejects_wrong_hash", wrong_hash_rejected, "approval must target current revision hash")

    eng.approve("r_gate_v", gate=ProductionApprovalGate.CONCEPT_APPROVAL, revision_id="rev1", target_hash=h64, actor="human")
    stale_reuse_rejected = False
    try:
        eng.approve("r_gate_v", gate=ProductionApprovalGate.CONCEPT_APPROVAL, revision_id="rev1", target_hash="q" * 64, actor="human")
    except Exception:
        stale_reuse_rejected = True
    _record(checks, "engine_rejects_stale_reuse", stale_reuse_rejected, "stale approval never reused")

    # run pauses at approval gate, resumes only after gate satisfied
    eng2 = ProductionWorkflowEngine(
        store=ProductionRunStore(state_dir=str(tempfile.mkdtemp())),
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
    )
    r2 = eng2.create_run(project_id="p1", revision_id="rev1", revision_hash=h64, run_id="r_gate2")
    eng2.start("r_gate2")
    # Ungated steps (CREATE_PROJECT, GENERATE_CONCEPTS) run, then the run pauses
    # at the FIRST approval gate (SELECT_CONCEPT -> CONCEPT_APPROVAL).
    guard = 0
    while guard < 20:
        eng2.advance("r_gate2")
        r2 = eng2.load("r_gate2")
        if r2.state == ProductionRunState.WAITING_APPROVAL:
            break
        guard += 1
    _record(checks, "run_pauses_at_gate", r2.state == ProductionRunState.WAITING_APPROVAL, f"state={r2.state.value}")
    r2 = eng2.approve("r_gate2", gate=ProductionApprovalGate.CONCEPT_APPROVAL, revision_id="rev1", target_hash=h64, actor="human")
    _record(checks, "run_resumes_after_gate", r2.state == ProductionRunState.RUNNING, f"state={r2.state.value}")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP17_DURABLE_WORKFLOW_VERIFIED",
        "workstream": "approval_gates",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Receipt 4 — checkpoint + outbox (plan 05 §8.3)
# ---------------------------------------------------------------------------


def verify_checkpoint_outbox() -> dict:
    checks = []
    from windagent_orchestration.production import new_event

    tmp = tempfile.mkdtemp()
    store = ProductionRunStore(state_dir=str(tmp))
    run = ProductionRun(run_id="r_uow", project_id="p1", revision_id="rev1", revision_hash="h" * 64)
    store.save(run)
    eng = ProductionWorkflowEngine(store=store, executor=_fake_executor({}), step_nodes=build_production_step_nodes())
    run = eng.load("r_uow")
    event = new_event("video_production.test", {"k": "v"}, dedup_key="dedup-1")
    eng.uow.commit(run, [event])
    reloaded = eng.load("r_uow")
    evs = [e for e in reloaded.outbox.events() if e.event_id == event.event_id]
    _record(checks, "event_committed_atomically", len(evs) == 1 and evs[0].status == "published", "state+event single write")
    _record(checks, "outbox_replay_no_pending", eng.replay_pending("r_uow") == [], "no stuck-pending events")

    # crash before commit -> nothing persisted
    tmp2 = tempfile.mkdtemp()
    store2 = ProductionRunStore(state_dir=str(tmp2))
    run2 = ProductionRun(run_id="r_uow2", project_id="p1", revision_id="rev1", revision_hash="h" * 64)
    store2.save(run2)
    run2b = store2.load("r_uow2")
    ghost = new_event("video_production.ghost", {"x": 1}, dedup_key="ghost-1")
    run2b.outbox.append(ghost)  # appended in memory but never committed
    _record(checks, "uncommitted_event_not_persisted", not any(
        e.event_id == ghost.event_id for e in store2.load("r_uow2").outbox.events()
    ), "crash before commit leaves no record")

    # idempotent external ingestion
    tmp3 = tempfile.mkdtemp()
    eng3 = ProductionWorkflowEngine(
        store=ProductionRunStore(state_dir=str(tmp3)),
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
    )
    r3 = eng3.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_ingest")
    eng3.start("r_ingest")
    for gate in ProductionApprovalGate.all_gates():
        eng3.approve("r_ingest", gate=ProductionApprovalGate(gate), revision_id="rev1", target_hash="h" * 64, actor="human")
    guard = 0
    while guard < 100:
        r3 = eng3.advance("r_ingest")
        if r3.state == ProductionRunState.WAITING_PROVIDER:
            break
        guard += 1
    pending = r3.checkpoint.pending_external_operation
    r3 = eng3.ingest_external_result("r_ingest", external_id=pending.external_id, output_hashes={"clip": "abc"})
    dup_events = [e for e in r3.outbox.events() if e.deduplication_key == f"external:{pending.external_id}"]
    _record(checks, "result_ingested_once", len(dup_events) == 1, "single ingestion event")
    r3 = eng3.ingest_external_result("r_ingest", external_id=pending.external_id, output_hashes={"clip": "xyz"})
    _record(checks, "duplicate_ingestion_no_side_effect", r3.output_hashes["clip"] == "abc", "duplicate delivery ignored")

    # SUBMITTING intent persisted before executor side effect
    engine_text = (ROOT / "orchestration" / "windagent_orchestration" / "production" / "engine.py").read_text(encoding="utf-8")
    intent_before_exec = engine_text.index("self.uow.commit(run, intent_events)") < engine_text.index("result = self.executor.execute(step_id, run)")
    _record(checks, "submit_intent_before_side_effect", intent_before_exec, "generation_submitting write precedes executor call")

    # version CAS rejects stale write
    tmp4 = tempfile.mkdtemp()
    store4 = ProductionRunStore(state_dir=str(tmp4))
    r4 = ProductionRun(run_id="r_cas", project_id="p1", revision_id="rev1", revision_hash="h" * 64)
    store4.save(r4)
    stale = ProductionRun(run_id="r_cas", project_id="p1", revision_id="rev1", revision_hash="h" * 64)
    stale.loaded_version = 0
    cur = store4.load("r_cas")
    for _ in range(3):
        cur.bump_version()
        store4.save(cur)
    cas_rejected = False
    try:
        store4.save(stale)
    except Exception:
        cas_rejected = True
    _record(checks, "version_cas_rejects_stale_write", cas_rejected, "stale writer version mismatch rejected")

    # lease stale write rejected
    tmp5 = tempfile.mkdtemp()
    eng5 = ProductionWorkflowEngine(
        store=ProductionRunStore(state_dir=str(tmp5)),
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
    )
    eng5.create_run(project_id="p1", revision_id="rev1", revision_hash="h" * 64, run_id="r_lease")
    eng5.start("r_lease", worker_id="worker_A")
    lease_rejected = False
    try:
        eng5.advance("r_lease", worker_id="worker_B")
    except Exception:
        lease_rejected = True
    _record(checks, "cross_worker_lease_rejected", lease_rejected, "worker_B cannot write worker_A's run")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP17_DURABLE_WORKFLOW_VERIFIED",
        "workstream": "checkpoint_outbox",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Receipt 5 — recovery failure matrix (plan 05 §8.5, §9)
# ---------------------------------------------------------------------------


def verify_recovery() -> dict:
    checks = []
    rec = ProductionRecovery()

    d_no_ckpt = rec.decide(None)
    _record(checks, "no_checkpoint_fresh_attempt", d_no_ckpt.action == RecoveryAction.NEW_ATTEMPT, d_no_ckpt.action.value)

    ckpt_no_op = ProductionCheckpoint(run_id="r1", current_step="RENDER_SHOTS", attempt=1)
    d_no_op = rec.decide(ckpt_no_op)
    _record(checks, "checkpoint_no_pending_fresh_attempt", d_no_op.action == RecoveryAction.NEW_ATTEMPT, d_no_op.action.value)

    ckpt_pending = ProductionCheckpoint(
        run_id="r1", current_step="RENDER_SHOTS", attempt=1,
        pending_external_operation=PendingExternalOperation(step_id="RENDER_SHOTS", provider="fake", request_hash="req_1", external_id="ext_1"),
    )
    d_no_inspector = rec.decide(ckpt_pending)
    _record(checks, "pending_no_inspector_reconcile_unknown", d_no_inspector.action == RecoveryAction.RECONCILE_UNKNOWN, "never blind resubmit")

    rec_completed = ProductionRecovery(inspect_provider=lambda req, ext: ProviderJobState.COMPLETED)
    d_completed = rec_completed.decide(ckpt_pending)
    _record(checks, "pending_inspector_completed_resume", d_completed.action == RecoveryAction.RESUME_AFTER_INSPECTION, "resume, do NOT resubmit")
    _record(checks, "completed_no_attempt_increment", d_completed.attempt_increment is False, "no new submit on completion")

    rec_generating = ProductionRecovery(inspect_provider=lambda req, ext: ProviderJobState.GENERATING)
    d_generating = rec_generating.decide(ckpt_pending)
    _record(checks, "pending_inspector_generating_reattach", d_generating.action == RecoveryAction.REATTACH_WAITING_PROVIDER, "reattach poll")

    rec_failed = ProductionRecovery(inspect_provider=lambda req, ext: ProviderJobState.FAILED)
    d_failed = rec_failed.decide(ckpt_pending)
    _record(checks, "pending_inspector_failed_new_attempt", d_failed.action == RecoveryAction.NEW_ATTEMPT, "bounded new attempt")

    rec_unknown = ProductionRecovery(inspect_provider=lambda req, ext: ProviderJobState.UNKNOWN)
    d_unknown = rec_unknown.decide(ckpt_pending)
    _record(checks, "pending_inspector_unknown_reconcile", d_unknown.action == RecoveryAction.RECONCILE_UNKNOWN, "stay observable")

    d_retry = rec.decide_download_retry(download_failures=0, request_hash="req_1")
    _record(checks, "download_retry_bounded", d_retry.action == RecoveryAction.RETRY_DOWNLOAD, "retry download, no resubmit")
    d_exhausted = rec.decide_download_retry(download_failures=3, request_hash="req_1")
    _record(checks, "download_retry_exhausted_terminal", d_exhausted.action == RecoveryAction.FAIL_TERMINAL, "fail after budget")

    siblings = ProductionRecovery.single_shot_failure_keeps_siblings(["S1", "S2", "S3"], "S2")
    _record(checks, "single_shot_failure_keeps_siblings", siblings == ["S1", "S3"], f"siblings={siblings}")

    d_rev_same = rec.decide_revision_change(expected_hash="h" * 64, actual_hash="h" * 64, dependent_artifacts=["clip1"])
    _record(checks, "revision_unchanged_keeps_dependents", d_rev_same.action == RecoveryAction.RESUME_AFTER_INSPECTION, "dependents valid")
    d_rev_changed = rec.decide_revision_change(expected_hash="h" * 64, actual_hash="j" * 64, dependent_artifacts=["clip1"])
    _record(checks, "revision_changed_stales_dependents", d_rev_changed.action == RecoveryAction.STALE_REVISION_BLOCK, "dependents stale")

    # END-TO-END: crash after submit -> fresh engine -> recover with inspector -> NO duplicate submit.
    h64 = "h" * 64
    tmp = tempfile.mkdtemp()
    store = ProductionRunStore(state_dir=str(tmp))
    eng = ProductionWorkflowEngine(
        store=store, executor=_fake_executor({}), step_nodes=build_production_step_nodes()
    )
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash=h64, run_id="r_crash_e2e")
    eng.start("r_crash_e2e")
    for gate in ProductionApprovalGate.all_gates():
        eng.approve("r_crash_e2e", gate=ProductionApprovalGate(gate), revision_id="rev1", target_hash=h64, actor="human")
    guard = 0
    while guard < 100:
        run = eng.advance("r_crash_e2e")
        if run.state == ProductionRunState.WAITING_PROVIDER:
            break
        guard += 1
    original_pending = run.checkpoint.pending_external_operation
    _record(checks, "crash_lands_in_waiting_provider", run.state == ProductionRunState.WAITING_PROVIDER, f"state={run.state.value}")
    _record(checks, "pending_op_has_external_id", bool(original_pending.external_id), original_pending.external_id)

    # Simulate worker restart: fresh engine + fresh recovery, provider still generating.
    fresh = ProductionWorkflowEngine(
        store=store,
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
        recovery=ProductionRecovery(inspect_provider=lambda req, ext: ProviderJobState.GENERATING),
    )
    recovered = fresh.recover("r_crash_e2e")
    still_pending = recovered.checkpoint.pending_external_operation
    _record(checks, "recovery_reattaches_same_external_id", still_pending is not None and still_pending.external_id == original_pending.external_id,
            f"external_id unchanged: {still_pending.external_id if still_pending else None}")
    _record(checks, "recovery_no_new_submit", recovered.state == ProductionRunState.WAITING_PROVIDER, "no blind resubmit; still waiting")

    # durable-state recovery: reload run from the SAME durable store in a NEW engine
    # proves the workflow recovers from durable state (gate condition 1).
    reloaded = fresh.load("r_crash_e2e")
    _record(checks, "run_recovers_from_durable_state", reloaded is not None and reloaded.state == ProductionRunState.WAITING_PROVIDER
            and reloaded.current_step == original_pending.step_id, f"state={reloaded.state.value} step={reloaded.current_step}")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP17_DURABLE_WORKFLOW_VERIFIED",
        "workstream": "recovery",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Receipt 6 — cancellation (plan 05 §8.6)
# ---------------------------------------------------------------------------


def verify_cancellation() -> dict:
    checks = []
    h64 = "h" * 64
    tmp = tempfile.mkdtemp()
    eng = ProductionWorkflowEngine(
        store=ProductionRunStore(state_dir=str(tmp)),
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
    )
    eng.create_run(project_id="p1", revision_id="rev1", revision_hash=h64, run_id="r_cancel")
    eng.start("r_cancel")
    run = eng.cancel("r_cancel", actor="operator", reason="user request")
    _record(checks, "cancel_sets_state", run.state == ProductionRunState.CANCELLED, run.state.value)
    entries = run.cancellations.entries()
    _record(checks, "cancel_audit_actor_reason", len(entries) == 1 and entries[0].actor == "operator" and entries[0].reason == "user request",
            f"actor={entries[0].actor if entries else None}")
    _record(checks, "cancel_audit_timestamp", len(entries) == 1 and entries[0].requested_at > 0, "timestamp recorded")

    # cancelled run schedules nothing and advance() does not crash
    before = len(run.completed_steps)
    run = eng.advance("r_cancel")
    _record(checks, "cancel_stops_new_scheduling", run.state == ProductionRunState.CANCELLED and len(run.completed_steps) == before,
            "no new steps after cancel")

    # provider honesty: unconfirmed cancel stays observable
    tmp2 = tempfile.mkdtemp()
    eng2 = ProductionWorkflowEngine(
        store=ProductionRunStore(state_dir=str(tmp2)),
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
    )
    eng2.create_run(project_id="p1", revision_id="rev1", revision_hash=h64, run_id="r_cancel2")
    eng2.start("r_cancel2")
    for gate in ProductionApprovalGate.all_gates():
        eng2.approve("r_cancel2", gate=ProductionApprovalGate(gate), revision_id="rev1", target_hash=h64, actor="human")
    guard = 0
    while guard < 100:
        run2 = eng2.advance("r_cancel2")
        if run2.state == ProductionRunState.WAITING_PROVIDER:
            break
        guard += 1
    run2 = eng2.cancel("r_cancel2", actor="operator", reason="mid-provider", provider_cancel_confirmed=False)
    _record(checks, "unconfirmed_cancel_stays_observable", run2.state == ProductionRunState.WAITING_PROVIDER,
            f"state={run2.state.value} (never claims provider cancelled)")
    _record(checks, "unconfirmed_cancel_audited", run2.cancellations.entries()[0].provider_cancel_confirmed is False,
            "provider_cancel_confirmed=False recorded")

    # confirmed+evidence cancels
    tmp3 = tempfile.mkdtemp()
    eng3 = ProductionWorkflowEngine(
        store=ProductionRunStore(state_dir=str(tmp3)),
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
    )
    eng3.create_run(project_id="p1", revision_id="rev1", revision_hash=h64, run_id="r_cancel3")
    eng3.start("r_cancel3")
    run3 = eng3.cancel("r_cancel3", actor="operator", reason="confirmed", provider_cancel_confirmed=True, provider_evidence="job=dead")
    _record(checks, "confirmed_cancel_with_evidence_cancels", run3.state == ProductionRunState.CANCELLED, run3.state.value)
    _record(checks, "confirmed_evidence_audited", run3.cancellations.entries()[0].provider_evidence == "job=dead", "evidence recorded")

    # artifacts keep provenance but are not auto-published after cancel
    _record(checks, "artifact_not_auto_published_on_cancel", ProductionCancellation.artifact_publish_allowed(cancel_requested=True) is False,
            "completed artifacts keep provenance, no auto-publish")

    # completed run cannot be cancelled
    tmp4 = tempfile.mkdtemp()
    eng4 = ProductionWorkflowEngine(
        store=ProductionRunStore(state_dir=str(tmp4)),
        executor=_fake_executor({}),
        step_nodes=build_production_step_nodes(),
    )
    eng4.create_run(project_id="p1", revision_id="rev1", revision_hash=h64, run_id="r_comp")
    eng4.start("r_comp")
    r4 = eng4.load("r_comp")
    r4.transition(ProductionRunState.COMPLETED)
    eng4.store.save(r4)
    completed_cancel_blocked = False
    try:
        eng4.cancel("r_comp", actor="op", reason="late")
    except Exception:
        completed_cancel_blocked = True
    _record(checks, "completed_run_cannot_cancel", completed_cancel_blocked, "archive instead")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP17_DURABLE_WORKFLOW_VERIFIED",
        "workstream": "cancellation",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(no_write: bool = False) -> int:
    print("Verifying Phase 17 — Durable Production Workflow...")
    wf = verify_workflow_definition()
    sm = verify_state_machine()
    ag = verify_approval_gates()
    co = verify_checkpoint_outbox()
    rec = verify_recovery()
    can = verify_cancellation()

    all_workstreams = [wf, sm, ag, co, rec, can]
    overall_pass = all(w["all_checks_pass"] for w in all_workstreams)
    overall_status = "PASSED" if overall_pass else "FAILED"

    gate_reasons = []
    if not overall_pass:
        for w in all_workstreams:
            if not w["all_checks_pass"]:
                for c in w["checks"]:
                    if not c["ok"]:
                        gate_reasons.append(f"[{w['workstream']}] {c['check']}: {c['detail']}")

    verdict = {
        "gate": "VP17_DURABLE_WORKFLOW_VERIFIED",
        "status": overall_status,
        "verified_at": utc_now_iso(),
        "workstreams": {
            "workflow_definition": wf["all_checks_pass"],
            "state_machine": sm["all_checks_pass"],
            "approval_gates": ag["all_checks_pass"],
            "checkpoint_outbox": co["all_checks_pass"],
            "recovery": rec["all_checks_pass"],
            "cancellation": can["all_checks_pass"],
        },
        "blocking_reasons": gate_reasons,
    }

    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)
        write_json(PHASE_DIR / "workflow_definition_receipt.json", wf)
        write_json(PHASE_DIR / "state_machine_receipt.json", sm)
        write_json(PHASE_DIR / "approval_gate_receipt.json", ag)
        write_json(PHASE_DIR / "checkpoint_outbox_receipt.json", co)
        write_json(PHASE_DIR / "recovery_receipt.json", rec)
        write_json(PHASE_DIR / "cancellation_receipt.json", can)
        write_json(PHASE_DIR / "phase_verdict.json", verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(overall_status, wf, sm, ag, co, rec, can),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_17 artifacts untouched.")

    print(f"Phase 17 verdict: {overall_status}")
    print(f"  workflow definition: {'PASS' if wf['all_checks_pass'] else 'FAIL'}")
    print(f"  state machine: {'PASS' if sm['all_checks_pass'] else 'FAIL'}")
    print(f"  approval gates: {'PASS' if ag['all_checks_pass'] else 'FAIL'}")
    print(f"  checkpoint/outbox: {'PASS' if co['all_checks_pass'] else 'FAIL'}")
    print(f"  recovery: {'PASS' if rec['all_checks_pass'] else 'FAIL'}")
    print(f"  cancellation: {'PASS' if can['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, wf, sm, ag, co, rec, can) -> str:
    return f"""# Phase 17 Report — Durable Production Workflow

- **Gate:** `VP17_DURABLE_WORKFLOW_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Workflow Definition

- Contract: `docs/video_production/durable_workflow/workflow_definition_contract.md`
- 16 steps: {len(wf.get('steps', []))}
- Checks: {wf.get('check_count')}; all pass: {wf.get('all_checks_pass')}

## State Machine

- Contract: `docs/video_production/durable_workflow/workflow_definition_contract.md`
- 11 run states; checks: {sm.get('check_count')}; all pass: {sm.get('all_checks_pass')}

## Approval Gates

- Contract: `docs/video_production/durable_workflow/approval_gate_contract.md`
- 7 gates bound to revision/hash; checks: {ag.get('check_count')}; all pass: {ag.get('all_checks_pass')}

## Checkpoint & Outbox

- Contract: `docs/video_production/durable_workflow/checkpoint_outbox_contract.md`
- Atomic commit + idempotent ingestion; checks: {co.get('check_count')}; all pass: {co.get('all_checks_pass')}

## Recovery

- Contract: `docs/video_production/durable_workflow/recovery_contract.md`
- Failure matrix (no duplicate submit); checks: {rec.get('check_count')}; all pass: {rec.get('all_checks_pass')}

## Cancellation

- Contract: `docs/video_production/durable_workflow/cancellation_contract.md`
- Audit + provider honesty; checks: {can.get('check_count')}; all pass: {can.get('all_checks_pass')}

## Evidence

- `workflow_definition_receipt.json`
- `state_machine_receipt.json`
- `approval_gate_receipt.json`
- `checkpoint_outbox_receipt.json`
- `recovery_receipt.json`
- `cancellation_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
