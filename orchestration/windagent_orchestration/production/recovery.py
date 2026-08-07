"""
Recovery engine for the Durable Production Workflow (plan 05 §8.5).

Design principles:

- recovery ALWAYS inspects durable state AND the provider before retrying —
  "file exists" or a leftover record is never the only decision;
- a crash after external submit lands in reconciliation: the same provider
  job is inspected, never blindly resubmitted;
- a single-shot failure does not lose successful siblings;
- prompt/reference revision change stales dependent approvals/artifacts;
- human-action and cancel/archive are typed recovery outcomes, not retries.

The recovery engine is provider-port driven: the caller injects an
``inspect_provider`` callback so the verifier can run offline with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from windagent_orchestration.production.states import ProductionRunState
from windagent_orchestration.production.checkpoint import (
    PendingExternalOperation,
    ProductionCheckpoint,
)


class ProviderJobState(str, Enum):
    """Observable provider-side job state (typed, never guessed)."""

    COMPLETED = "COMPLETED"
    GENERATING = "GENERATING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"  # provider cannot confirm the job exists


class RecoveryAction(str, Enum):
    """Typed outcome of a reconciliation decision."""

    RESUME_AFTER_INSPECTION = "RESUME_AFTER_INSPECTION"
    REATTACH_WAITING_PROVIDER = "REATTACH_WAITING_PROVIDER"
    RETRY_DOWNLOAD = "RETRY_DOWNLOAD"
    NEW_ATTEMPT = "NEW_ATTEMPT"
    STALE_REVISION_BLOCK = "STALE_REVISION_BLOCK"
    WAITING_HUMAN = "WAITING_HUMAN"
    FAIL_TERMINAL = "FAIL_TERMINAL"
    RECONCILE_UNKNOWN = "RECONCILE_UNKNOWN"


@dataclass
class RecoveryDecision:
    action: RecoveryAction
    reason: str = ""
    attempt_increment: bool = False
    next_state: Optional[ProductionRunState] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "attempt_increment": self.attempt_increment,
            "next_state": self.next_state.value if self.next_state else None,
            "details": self.details,
        }


InspectProviderFn = Callable[[str, str], ProviderJobState]  # (request_hash, external_id) -> state
InspectEngineJobFn = Callable[[str], ProviderJobState]  # (engine job_id) -> state


def _decision_for_job_state(state: ProviderJobState, external_id: str) -> RecoveryDecision:
    """Map one engine job's observed provider state to a typed recovery decision."""
    if state == ProviderJobState.COMPLETED:
        return RecoveryDecision(
            action=RecoveryAction.RESUME_AFTER_INSPECTION,
            reason="engine job completed — resume ingestion, do NOT resubmit",
            next_state=ProductionRunState.RUNNING,
            details={"engine_job": external_id},
        )
    if state == ProviderJobState.GENERATING:
        return RecoveryDecision(
            action=RecoveryAction.REATTACH_WAITING_PROVIDER,
            reason="engine job still generating — reattach poll, do NOT resubmit",
            next_state=ProductionRunState.WAITING_PROVIDER,
            details={"engine_job": external_id},
        )
    if state == ProviderJobState.FAILED:
        return RecoveryDecision(
            action=RecoveryAction.NEW_ATTEMPT,
            reason="engine job failed — bounded retry within budget, do NOT blind-resubmit siblings",
            attempt_increment=True,
            next_state=ProductionRunState.RUNNING,
            details={"engine_job": external_id},
        )
    return RecoveryDecision(
        action=RecoveryAction.RECONCILE_UNKNOWN,
        reason="engine job state unknown — pause for reconciliation, never resubmit",
        next_state=ProductionRunState.WAITING_PROVIDER,
        details={"engine_job": external_id},
    )


