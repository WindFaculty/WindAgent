"""
Generation budget policy for the Durable Production Workflow (plan 05 §19.4,
gate VP19_COST_AND_QUOTA_CONTROL_VERIFIED).

The policy is the SINGLE gate every provider submit path must pass:

- no submit when the credit state or estimate is UNKNOWN (fail closed);
- reserve BEFORE submit; reconcile against the observed result after;
- retry only while the retry budget remains;
- candidate count is bounded;
- quality / high-cost mode requires explicit approval bound to the estimate
  hash (when the plan or the cost catalog changes, the old approval is
  stale and must NOT be reused — §19.2);
- daily / monthly / project / run limits are enforced BEFORE the provider
  call;
- a PoC run never submits many parallel generations (concurrency bound).

The policy never mutates the ledger itself — it only DECIDES. Reserve and
reconcile are separate explicit calls so the caller (engine/outbox) can
commit them atomically with the run state (plan 05 §8.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError

from windagent_orchestration.production.estimator import (
    ESTIMATE_STATUS_KNOWN,
    CostEstimate,
    CreditEstimator,
)
from windagent_orchestration.production.quota_ledger import QuotaLedger

BUDGET_POLICY_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class RetryBudget:
    """Bounded retry allowance for a request/run (§19.4)."""

    max_retries: int
    used_retries: int = 0

    def remaining(self) -> int:
        return max(0, self.max_retries - self.used_retries)

    def can_retry(self) -> bool:
        return self.used_retries < self.max_retries

    def consume(self) -> "RetryBudget":
        return RetryBudget(max_retries=self.max_retries, used_retries=self.used_retries + 1)


@dataclass(frozen=True)
class DailyLimit:
    """Daily credit ceiling for a project scope (§19.4)."""

    max_credits: int
    used_credits: int = 0

    def remaining(self) -> int:
        return max(0, self.max_credits - self.used_credits)

    def can_cover(self, amount: int) -> bool:
        return self.used_credits + amount <= self.max_credits


@dataclass(frozen=True)
class MonthlyLimit:
    """Monthly credit ceiling for a project scope (§19.4)."""

    max_credits: int
    used_credits: int = 0

    def remaining(self) -> int:
        return max(0, self.max_credits - self.used_credits)

    def can_cover(self, amount: int) -> bool:
        return self.used_credits + amount <= self.max_credits


@dataclass(frozen=True)
class ProjectLimit:
    """Per-project total credit ceiling (§19.4)."""

    max_credits: int
    used_credits: int = 0

    def remaining(self) -> int:
        return max(0, self.max_credits - self.used_credits)

    def can_cover(self, amount: int) -> bool:
        return self.used_credits + amount <= self.max_credits


class SubmitVerdict(str, object):
    """Verdicts returned by the budget policy gate (§19.4)."""

    ALLOWED = "ALLOWED"
    BLOCKED_UNKNOWN_ESTIMATE = "BLOCKED_UNKNOWN_ESTIMATE"
    BLOCKED_UNKNOWN_CREDIT_STATE = "BLOCKED_UNKNOWN_CREDIT_STATE"
    BLOCKED_APPROVAL_REQUIRED = "BLOCKED_APPROVAL_REQUIRED"
    BLOCKED_STALE_APPROVAL = "BLOCKED_STALE_APPROVAL"
    BLOCKED_RETRY_BUDGET = "BLOCKED_RETRY_BUDGET"
    BLOCKED_CANDIDATE_LIMIT = "BLOCKED_CANDIDATE_LIMIT"
    BLOCKED_DAILY_LIMIT = "BLOCKED_DAILY_LIMIT"
    BLOCKED_MONTHLY_LIMIT = "BLOCKED_MONTHLY_LIMIT"
    BLOCKED_PROJECT_LIMIT = "BLOCKED_PROJECT_LIMIT"
    BLOCKED_RUN_LIMIT = "BLOCKED_RUN_LIMIT"
    BLOCKED_INSUFFICIENT_CREDITS = "BLOCKED_INSUFFICIENT_CREDITS"
    BLOCKED_PARALLEL_SUBMIT = "BLOCKED_PARALLEL_SUBMIT"


@dataclass(frozen=True)
class SubmitDecision:
    """Outcome of the budget gate for one provider submit (§19.4)."""

    verdict: str
    reason: str = ""
    estimate_hash: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict == SubmitVerdict.ALLOWED


@dataclass
class BudgetApproval:
    """Explicit approval bound to an estimate hash (§19.4)."""

    estimate_hash: str
    actor: str
    reason: str = ""
    approved_at: float = 0.0


class GenerationBudgetPolicy:
    """Deterministic gate deciding whether a provider submit may proceed.

    Every submit path in the production workflow must pass `can_submit`.
    The policy reads (never mutates) the quota ledger and the estimator, and
    returns a `SubmitDecision` — reserve/reconcile are explicit separate
    calls so they can be committed atomically by the caller.
    """

    def __init__(
        self,
        *,
        estimator: CreditEstimator,
        ledger: QuotaLedger,
        approval_threshold: int = 100,
        candidate_limit: int = 4,
        max_parallel_submits: int = 1,
        run_limit_credits: Optional[int] = None,
    ) -> None:
        if candidate_limit < 1:
            raise ValidationError(
                "candidate_limit must be >= 1", code="WINDAGENT_ERR_VALIDATION"
            )
        if max_parallel_submits < 1:
            raise ValidationError(
                "max_parallel_submits must be >= 1", code="WINDAGENT_ERR_VALIDATION"
            )
        self.estimator = estimator
        self.ledger = ledger
        self.approval_threshold = approval_threshold
        self.candidate_limit = candidate_limit
        self.max_parallel_submits = max_parallel_submits
        self.run_limit_credits = run_limit_credits
        self._approvals: List[BudgetApproval] = []

    # -- approvals (bound to estimate hash) -----------------------------------
    def approve(
        self,
        *,
        estimate: CostEstimate,
        actor: str,
        reason: str = "",
    ) -> BudgetApproval:
        """Record an explicit approval for a concrete estimate hash.

        The approval is bound to the estimate hash; a different plan/catalog
        produces a different hash and this approval is stale for it (§19.2).
        """
        approval = BudgetApproval(
            estimate_hash=estimate.estimate_hash(),
            actor=actor,
            reason=reason,
        )
        # idempotent: same hash + actor -> keep the first
        if not any(
            a.estimate_hash == approval.estimate_hash and a.actor == actor
            for a in self._approvals
        ):
            self._approvals.append(approval)
        return approval

    def has_approval(self, estimate: CostEstimate) -> bool:
        h = estimate.estimate_hash()
        return any(a.estimate_hash == h for a in self._approvals)

    # -- gate -----------------------------------------------------------------
    def can_submit(
        self,
        *,
        estimate: CostEstimate,
        retry_budget: Optional[RetryBudget] = None,
        is_retry: bool = False,
        daily: Optional[DailyLimit] = None,
        monthly: Optional[MonthlyLimit] = None,
        project: Optional[ProjectLimit] = None,
        in_flight_submits: int = 0,
        credits_available: Optional[int] = None,
        plan_hash: str,
    ) -> SubmitDecision:
        """Decide whether one provider submit may proceed (§19.4).

        Order of checks (fail closed first):
        1. UNKNOWN estimate            -> blocked (never guess);
        2. unknown credit state        -> blocked;
        3. stale estimate/approval     -> blocked (re-estimate + re-approve);
        4. approval required & missing -> blocked;
        5. retry budget exhausted      -> blocked;
        6. candidate limit             -> blocked;
        7. daily / monthly / project / run limits -> blocked;
        8. parallel submit bound       -> blocked;
        9. credits available           -> blocked when insufficient.
        """
        eh = estimate.estimate_hash()

        if estimate.status != ESTIMATE_STATUS_KNOWN:
            return SubmitDecision(
                SubmitVerdict.BLOCKED_UNKNOWN_ESTIMATE,
                reason=f"estimate unknown: {'; '.join(estimate.unknown_reasons)}",
                estimate_hash=eh,
            )
        if credits_available is None:
            return SubmitDecision(
                SubmitVerdict.BLOCKED_UNKNOWN_CREDIT_STATE,
                reason="credit state unknown (no balance provided)",
                estimate_hash=eh,
            )
        if plan_hash != estimate.plan_hash:
            return SubmitDecision(
                SubmitVerdict.BLOCKED_STALE_APPROVAL,
                reason="estimate bound to a different plan hash",
                estimate_hash=eh,
            )
        if self.estimator.catalog.signature() != estimate.catalog_signature:
            return SubmitDecision(
                SubmitVerdict.BLOCKED_STALE_APPROVAL,
                reason="estimate stale: cost catalog changed",
                estimate_hash=eh,
            )
        if estimate.requires_approval and not self.has_approval(estimate):
            return SubmitDecision(
                SubmitVerdict.BLOCKED_APPROVAL_REQUIRED,
                reason=f"estimate requires approval (hash {eh[:12]}...)",
                estimate_hash=eh,
            )
        if is_retry:
            if retry_budget is None or not retry_budget.can_retry():
                return SubmitDecision(
                    SubmitVerdict.BLOCKED_RETRY_BUDGET,
                    reason="retry budget exhausted",
                    estimate_hash=eh,
                )
        if estimate.candidate_count > self.candidate_limit:
            return SubmitDecision(
                SubmitVerdict.BLOCKED_CANDIDATE_LIMIT,
                reason=f"candidate_count {estimate.candidate_count} > limit {self.candidate_limit}",
                estimate_hash=eh,
            )
        if daily is not None and not daily.can_cover(estimate.maximum_credits):
            return SubmitDecision(
                SubmitVerdict.BLOCKED_DAILY_LIMIT,
                reason=f"daily limit exceeded (used {daily.used_credits} + {estimate.maximum_credits} > {daily.max_credits})",
                estimate_hash=eh,
            )
        if monthly is not None and not monthly.can_cover(estimate.maximum_credits):
            return SubmitDecision(
                SubmitVerdict.BLOCKED_MONTHLY_LIMIT,
                reason=f"monthly limit exceeded (used {monthly.used_credits} + {estimate.maximum_credits} > {monthly.max_credits})",
                estimate_hash=eh,
            )
        if project is not None and not project.can_cover(estimate.maximum_credits):
            return SubmitDecision(
                SubmitVerdict.BLOCKED_PROJECT_LIMIT,
                reason=f"project limit exceeded (used {project.used_credits} + {estimate.maximum_credits} > {project.max_credits})",
                estimate_hash=eh,
            )
        if self.run_limit_credits is not None and estimate.maximum_credits > self.run_limit_credits:
            return SubmitDecision(
                SubmitVerdict.BLOCKED_RUN_LIMIT,
                reason=f"run limit exceeded ({estimate.maximum_credits} > {self.run_limit_credits})",
                estimate_hash=eh,
            )
        if in_flight_submits >= self.max_parallel_submits:
            return SubmitDecision(
                SubmitVerdict.BLOCKED_PARALLEL_SUBMIT,
                reason=f"parallel submit bound reached ({in_flight_submits} in flight)",
                estimate_hash=eh,
            )
        if credits_available < estimate.maximum_credits:
            return SubmitDecision(
                SubmitVerdict.BLOCKED_INSUFFICIENT_CREDITS,
                reason=f"insufficient credits ({credits_available} < {estimate.maximum_credits})",
                estimate_hash=eh,
            )
        return SubmitDecision(SubmitVerdict.ALLOWED, reason="budget gate passed", estimate_hash=eh)

    # -- explicit reserve / reconcile (called by the engine, atomically) ------
    def reserve(self, *, run_id: str, request_hash: str, estimate: CostEstimate, dedup_key: str = "") -> str:
        """Reserve credits BEFORE the submit; returns the dedup key.

        The caller commits this reservation atomically with the run state so
        a crash after reserve but before submit reconciles to the reserved
        entry (never a blind resubmit — plan 05 §8.3/§8.5).
        """
        key = dedup_key or f"reserve:{run_id}:{request_hash}"
        self.ledger.reserve(
            run_id=run_id,
            request_hash=request_hash,
            amount=estimate.maximum_credits,
            estimate_hash=estimate.estimate_hash(),
            dedup_key=key,
        )
        return key

    def reconcile(
        self,
        *,
        run_id: str,
        request_hash: str,
        observed: Optional[int],
        external_id: str = "",
        source: str = "provider_billing",
        dedup_key: str = "",
    ) -> str:
        """Record the observed debit (or UNKNOWN) after a provider result.

        Idempotent by dedup_key: replaying the result never double-debits
        (gate VP19 — ledger no double count through replay).
        """
        key = dedup_key or f"observe:{run_id}:{request_hash}:{external_id or 'none'}"
        if observed is None:
            self.ledger.unknown(run_id=run_id, request_hash=request_hash, dedup_key=key)
            return key
        self.ledger.observe_debit(
            run_id=run_id,
            request_hash=request_hash,
            amount=observed,
            source=source,
            external_id=external_id,
            dedup_key=key,
        )
        return key

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": BUDGET_POLICY_SCHEMA_VERSION,
            "approval_threshold": self.approval_threshold,
            "candidate_limit": self.candidate_limit,
            "max_parallel_submits": self.max_parallel_submits,
            "run_limit_credits": self.run_limit_credits,
            "approvals": [
                {"estimate_hash": a.estimate_hash, "actor": a.actor, "reason": a.reason, "approved_at": a.approved_at}
                for a in self._approvals
            ],
        }


__all__ = [
    "BUDGET_POLICY_SCHEMA_VERSION",
    "RetryBudget",
    "DailyLimit",
    "MonthlyLimit",
    "ProjectLimit",
    "SubmitVerdict",
    "SubmitDecision",
    "BudgetApproval",
    "GenerationBudgetPolicy",
]
