"""
Durable production workflow engine (plan 05 §6-§10, gate VP17_DURABLE_WORKFLOW_VERIFIED).

Implements an end-to-end durable workflow over canonical primitives:

- `ProductionRun` — aggregate: state, current step, attempt, input/output
  hashes, approval ledger, checkpoint, outbox journal, cancellation audit;
- `ProductionRunStore` — durable file-backed store with optimistic-concurrency
  compare-and-swap on save (stale writes rejected by version + lease);
- `ProductionUnitOfWork` — commits run state + checkpoint + outbox events
  ATOMICALLY (single atomic write): an event is never published before the
  state commit lands;
- `ProductionWorkflowEngine` — orchestrator: pause/resume at approval gates,
  waiting human/provider, recovery, cancel/archive, stale-write rejection via
  optimistic version checks and worker leases.

Fail-closed properties enforced here (gate VP17):

- approval gates are satisfied ONLY by an APPROVED approval for the exact
  current revision/hash — a stale approval never re-opens a gate (§8.2);
- for external-cost steps the SUBMITTING intent is persisted BEFORE the
  provider side effect, so a crash between submit and result ingestion lands
  in reconciliation — never a blind resubmit (§8.5, §8.3);
- the engine NEVER selects a candidate and NEVER approves anything itself
  (§8.4); cancel stops new scheduling and never claims provider-side
  cancellation without evidence (§8.6).

DEPRECATED AUTHORITY (studio.contract/v0.1, authority rule 5): this engine may
serve existing VP3D production paths only. Plan A fences it: ``step_nodes``
referencing the Studio namespace (``studio.`` / ``studio.story.*``) are rejected
at construction. New Story runs belong to ``OrchestratorService``.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from windagent_core.errors.exceptions import (
    ConcurrentStateConflictError,
    DomainError,
)

from windagent_orchestration.production.approvals import (
    ApprovalLedger,
    ProductionApproval,
    ProductionApprovalGate,
)
from windagent_orchestration.production.cancellation import (
    CancellationAuditLog,
    ProductionCancellation,
)
from windagent_orchestration.production.checkpoint import (
    PendingExternalOperation,
    ProductionCheckpoint,
    WorkerLease,
)
from windagent_orchestration.production.outbox import (
    OutboxEvent,
    OutboxJournal,
    new_event,
)
from windagent_orchestration.production.recovery import (
    ProductionRecovery,
    RecoveryAction,
    RecoveryDecision,
)
from windagent_orchestration.production.scheduler import (
    ProductionScheduler,
    ProductionStepNode,
    SchedulerFacts,
    by_id_step,
)
from windagent_orchestration.production.states import (
    ProductionRunState,
    ProductionRunStateMachine,
    parse_run_state,
)

ClockFn = Callable[[], float]

PRODUCTION_WORKFLOW_SCHEMA_VERSION = "1.0.0"


@dataclass
class StepExecutionResult:
    """Typed result of executing one step (injected executor)."""

    step_id: str
    status: str  # completed | failed | waiting_provider | waiting_human
    output_hashes: Dict[str, str] = field(default_factory=dict)
    pending_external_operation: Optional[PendingExternalOperation] = None
    error: str = ""
    candidate_count: int = 0


class StepExecutorPort(Protocol):
    """Port the engine calls to execute a step (injected at composition).

    Contract: for external-cost steps the executor MUST return
    ``status == "waiting_provider"`` with a populated
    ``pending_external_operation`` — the engine persists the SUBMITTING intent
    BEFORE invoking this method, so returning without a pending op after a
    real submit is a contract violation (the engine treats a missing pending
    op as "not submitted" during recovery).
    """

    def execute(self, step_id: str, run: "ProductionRun") -> StepExecutionResult: ...


@dataclass
class ProductionRun:
    """Durable aggregate for one production workflow run (plan 05 §7-§8)."""

    run_id: str
    project_id: str
    revision_id: str
    revision_hash: str
    state: ProductionRunState = ProductionRunState.CREATED
    current_step: str = ""
    attempt: int = 0
    version: int = 0  # optimistic concurrency guard (CAS on save)
    loaded_version: int = -1  # snapshot of on-disk version at load (not serialized)
    lease: Optional[WorkerLease] = None
    input_hashes: Dict[str, str] = field(default_factory=dict)
    output_hashes: Dict[str, str] = field(default_factory=dict)
    completed_steps: List[str] = field(default_factory=list)
    step_attempts: Dict[str, int] = field(default_factory=dict)
    approvals: ApprovalLedger = field(default_factory=ApprovalLedger)
    checkpoint: Optional[ProductionCheckpoint] = None
    outbox: OutboxJournal = field(default_factory=OutboxJournal)
    cancellations: CancellationAuditLog = field(default_factory=CancellationAuditLog)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # -- state helpers ---------------------------------------------------------
    def transition(self, target: ProductionRunState, reason: Optional[str] = None) -> Dict[str, Any]:
        record = ProductionRunStateMachine.transition(self.state, target, reason=reason)
        if record["changed"]:
            self.state = parse_run_state(target)
            self.version += 1
            self.updated_at = time.time()
        return record

    def bump_version(self) -> None:
        self.version += 1
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": PRODUCTION_WORKFLOW_SCHEMA_VERSION,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "revision_hash": self.revision_hash,
            "state": self.state.value,
            "current_step": self.current_step,
            "attempt": self.attempt,
            "version": self.version,
            "lease": self.lease.to_dict() if self.lease else None,
            "input_hashes": dict(self.input_hashes),
            "output_hashes": dict(self.output_hashes),
            "completed_steps": list(self.completed_steps),
            "step_attempts": dict(self.step_attempts),
            "approvals": self.approvals.to_dict(),
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "outbox": self.outbox.to_dict(),
            "cancellations": self.cancellations.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProductionRun":
        raw_checkpoint = data.get("checkpoint")
        return cls(
            run_id=data["run_id"],
            project_id=data["project_id"],
            revision_id=data["revision_id"],
            revision_hash=data.get("revision_hash", ""),
            state=parse_run_state(data.get("state", "CREATED")),
            current_step=data.get("current_step", ""),
            attempt=data.get("attempt", 0),
            version=data.get("version", 0),
            lease=WorkerLease.from_dict(data.get("lease")),
            input_hashes=data.get("input_hashes", {}),
            output_hashes=data.get("output_hashes", {}),
            completed_steps=list(data.get("completed_steps", [])),
            step_attempts=data.get("step_attempts", {}),
            approvals=ApprovalLedger.from_dict(data.get("approvals", {})),
            checkpoint=(
                ProductionCheckpoint.from_dict(raw_checkpoint) if raw_checkpoint else None
            ),
            outbox=OutboxJournal.from_dict(data.get("outbox", {})),
            cancellations=CancellationAuditLog.from_dict(data.get("cancellations", {})),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )


class ProductionRunStore:
    """Durable file-backed store for ProductionRun with CAS stale-write guard."""

    def __init__(self, state_dir: str, clock: Optional[ClockFn] = None) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock or time.time

    def _path(self, run_id: str) -> Path:
        return self.state_dir / f"run_{run_id}.json"

    def save(self, run: ProductionRun) -> None:
        """Atomic temp+rename write with compare-and-swap version guard.

        A stale write (on-disk version differs from the version snapshot taken
        at load) is rejected with ConcurrentStateConflictError — duplicate or
        stale worker writes never cause side effects (gate VP17).
        """
        existing = self.load(run.run_id)
        if run.loaded_version >= 0:
            expected = run.loaded_version
            actual = existing.version if existing is not None else -1
            if actual != expected:
                raise ConcurrentStateConflictError(
                    f"Stale write for run {run.run_id}: on-disk version {actual}, "
                    f"expected {expected}"
                )
        path = self._path(run.run_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(tmp, path)
        run.loaded_version = run.version

    def load(self, run_id: str) -> Optional[ProductionRun]:
        path = self._path(run_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        run = ProductionRun.from_dict(data)
        run.loaded_version = run.version
        return run

    def exists(self, run_id: str) -> bool:
        return self._path(run_id).exists()

    def list_run_ids(self) -> List[str]:
        return sorted(p.name[4:-5] for p in self.state_dir.glob("run_*.json"))


class ProductionUnitOfWork:
    """Atomic commit of run state + checkpoint + outbox events (plan 05 §8.3).

    State, checkpoint and events are persisted in ONE atomic write; an event
    is only marked published after that write succeeded. A crash before the
    write leaves NOTHING persisted — the journal on disk never contains an
    unpublished event, so there is no stuck-pending window to replay.
    """

    def __init__(self, store: ProductionRunStore) -> None:
        self._store = store

    def commit(self, run: ProductionRun, events: List[OutboxEvent]) -> None:
        for event in events:
            run.outbox.append(event)
            run.outbox.mark_published(event.event_id)
        run.bump_version()
        self._store.save(run)  # atomic write: state + published events land together


class ProductionWorkflowEngine:
    """Orchestrator for the durable production workflow (plan 05 §8).

    DEPRECATED for Story: this is a legacy VP3D authority. It rejects
    ``ProductionStepNode`` entries whose step_id uses the Studio namespace.
    """

    def __init__(
        self,
        *,
        store: ProductionRunStore,
        scheduler: Optional[ProductionScheduler] = None,
        recovery: Optional[ProductionRecovery] = None,
        executor: Optional[StepExecutorPort] = None,
        step_nodes: Optional[List[ProductionStepNode]] = None,
        clock: Optional[ClockFn] = None,
    ) -> None:
        nodes = list(step_nodes or [])
        # STORY-FENCE-START
        # Fence (authority rule 5): this line names the Studio namespace only
        # to reject Story steps in this legacy engine. Do not add Story logic.
        for node in nodes:
            if str(node.step_id).startswith(("studio.", "studio.story.")):
                raise DomainError(
                    message=(
                        f"Story step '{node.step_id}' rejected by legacy "
                        "ProductionWorkflowEngine (authority rule 5); Story "
                        "runs belong to OrchestratorService."
                    ),
                    code="WINDAGENT_ERR_STORY_LEGACY_ENGINE",
                )
        # STORY-FENCE-END
        self.store = store
        self.scheduler = scheduler or ProductionScheduler(provider_concurrency=1)
        self.recovery = recovery or ProductionRecovery()
        self.executor = executor
        self.step_nodes = nodes
        self._clock = clock or time.time
        self.uow = ProductionUnitOfWork(store)

    # -- run lifecycle ---------------------------------------------------------
    def create_run(
        self,
        *,
        project_id: str,
        revision_id: str,
        revision_hash: str,
        run_id: Optional[str] = None,
        input_hashes: Optional[Dict[str, str]] = None,
    ) -> ProductionRun:
        if self.store.exists(run_id or ""):
            raise DomainError(
                message=f"Run {run_id} already exists",
                code="WINDAGENT_ERR_RUN_EXISTS",
            )
        run = ProductionRun(
            run_id=run_id or f"run_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            revision_id=revision_id,
            revision_hash=revision_hash,
            input_hashes=dict(input_hashes or {}),
        )
        self.store.save(run)
        return run

    def load(self, run_id: str) -> ProductionRun:
        run = self.store.load(run_id)
        if run is None:
            raise DomainError(
                message=f"Production run {run_id} not found",
                code="WINDAGENT_ERR_RUN_NOT_FOUND",
            )
        return run

    # -- transitions -----------------------------------------------------------
    def start(self, run_id: str, *, worker_id: str = "worker_default", lease_ttl: float = 120.0) -> ProductionRun:
        run = self.load(run_id)
        self._assert_lease_ok(run, worker_id, lease_ttl)
        record = run.transition(ProductionRunState.RUNNING, reason="run started")
        self._emit(run, "video_production.run_started", {"run_id": run.run_id, **record})
        self.store.save(run)
        return run

    def pause(self, run_id: str, *, reason: str = "operator pause") -> ProductionRun:
        run = self.load(run_id)
        run.transition(ProductionRunState.PAUSED, reason=reason)
        self.store.save(run)
        return run

    def resume(self, run_id: str, *, reason: str = "operator resume") -> ProductionRun:
        run = self.load(run_id)
        run.transition(ProductionRunState.RUNNING, reason=reason)
        self.store.save(run)
        return run

    def approve(
        self,
        run_id: str,
        *,
        gate: ProductionApprovalGate,
        revision_id: str,
        target_hash: str,
        actor: str,
        reason: str = "",
    ) -> ProductionRun:
        """Record an approval bound to the CURRENT revision/hash (plan 05 §8.2).

        Only an approval for the exact current revision hash is accepted; a
        stale approval (for a different target) is never reused and a fresh
        approval for a wrong hash is rejected. The run resumes only when the
        gate it was waiting on becomes satisfied.
        """
        run = self.load(run_id)

        if target_hash != run.revision_hash:
            raise DomainError(
                message=(
                    "Approval target_hash does not match current revision hash; "
                    "approvals must target the CURRENT revision"
                ),
                code="WINDAGENT_ERR_APPROVAL_TARGET",
                details={"gate": gate.value, "requested_hash": target_hash, "current_hash": run.revision_hash},
            )
        if str(revision_id) != str(run.revision_id):
            raise DomainError(
                message="Approval revision_id does not match current run revision",
                code="WINDAGENT_ERR_APPROVAL_TARGET",
                details={"gate": gate.value, "requested_revision": str(revision_id), "current_revision": run.revision_id},
            )

        # The ledger's stale guard: an approval for this gate already exists
        # for a DIFFERENT hash — the caller must approve the current target.
        if run.approvals.is_stale(gate, revision_id=revision_id, target_hash=target_hash):
            raise DomainError(
                message=(
                    f"Approval for gate {gate.value} exists for a different "
                    f"target hash; re-approval for the current hash required"
                ),
                code="WINDAGENT_ERR_STALE_APPROVAL",
                details={"gate": gate.value, "requested_hash": target_hash},
            )

        approval = ProductionApproval(
            approval_id=str(uuid.uuid4()),
            run_id=run.run_id,
            gate=gate,
            project_id=run.project_id,
            revision_id=revision_id,
            target_hash=target_hash,
            actor=actor,
            reason=reason,
        )
        added = run.approvals.record(approval)
        if added:
            self._emit(run, "video_production.approval_recorded", {"gate": gate.value, "target_hash": target_hash, "actor": actor})
        # Resume ONLY when the gate this run is waiting on is now satisfied.
        if run.state == ProductionRunState.WAITING_APPROVAL and not self._pending_gates(run):
            run.transition(ProductionRunState.RUNNING, reason="all pending gates satisfied")
        self.store.save(run)
        return run

    def cancel(
        self,
        run_id: str,
        *,
        actor: str,
        reason: str,
        provider_cancel_confirmed: bool = False,
        provider_evidence: str = "",
    ) -> ProductionRun:
        """Cancel a run with full audit (plan 05 §8.6)."""
        run = self.load(run_id)
        ProductionCancellation.ensure_cancellable(run.state)

        entry = ProductionCancellation.request(
            run_id=run_id, actor=actor, reason=reason, audit_log=run.cancellations, clock=self._clock
        )
        entry.provider_cancel_confirmed = provider_cancel_confirmed
        entry.provider_evidence = provider_evidence

        if provider_cancel_confirmed and provider_evidence:
            run.transition(ProductionRunState.CANCELLED, reason=f"cancelled by {actor}: {reason}")
        else:
            # Only an ACTIVE provider operation (pending external op) stays
            # observable for cancel/reconcile; everything else cancels cleanly
            # (plan 05 §8.6 — never claim the external job stopped without
            # evidence, but a run with no provider op has nothing to reconcile).
            has_pending_op = (
                run.checkpoint is not None
                and run.checkpoint.pending_external_operation is not None
            )
            if has_pending_op or run.state == ProductionRunState.WAITING_PROVIDER:
                run.transition(ProductionRunState.WAITING_PROVIDER, reason="provider cancel unconfirmed")
            else:
                run.transition(ProductionRunState.CANCELLED, reason=f"cancelled by {actor}: {reason}")

        self._emit(run, "video_production.run_cancelled", {"actor": actor, "reason": reason})
        self.store.save(run)
        return run

    def archive(self, run_id: str, *, actor: str = "system", reason: str = "archive") -> ProductionRun:
        run = self.load(run_id)
        run.transition(ProductionRunState.ARCHIVED, reason=f"archived by {actor}: {reason}")
        self.store.save(run)
        return run

    def fail(self, run_id: str, *, reason: str = "run failed") -> ProductionRun:
        run = self.load(run_id)
        run.transition(ProductionRunState.FAILED, reason=reason)
        self._emit(run, "video_production.run_failed", {"reason": reason})
        self.store.save(run)
        return run

    # -- step execution --------------------------------------------------------
    def ready_step_ids(self, run: ProductionRun) -> List[str]:
        """Ready step ids under CURRENT-hash approval gating (plan 05 §8.2).

        Only approvals that match the run's current revision_id + revision_hash
        satisfy a gate; stale approvals never re-open a gate.
        """
        approved_gates = {
            node.approval_gate
            for node in self.step_nodes
            if node.approval_gate is not None
            and run.approvals.has_current_approval(
                node.approval_gate,
                revision_id=run.revision_id,
                target_hash=run.revision_hash,
            )
        }
        facts = SchedulerFacts(
            completed_steps=set(run.completed_steps),
            in_flight_steps=set(),
            step_attempts=dict(run.step_attempts),
            approved_gates=approved_gates,
            revision_hash=run.revision_hash,
            cancelled=bool(run.cancellations.entries()),
        )
        decisions = self.scheduler.ready_steps(self.step_nodes, facts)
        return [d.step_id for d in decisions]

    def advance(self, run_id: str, *, worker_id: str = "worker_default", lease_ttl: float = 120.0) -> ProductionRun:
        """Execute the next ready step (if any) with atomic checkpoint commit.

        A cancelled run never schedules new steps. If no step is ready because
        approval gates are pending, the run moves to WAITING_APPROVAL; when all
        steps are complete it moves to COMPLETED.
        """
        run = self.load(run_id)
        self._assert_lease_ok(run, worker_id, lease_ttl)

        if ProductionRunStateMachine.is_terminal(run.state):
            return run
        if run.cancellations.entries():
            # Cancel stops new scheduling; no gating transitions are attempted.
            return run
        if run.state == ProductionRunState.WAITING_PROVIDER:
            # A step is in flight with the provider — never re-schedule it
            # (would duplicate the submit). Resume only via ingestion.
            return run

        ready = self.ready_step_ids(run)
        if not ready:
            pending_gates = self._pending_gates(run)
            if pending_gates:
                run.transition(ProductionRunState.WAITING_APPROVAL, reason=f"waiting gates: {sorted(g.value for g in pending_gates)}")
                self.store.save(run)
                return run
            if not run.completed_steps and self.step_nodes:
                run.transition(ProductionRunState.WAITING_HUMAN_ACTION, reason="no ready step and no approvals pending")
                self.store.save(run)
                return run
            run.transition(ProductionRunState.COMPLETED, reason="all steps completed")
            self._emit(run, "video_production.run_completed", {"run_id": run.run_id})
            self.store.save(run)
            return run

        step_id = ready[0]
        return self._execute_step(run, step_id, worker_id)

    # -- recovery --------------------------------------------------------------
    def recover(self, run_id: str, *, worker_id: str = "worker_default") -> ProductionRun:
        """Reconcile a run from its durable checkpoint (plan 05 §8.5).

        VP3D: a RENDER step submits ONE engine job per scene/shot unit and the
        checkpoint carries the FULL batch in ``pending_external_operation``.
        Recovery therefore reconciles EVERY engine job of the batch — not just
        the first — via ``ProductionRecovery.decide_batch`` (fail closed on any
        unknown/failed sibling; never a blind resubmit).
        """
        run = self.load(run_id)
        pending = (
            run.checkpoint.pending_external_operation if run.checkpoint else None
        )
        if pending is not None and len(pending.job_ids) > 1:
            decision = self.recovery.decide_batch(pending)
        else:
            decision = self.recovery.decide(run.checkpoint)
        return self._apply_recovery(run, decision, worker_id)

    def recover_download(
        self,
        run_id: str,
        *,
        download_failures: int,
        request_hash: str,
        worker_id: str = "worker_default",
    ) -> ProductionRun:
        run = self.load(run_id)
        decision = self.recovery.decide_download_retry(download_failures=download_failures, request_hash=request_hash)
        return self._apply_recovery(run, decision, worker_id)

    def ingest_external_result(
        self,
        run_id: str,
        *,
        external_id: str,
        output_hashes: Dict[str, str],
        event_id: Optional[str] = None,
    ) -> ProductionRun:
        """Idempotent ingestion of an external provider result (plan 05 §8.3).

        VP3D batch semantics: when the pending operation carries multiple
        engine jobs (``job_ids``), ONE ingested result never completes the
        step — the pending op stays visible and the run stays WAITING_PROVIDER
        until EVERY engine job of the batch has been ingested (tracked via
        ``run.output_hashes``). Only then is the step completed and the
        pending op cleared.
        """
        run = self.load(run_id)
        if not run.outbox.ingest_external_result(external_id):
            return run  # duplicate delivery — no side effects
        event = new_event(
            "video_production.external_result_ingested",
            {"external_id": external_id, "output_hashes": output_hashes},
            dedup_key=f"external:{external_id}",
        )
        run.outbox.append(event)
        run.output_hashes.update(output_hashes)

        pending = (
            run.checkpoint.pending_external_operation if run.checkpoint else None
        )
        batch_remaining: List[str] = []
        if pending is not None and len(pending.job_ids) > 1:
            # A result only counts toward the batch when it names one of the
            # batch's engine jobs; anything else is recorded but never allows
            # the step to complete (fail closed).
            ingested = set(run.output_hashes)
            batch_remaining = [
                job_id for job_id in pending.job_ids if job_id not in ingested
            ]

        if run.checkpoint:
            step_id = run.checkpoint.current_step
            run.checkpoint.output_hashes = dict(run.output_hashes)
            if not batch_remaining:
                if step_id and step_id not in run.completed_steps:
                    run.completed_steps.append(step_id)
                run.checkpoint.pending_external_operation = None
        if run.state in (ProductionRunState.WAITING_PROVIDER, ProductionRunState.RECOVERING):
            if batch_remaining:
                # Still waiting on sibling engine jobs — do NOT leave the
                # provider state or reschedule the step.
                run.bump_version()
            else:
                run.transition(ProductionRunState.RUNNING, reason="external result ingested")
        else:
            run.bump_version()  # mutating run without a transition — bump anyway
        run.outbox.mark_published(event.event_id)
        self.store.save(run)
        return run

    def replay_pending(self, run_id: str) -> List[str]:
        """Publish any events still pending after a crash (outbox replay, §9).

        With the single-write UnitOfWork no event can be left pending by
        design; this is a defensive replay for records written by older or
        external writers and is used by the gate's outbox-replay test.
        """
        run = self.load(run_id)
        republished: List[str] = []
        for event in run.outbox.pending():
            if run.outbox.mark_published(event.event_id):
                republished.append(event.event_id)
        if republished:
            self.store.save(run)
        return republished

    # -- internals -------------------------------------------------------------
    def _request_hash(self, run: ProductionRun, step_id: str) -> str:
        seed = f"{run.revision_hash}:{step_id}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def _execute_step(self, run: ProductionRun, step_id: str, worker_id: str) -> ProductionRun:
        run.current_step = step_id
        run.step_attempts[step_id] = run.step_attempts.get(step_id, 0) + 1
        run.attempt += 1
        run.bump_version()

        node = by_id_step(self.step_nodes, step_id)
        external = node.external_cost

        # (A) Persist the SUBMITTING intent BEFORE any provider side effect
        #     (plan 05 §8.3/§8.5): if the process dies between this write and
        #     the executor's submit, durable state shows a pending external op
        #     and recovery lands in reconciliation — never a blind resubmit.
        if external:
            intent_op = PendingExternalOperation(
                step_id=step_id,
                provider="",
                request_hash=self._request_hash(run, step_id),
                external_id="",
            )
            run.checkpoint = ProductionCheckpoint(
                run_id=run.run_id,
                current_step=step_id,
                attempt=run.step_attempts[step_id],
                input_revision_hash=run.revision_hash,
                input_hashes=dict(run.input_hashes),
                output_hashes=dict(run.output_hashes),
                lease=run.lease,
                pending_external_operation=intent_op,
            )
            run.transition(ProductionRunState.WAITING_PROVIDER, reason=f"step {step_id} submit intent persisted")
            intent_events = [
                new_event(
                    "video_production.generation_submitting",
                    {"step_id": step_id, "request_hash": intent_op.request_hash},
                )
            ]
            self.uow.commit(run, intent_events)

        if self.executor is None:
            raise DomainError(
                message="No StepExecutorPort injected — cannot execute steps",
                code="WINDAGENT_ERR_EXECUTOR_MISSING",
            )

        result = self.executor.execute(step_id, run)

        # If an external-cost step's intent write moved the run to
        # WAITING_PROVIDER but the executor resolved the step synchronously
        # (completed/failed/human without a pending op), move back to RUNNING
        # first — otherwise the run would be stuck in WAITING_PROVIDER or the
        # transition to WAITING_HUMAN_ACTION would be illegal.
        if run.state == ProductionRunState.WAITING_PROVIDER and result.status != "waiting_provider":
            run.transition(ProductionRunState.RUNNING, reason=f"step {step_id} resolved synchronously")

        # Refresh checkpoint with the actual outcome.
        if run.checkpoint is None:
            run.checkpoint = ProductionCheckpoint(
                run_id=run.run_id,
                current_step=step_id,
                attempt=run.step_attempts[step_id],
                input_revision_hash=run.revision_hash,
                input_hashes=dict(run.input_hashes),
                output_hashes=dict(run.output_hashes),
                lease=run.lease,
            )

        if result.status == "waiting_provider" and result.pending_external_operation:
            run.checkpoint.pending_external_operation = result.pending_external_operation
            if run.state != ProductionRunState.WAITING_PROVIDER:
                run.transition(ProductionRunState.WAITING_PROVIDER, reason=f"step {step_id} submitted to provider")
            events = [
                new_event(
                    "video_production.generation_submitted",
                    {
                        "step_id": step_id,
                        "request_hash": result.pending_external_operation.request_hash,
                        "external_id": result.pending_external_operation.external_id,
                    },
                )
            ]
            self.uow.commit(run, events)
            return run

        if result.status == "waiting_human":
            run.checkpoint.pending_external_operation = None
            run.transition(ProductionRunState.WAITING_HUMAN_ACTION, reason=f"step {step_id} requires human action")
            events = [new_event("video_production.human_action_required", {"step_id": step_id})]
            self.uow.commit(run, events)
            return run

        if result.status == "failed":
            run.checkpoint.pending_external_operation = None
            if run.step_attempts[step_id] >= self._max_attempts(step_id):
                run.transition(ProductionRunState.FAILED, reason=f"step {step_id} exhausted retries")
                events = [new_event("video_production.step_failed_terminal", {"step_id": step_id, "error": result.error})]
                self.uow.commit(run, events)
                return run
            events = [new_event("video_production.step_failed_retryable", {"step_id": step_id, "error": result.error})]
            self.uow.commit(run, events)
            return run

        # completed
        run.output_hashes.update(result.output_hashes)
        if step_id not in run.completed_steps:
            run.completed_steps.append(step_id)
        run.checkpoint.output_hashes = dict(run.output_hashes)
        run.checkpoint.pending_external_operation = None
        events = [
            new_event(
                "video_production.step_completed",
                {"step_id": step_id, "output_hashes": result.output_hashes, "candidate_count": result.candidate_count},
            )
        ]
        self.uow.commit(run, events)
        return run

    def _apply_recovery(self, run: ProductionRun, decision: RecoveryDecision, worker_id: str) -> ProductionRun:
        action = decision.action
        if action == RecoveryAction.NEW_ATTEMPT:
            if decision.attempt_increment:
                run.attempt += 1
            run.transition(ProductionRunState.RUNNING, reason=decision.reason)
        elif action == RecoveryAction.RESUME_AFTER_INSPECTION:
            run.transition(ProductionRunState.RUNNING, reason=decision.reason)
        elif action == RecoveryAction.REATTACH_WAITING_PROVIDER:
            run.transition(ProductionRunState.WAITING_PROVIDER, reason=decision.reason)
        elif action == RecoveryAction.RETRY_DOWNLOAD:
            run.transition(ProductionRunState.RUNNING, reason=decision.reason)
        elif action == RecoveryAction.STALE_REVISION_BLOCK:
            run.transition(ProductionRunState.WAITING_APPROVAL, reason=decision.reason)
        elif action == RecoveryAction.WAITING_HUMAN:
            run.transition(ProductionRunState.WAITING_HUMAN_ACTION, reason=decision.reason)
        elif action == RecoveryAction.FAIL_TERMINAL:
            run.transition(ProductionRunState.FAILED, reason=decision.reason)
        elif action == RecoveryAction.RECONCILE_UNKNOWN:
            if run.state != ProductionRunState.WAITING_PROVIDER:
                run.transition(ProductionRunState.WAITING_PROVIDER, reason=decision.reason)
        else:  # pragma: no cover - defensive
            run.transition(ProductionRunState.RECOVERING, reason="unknown recovery action")

        self._emit(run, "video_production.run_recovered", {"action": action.value, "reason": decision.reason})
        self.store.save(run)
        return run

    def _pending_gates(self, run: ProductionRun) -> List[ProductionApprovalGate]:
        """Gates that block the NEXT schedulable step (dependencies complete).

        Only the gate of the next step(s) whose dependencies are all satisfied
        counts as pending; future gates on steps whose dependencies are not yet
        complete are NOT pending yet (plan 05 §8.2 pause-at-each-gate).
        """
        completed = set(run.completed_steps)
        pending: List[ProductionApprovalGate] = []
        for node in self.step_nodes:
            if node.approval_gate is None or node.step_id in completed:
                continue
            deps_ok = all(d in completed for d in node.dependencies)
            if not deps_ok:
                continue  # not the next schedulable step — gate not yet pending
            if not run.approvals.has_current_approval(
                node.approval_gate,
                revision_id=run.revision_id,
                target_hash=run.revision_hash,
            ):
                if node.approval_gate not in pending:
                    pending.append(node.approval_gate)
        return sorted(pending, key=lambda g: g.value)

    def _max_attempts(self, step_id: str) -> int:
        for node in self.step_nodes:
            if node.step_id == step_id:
                return node.max_attempts
        return 3

    def _assert_lease_ok(self, run: ProductionRun, worker_id: str, ttl: float) -> None:
        now = self._clock()
        if run.lease is not None and not run.lease.is_expired(now=now) and run.lease.worker_id != worker_id:
            raise ConcurrentStateConflictError(
                f"Run {run.run_id} is leased by worker {run.lease.worker_id}; stale write rejected"
            )
        run.lease = WorkerLease(
            worker_id=worker_id,
            expires_at=now + ttl,
        )

    def _emit(self, run: ProductionRun, event_type: str, payload: Dict[str, Any]) -> None:
        event = new_event(event_type, {"run_id": run.run_id, **payload})
        run.outbox.append(event)
        # Mark published immediately: every _emit call site persists via
        # store.save() right after, so the state + event land in one write
        # (same semantics as ProductionUnitOfWork.commit) — no stuck-pending
        # journal records from the lifecycle paths.
        run.outbox.mark_published(event.event_id)


__all__ = [
    "PRODUCTION_WORKFLOW_SCHEMA_VERSION",
    "StepExecutionResult",
    "StepExecutorPort",
    "ProductionRun",
    "ProductionRunStore",
    "ProductionUnitOfWork",
    "ProductionWorkflowEngine",
]