class ProductionRecovery:
    """Reconciliation policy — pure decision making, no side effects."""

    def __init__(
        self,
        *,
        max_download_retries: int = 3,
        inspect_provider: Optional[InspectProviderFn] = None,
        inspect_engine_job: Optional[InspectEngineJobFn] = None,
    ) -> None:
        self.max_download_retries = max_download_retries
        self._inspect_provider = inspect_provider
        self._inspect_engine_job = inspect_engine_job

    def decide(self, checkpoint: Optional[ProductionCheckpoint]) -> RecoveryDecision:
        """Reconcile a run given its last durable checkpoint.

        A missing checkpoint means the worker died BEFORE any durable write:
        nothing was submitted, so a fresh attempt is safe.
        """
        if checkpoint is None:
            return RecoveryDecision(
                action=RecoveryAction.NEW_ATTEMPT,
                reason="no checkpoint; worker died before any durable write — safe fresh attempt",
                attempt_increment=False,
            )

        pending = checkpoint.pending_external_operation
        if pending is None:
            # Worker died AFTER checkpoint but BEFORE an external submit:
            # the step was not submitted, so a new attempt is safe and
            # deterministic (same input hash -> same request).
            return RecoveryDecision(
                action=RecoveryAction.NEW_ATTEMPT,
                reason="checkpoint present but no pending external operation — step not yet submitted",
                attempt_increment=True,
                next_state=ProductionRunState.RUNNING,
            )

        # A pending external operation exists: the provider may or may not
        # have accepted the job. ALWAYS inspect the provider before deciding.
        if self._inspect_provider is None:
            return RecoveryDecision(
                action=RecoveryAction.RECONCILE_UNKNOWN,
                reason="pending external operation and no provider inspector available — never blind resubmit",
                next_state=ProductionRunState.WAITING_PROVIDER,
            )

        provider_state = self._inspect_provider(pending.request_hash, pending.external_id)

        if provider_state == ProviderJobState.COMPLETED:
            return RecoveryDecision(
                action=RecoveryAction.RESUME_AFTER_INSPECTION,
                reason="provider reports job completed — resume ingestion, do NOT resubmit",
                next_state=ProductionRunState.RUNNING,
                details={"external_id": pending.external_id},
            )
        if provider_state == ProviderJobState.GENERATING:
            return RecoveryDecision(
                action=RecoveryAction.REATTACH_WAITING_PROVIDER,
                reason="provider reports job still generating — reattach poll, do NOT resubmit",
                next_state=ProductionRunState.WAITING_PROVIDER,
                details={"external_id": pending.external_id},
            )
        if provider_state == ProviderJobState.FAILED:
            return RecoveryDecision(
                action=RecoveryAction.NEW_ATTEMPT,
                reason="provider reports job failed — bounded new attempt within retry budget",
                attempt_increment=True,
                next_state=ProductionRunState.RUNNING,
                details={"external_id": pending.external_id},
            )
        return RecoveryDecision(
            action=RecoveryAction.RECONCILE_UNKNOWN,
            reason="provider cannot confirm job state — pause for reconciliation, never resubmit",
            next_state=ProductionRunState.WAITING_PROVIDER,
            details={"external_id": pending.external_id},
        )

    def decide_all_engine_jobs(self, pending: PendingExternalOperation) -> List[RecoveryDecision]:
        """Reconcile EVERY engine job in a scene/shot batch (VP3D).

        A single RENDER step submits one engine job per scene/shot unit, all
        recorded in ``pending.job_ids``. Recovery must inspect the FULL batch,
        not just the primary ``external_id`` — otherwise a later job still
        generating (or failed) is invisible after a worker crash.

        Returns one decision per engine job, in batch order. Falls back to the
        primary job when no per-engine inspector is injected.
        """
        if not pending.job_ids:
            return [self.decide_from_op(pending)]
        if self._inspect_engine_job is None:
            # No per-engine inspector: reconcile the primary anchor and
            # surface the batch visibility into it (all jobs listed), but
            # never claim siblings are resolved without evidence.
            base = self.decide_from_op(pending)
            base.details["batch_job_ids"] = list(pending.job_ids)
            return [base]

        decisions: List[RecoveryDecision] = []
        for job_id in pending.job_ids:
            state = self._inspect_engine_job(job_id)
            decisions.append(_decision_for_job_state(state, job_id))
        return decisions

    def decide_from_op(self, pending: PendingExternalOperation) -> RecoveryDecision:
        """Single-op reconciliation reusing the primary ``external_id`` anchor."""
        fake = ProductionCheckpoint(
            run_id="",
            current_step=pending.step_id,
            pending_external_operation=pending,
        )
        return self.decide(fake)

    def decide_download_retry(
        self,
        *,
        download_failures: int,
        request_hash: str,
    ) -> RecoveryDecision:
        """Candidate download failure is retried WITHOUT resubmitting."""
        if download_failures < self.max_download_retries:
            return RecoveryDecision(
                action=RecoveryAction.RETRY_DOWNLOAD,
                reason="candidate download failed — retry download within budget, do NOT resubmit",
                attempt_increment=False,
                details={"request_hash": request_hash, "download_failures": download_failures},
            )
        return RecoveryDecision(
            action=RecoveryAction.FAIL_TERMINAL,
            reason="download retry budget exhausted",
            attempt_increment=True,
            next_state=ProductionRunState.FAILED,
            details={"request_hash": request_hash, "download_failures": download_failures},
        )

    def decide_revision_change(
        self,
        *,
        expected_hash: str,
        actual_hash: str,
        dependent_artifacts: List[str],
    ) -> RecoveryDecision:
        """A reference/prompt/revision change stales dependent work."""
        if expected_hash == actual_hash:
            return RecoveryDecision(
                action=RecoveryAction.RESUME_AFTER_INSPECTION,
                reason="revision hash unchanged — dependents remain valid",
            )
        return RecoveryDecision(
            action=RecoveryAction.STALE_REVISION_BLOCK,
            reason="revision hash changed — dependent artifacts/approvals are stale",
            next_state=ProductionRunState.WAITING_APPROVAL,
            details={"expected_hash": expected_hash, "actual_hash": actual_hash, "stale": dependent_artifacts},
        )

    @staticmethod
    def single_shot_failure_keeps_siblings(successful: List[str], failed_shot: str) -> List[str]:
        """Single-shot failure never loses successful siblings."""
        return [s for s in successful if s != failed_shot]


__all__ = [
    "ProviderJobState",
    "RecoveryAction",
    "RecoveryDecision",
    "InspectProviderFn",
    "InspectEngineJobFn",
    "ProductionRecovery",
]
