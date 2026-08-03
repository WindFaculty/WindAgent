#!/usr/bin/env python3
"""
Phase 19 verification — VP19_COST_AND_QUOTA_CONTROL_VERIFIED (plan 05 §17–§21).

Verifies the cost/credits/quota control layer
(`orchestration/windagent_orchestration/production/`: cost_catalog,
estimator, quota_ledger, budget_policy, circuit_breaker) against the
contracts in `docs/video_production/cost_quota/`:

  artifacts/video_production/phase_19/
  ├── cost_catalog_receipt.json   (rules, unknown -> None, signature versioning)
  ├── estimate_receipt.json       (math, UNKNOWN fail-closed, hash binding, staleness)
  ├── quota_ledger_receipt.json   (append-only, replay no-double-count, never overwrite debit)
  ├── budget_policy_receipt.json  (unknown fail-closed, approval hash, limits, reserve/reconcile)
  ├── circuit_breaker_receipt.json(open conditions, never continuous reset, human reset)
  └── phase_verdict.json

Gate conditions (plan 05 §21):
  1. every submit path goes through reserve/approval policy;
  2. unknown cost/credit state fails closed;
  3. retry and candidate counts are bounded;
  4. the ledger never double counts through replay.

Deterministic: fixed clock + fixed id_fn -> receipts byte-identical across
runs (modulo generated_at / verified_at). Supports --no-write / --verify-only.
"""

from __future__ import annotations

import datetime
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_19"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_orchestration.production import (  # noqa: E402
    CircuitState,
    CostCatalog,
    CostCatalogEntry,
    CreditEstimator,
    DailyLimit,
    EstimateLine,
    GenerationBudgetPolicy,
    MonthlyLimit,
    ProjectLimit,
    ProviderCircuitBreaker,
    QuotaLedger,
    RetryBudget,
    SubmitVerdict,
)

FIXED_CLOCK = 1700000000.0  # deterministic epoch for all receipts


def _clock():
    return FIXED_CLOCK


def _id_factory():
    counter = itertools.count(1)
    return lambda: f"det_{next(counter):04d}"


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


PLAN_HASH = "p" * 64
REQ_HASH = "r" * 64


def _catalog() -> CostCatalog:
    return CostCatalog(
        entries=[
            CostCatalogEntry(
                provider="flow", model="video-v2", operation="video_generation",
                mode="standard", candidate_semantics="per_candidate",
                base_credits=50, per_second_credits=5, per_reference_credits=2,
                post_production_credits=10, effective_at="2026-01-01",
                source="observed", confidence=0.9,
            ),
            CostCatalogEntry(
                provider="flow", model="video-v2", operation="video_generation",
                mode="quality", candidate_semantics="per_candidate",
                base_credits=100, per_second_credits=8, per_reference_credits=2,
                post_production_credits=10, effective_at="2026-01-01",
                source="observed", confidence=0.8,
            ),
            CostCatalogEntry(
                provider="flow", model="image-v2", operation="image_generation",
                mode="standard", candidate_semantics="per_candidate",
                base_credits=10, per_second_credits=0,
                effective_at="2026-01-01", source="vendor_doc", confidence=1.0,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Receipt 1 — cost catalog (§19.1)
# ---------------------------------------------------------------------------


def verify_cost_catalog() -> dict:
    checks = []
    cat = _catalog()

    rule = cat.rule_for(provider="flow", model="video-v2", operation="video_generation", mode="standard")
    _record(checks, "rule_matched_exact", rule is not None and rule.mode == "standard", "exact match found")
    _record(checks, "rule_credits", rule.base_credits == 50 and rule.per_second_credits == 5, f"base={rule.base_credits} per_sec={rule.per_second_credits}")

    unknown = cat.rule_for(provider="flow", model="no-such-model", operation="video_generation")
    _record(checks, "unknown_rule_returns_none", unknown is None, "no match -> None (estimator reports UNKNOWN)")

    cat2 = _catalog()
    cat2.add(
        CostCatalogEntry(
            provider="flow", model="video-v3", operation="video_generation",
            base_credits=80, effective_at="2026-02-01",
        )
    )
    _record(checks, "signature_changes_with_entries", cat.signature() != cat2.signature(), "versioned catalog signature")
    _record(checks, "signature_deterministic", cat.signature() == _catalog().signature(), "same entries -> same signature")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP19_COST_AND_QUOTA_CONTROL_VERIFIED",
        "workstream": "cost_catalog",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "catalog_signature": cat.signature(),
    }


# ---------------------------------------------------------------------------
# Receipt 2 — estimator (§19.2)
# ---------------------------------------------------------------------------


def verify_estimate() -> dict:
    checks = []
    cat = _catalog()
    est = CreditEstimator(cat, retry_reserve_ratio=0.25, contingency_ratio=1.2, approval_threshold=100)

    e = est.estimate(
        plan_hash=PLAN_HASH,
        request_hashes=[REQ_HASH],
        lines=[
            EstimateLine(
                provider="flow", model="video-v2", operation="video_generation",
                mode="standard", duration_seconds=10.0, candidate_count=2,
            )
        ],
    )
    _record(checks, "known_estimate", e.status == "KNOWN", e.status)
    _record(checks, "estimated_math", e.estimated_credits == 200, f"estimated={e.estimated_credits}")
    _record(checks, "candidate_count", e.candidate_count == 2, f"candidates={e.candidate_count}")
    _record(checks, "retry_reserve", e.retry_reserve == 50, f"reserve={e.retry_reserve}")
    _record(checks, "maximum_math", e.maximum_credits == 300, f"maximum={e.maximum_credits}")
    _record(checks, "requires_approval", e.requires_approval is True, ">= threshold")

    # unknown rule -> UNKNOWN (fail closed, §19.1)
    u = est.estimate(
        plan_hash=PLAN_HASH,
        request_hashes=[REQ_HASH],
        lines=[EstimateLine(provider="flow", model="ghost", operation="video_generation", duration_seconds=5.0)],
    )
    _record(checks, "unknown_rule_fails_closed", u.status == "UNKNOWN", f"status={u.status}")
    _record(checks, "unknown_reasons_recorded", bool(u.unknown_reasons), "; ".join(u.unknown_reasons))

    # hash binding + determinism
    e2 = est.estimate(
        plan_hash=PLAN_HASH,
        request_hashes=[REQ_HASH],
        lines=[
            EstimateLine(
                provider="flow", model="video-v2", operation="video_generation",
                mode="standard", duration_seconds=10.0, candidate_count=2,
            )
        ],
    )
    _record(checks, "estimate_hash_deterministic", e.estimate_hash() == e2.estimate_hash(), "same inputs -> same hash")
    e3 = est.estimate(
        plan_hash="q" * 64,
        request_hashes=[REQ_HASH],
        lines=[
            EstimateLine(
                provider="flow", model="video-v2", operation="video_generation",
                mode="standard", duration_seconds=10.0, candidate_count=2,
            )
        ],
    )
    _record(checks, "estimate_hash_binds_plan", e.estimate_hash() != e3.estimate_hash(), "different plan -> different hash")

    # staleness on catalog change (§19.2)
    cat2 = _catalog()
    cat2.add(
        CostCatalogEntry(
            provider="flow", model="video-v3", operation="video_generation",
            base_credits=1, effective_at="2026-03-01",
        )
    )
    _record(checks, "stale_when_catalog_changed", e.is_stale_for(PLAN_HASH, cat2.signature()) is True, "catalog signature changed")
    _record(checks, "current_when_catalog_same", e.is_stale_for(PLAN_HASH, cat.signature()) is False, "catalog unchanged")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP19_COST_AND_QUOTA_CONTROL_VERIFIED",
        "workstream": "estimate",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "sample_estimate": e.to_dict(),
    }


# ---------------------------------------------------------------------------
# Receipt 3 — quota ledger (§19.3)
# ---------------------------------------------------------------------------


def verify_quota_ledger() -> dict:
    checks = []
    ledger = QuotaLedger(clock=_clock, id_fn=_id_factory())

    ledger.estimate(run_id="r1", request_hash="h1", amount=200, dedup_key="est:h1")
    ledger.reserve(run_id="r1", request_hash="h1", amount=300, estimate_hash="eh1", dedup_key="reserve:h1")
    ledger.submit(run_id="r1", request_hash="h1", amount=300, external_id="ext1", dedup_key="submit:h1")
    ledger.observe_debit(run_id="r1", request_hash="h1", amount=180, source="billing", external_id="ext1", dedup_key="obs:h1:ext1")
    ledger.release(run_id="r1", request_hash="h1", amount=120, dedup_key="release:h1")
    ledger.adjust(run_id="r1", request_hash="h1", amount=-10, reason="billing correction", source="audit", dedup_key="adj:h1")
    ledger.unknown(run_id="r1", request_hash="h2", dedup_key="unk:h2")

    types = {e.entry_type.value for e in ledger.entries()}
    _record(checks, "all_seven_entry_types", types == {
        "ESTIMATED", "RESERVED", "SUBMITTED", "OBSERVED_DEBIT", "RELEASED", "ADJUSTED", "UNKNOWN",
    }, f"types={sorted(types)}")

    _record(checks, "totals_derived", ledger.total_reserved() == 300 and ledger.total_observed_debit() == 180
            and ledger.total_released() == 120 and ledger.total_adjusted() == -10, "derived totals")
    _record(checks, "committed_balance", ledger.committed() == 180 and ledger.balance() == -10,  # committed 300-120=180; balance 180-180-10=-10
            f"committed={ledger.committed()} balance={ledger.balance()}")

    # duplicate observation -> no double debit (replay safe)
    before_count = len(ledger.entries())
    replay = ledger.observe_debit(run_id="r1", request_hash="h1", amount=180, source="billing", external_id="ext1", dedup_key="obs:h1:ext1")
    _record(checks, "duplicate_observation_no_double_debit", len(ledger.entries()) == before_count
            and ledger.total_observed_debit() == 180, f"entries={len(ledger.entries())} debit={ledger.total_observed_debit()}")
    _record(checks, "replay_returns_existing_entry", replay.dedup_key == "obs:h1:ext1", "returned existing entry")

    # crash after reserve -> replay stream -> ledger identical
    snap = ledger.to_dict()
    ledger.reserve(run_id="r1", request_hash="h1", amount=300, estimate_hash="eh1", dedup_key="reserve:h1")
    ledger.observe_debit(run_id="r1", request_hash="h1", amount=180, source="billing", external_id="ext1", dedup_key="obs:h1:ext1")
    ledger.submit(run_id="r1", request_hash="h1", amount=300, external_id="ext1", dedup_key="submit:h1")
    _record(checks, "replay_stream_no_double_count", ledger.to_dict() == snap, "re-applying stream is byte-identical")

    # observed debit never overwritten by adjustment
    observed = next(e for e in ledger.entries() if e.entry_type.value == "OBSERVED_DEBIT")
    _record(checks, "observed_debit_never_overwritten", observed.amount == 180, f"amount={observed.amount}")

    # serialization round trip
    restored = QuotaLedger.from_dict(ledger.to_dict())
    _record(checks, "serialization_round_trip", restored.to_dict() == ledger.to_dict(), "to_dict/from_dict identical")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP19_COST_AND_QUOTA_CONTROL_VERIFIED",
        "workstream": "quota_ledger",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "ledger_snapshot": ledger.to_dict(),
    }


# ---------------------------------------------------------------------------
# Receipt 4 — budget policy (§19.4)
# ---------------------------------------------------------------------------


def verify_budget_policy() -> dict:
    checks = []
    cat = _catalog()
    est = CreditEstimator(cat, retry_reserve_ratio=0.25, contingency_ratio=1.2, approval_threshold=100)
    ledger = QuotaLedger(clock=_clock, id_fn=_id_factory())
    policy = GenerationBudgetPolicy(estimator=est, ledger=ledger, candidate_limit=4, max_parallel_submits=1)

    e = est.estimate(
        plan_hash=PLAN_HASH,
        request_hashes=[REQ_HASH],
        lines=[
            EstimateLine(
                provider="flow", model="video-v2", operation="video_generation",
                mode="standard", duration_seconds=10.0, candidate_count=2,
            )
        ],
    )

    # unknown credit state / unknown estimate fail closed
    d_unknown_credit = policy.can_submit(estimate=e, credits_available=None, plan_hash=PLAN_HASH)
    _record(checks, "unknown_credit_state_fails_closed", d_unknown_credit.verdict == SubmitVerdict.BLOCKED_UNKNOWN_CREDIT_STATE,
            d_unknown_credit.verdict)

    u = est.estimate(
        plan_hash=PLAN_HASH, request_hashes=[REQ_HASH],
        lines=[EstimateLine(provider="flow", model="ghost", operation="video_generation", duration_seconds=5.0)],
    )
    d_unknown_est = policy.can_submit(estimate=u, credits_available=1000, plan_hash=PLAN_HASH)
    _record(checks, "unknown_estimate_fails_closed", d_unknown_est.verdict == SubmitVerdict.BLOCKED_UNKNOWN_ESTIMATE,
            d_unknown_est.verdict)

    # approval required -> approve (bound to estimate hash) -> allowed
    d_req = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH)
    _record(checks, "approval_required_for_high_cost", d_req.verdict == SubmitVerdict.BLOCKED_APPROVAL_REQUIRED, d_req.verdict)
    policy.approve(estimate=e, actor="human")
    d_ok = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH)
    _record(checks, "approval_matches_estimate_hash_allows", d_ok.verdict == SubmitVerdict.ALLOWED, d_ok.verdict)

    # approval for a DIFFERENT hash is not accepted
    e_other_plan = est.estimate(
        plan_hash="q" * 64, request_hashes=[REQ_HASH],
        lines=[
            EstimateLine(
                provider="flow", model="video-v2", operation="video_generation",
                mode="standard", duration_seconds=10.0, candidate_count=2,
            )
        ],
    )
    _record(checks, "approval_not_reused_for_other_hash", policy.has_approval(e_other_plan) is False,
            "different plan hash -> different estimate hash -> not approved")

    # stale estimate after catalog change
    cat2 = _catalog()
    cat2.add(
        CostCatalogEntry(
            provider="flow", model="video-v3", operation="video_generation",
            base_credits=1, effective_at="2026-03-01",
        )
    )
    policy2 = GenerationBudgetPolicy(estimator=CreditEstimator(cat2, retry_reserve_ratio=0.25, contingency_ratio=1.2, approval_threshold=100),
                                     ledger=QuotaLedger(clock=_clock, id_fn=_id_factory()))
    d_stale = policy2.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH)
    _record(checks, "stale_estimate_blocked", d_stale.verdict == SubmitVerdict.BLOCKED_STALE_APPROVAL, d_stale.verdict)

    # retry bounded
    budget = RetryBudget(max_retries=2, used_retries=2)
    d_retry = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH, is_retry=True, retry_budget=budget)
    _record(checks, "retry_budget_exhausted_blocked", d_retry.verdict == SubmitVerdict.BLOCKED_RETRY_BUDGET, d_retry.verdict)

    # candidate bounded
    big = est.estimate(
        plan_hash=PLAN_HASH, request_hashes=[REQ_HASH],
        lines=[
            EstimateLine(
                provider="flow", model="video-v2", operation="video_generation",
                mode="standard", duration_seconds=5.0, candidate_count=8,
            )
        ],
    )
    policy.approve(estimate=big, actor="human")
    d_cand = policy.can_submit(estimate=big, credits_available=10000, plan_hash=PLAN_HASH)
    _record(checks, "candidate_limit_blocked", d_cand.verdict == SubmitVerdict.BLOCKED_CANDIDATE_LIMIT, d_cand.verdict)

    # limits: exact boundary allowed, exceeded blocked
    small = est.estimate(
        plan_hash=PLAN_HASH, request_hashes=[REQ_HASH],
        lines=[
            EstimateLine(
                provider="flow", model="video-v2", operation="video_generation",
                mode="standard", duration_seconds=1.0, candidate_count=1,
            )
        ],
    )
    # base 50 + 5*1 = 55; reserve 14 (25% of 55); max = round((55+14)*1.2) = 83
    _record(checks, "small_estimate_maximum", small.maximum_credits == 83, f"maximum={small.maximum_credits}")
    policy.approve(estimate=small, actor="human")

    d_boundary = policy.can_submit(
        estimate=small, credits_available=1000, plan_hash=PLAN_HASH,
        daily=DailyLimit(max_credits=166, used_credits=83),
    )
    _record(checks, "daily_exact_boundary_allowed", d_boundary.verdict == SubmitVerdict.ALLOWED, d_boundary.verdict)
    d_daily = policy.can_submit(
        estimate=small, credits_available=1000, plan_hash=PLAN_HASH,
        daily=DailyLimit(max_credits=166, used_credits=84),
    )
    _record(checks, "daily_limit_blocked", d_daily.verdict == SubmitVerdict.BLOCKED_DAILY_LIMIT, d_daily.verdict)
    d_month = policy.can_submit(
        estimate=small, credits_available=1000, plan_hash=PLAN_HASH,
        monthly=MonthlyLimit(max_credits=100, used_credits=90),
    )
    _record(checks, "monthly_limit_blocked", d_month.verdict == SubmitVerdict.BLOCKED_MONTHLY_LIMIT, d_month.verdict)
    d_proj = policy.can_submit(
        estimate=small, credits_available=1000, plan_hash=PLAN_HASH,
        project=ProjectLimit(max_credits=200, used_credits=150),
    )
    _record(checks, "project_limit_blocked", d_proj.verdict == SubmitVerdict.BLOCKED_PROJECT_LIMIT, d_proj.verdict)
    policy_run = GenerationBudgetPolicy(
        estimator=est, ledger=QuotaLedger(clock=_clock, id_fn=_id_factory()),
        approval_threshold=0, run_limit_credits=50,
    )
    policy_run.approve(estimate=small, actor="human")
    d_run = policy_run.can_submit(estimate=small, credits_available=1000, plan_hash=PLAN_HASH)
    _record(checks, "run_limit_blocked", d_run.verdict == SubmitVerdict.BLOCKED_RUN_LIMIT, d_run.verdict)

    # insufficient credits + parallel bound
    d_credits = policy.can_submit(estimate=e, credits_available=10, plan_hash=PLAN_HASH)
    _record(checks, "insufficient_credits_blocked", d_credits.verdict == SubmitVerdict.BLOCKED_INSUFFICIENT_CREDITS, d_credits.verdict)
    d_parallel = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH, in_flight_submits=1)
    _record(checks, "parallel_submit_bound", d_parallel.verdict == SubmitVerdict.BLOCKED_PARALLEL_SUBMIT, d_parallel.verdict)

    # reserve BEFORE submit + reconcile AFTER observed (no double count)
    policy.reserve(run_id="r1", request_hash=REQ_HASH, estimate=e, dedup_key="reserve:vp19:r1")
    _record(checks, "reserve_before_submit", ledger.total_reserved() == e.maximum_credits, f"reserved={ledger.total_reserved()}")
    policy.reserve(run_id="r1", request_hash=REQ_HASH, estimate=e, dedup_key="reserve:vp19:r1")
    _record(checks, "reserve_idempotent_on_replay", ledger.total_reserved() == e.maximum_credits, "crash+replay no double reserve")
    policy.reconcile(run_id="r1", request_hash=REQ_HASH, observed=120, external_id="ext1", source="billing", dedup_key="obs:vp19:r1:ext1")
    policy.reconcile(run_id="r1", request_hash=REQ_HASH, observed=120, external_id="ext1", source="billing", dedup_key="obs:vp19:r1:ext1")
    _record(checks, "reconcile_no_double_debit", ledger.total_observed_debit() == 120, f"observed={ledger.total_observed_debit()}")
    policy.reconcile(run_id="r1", request_hash="h9", observed=None, external_id="ext9", source="billing", dedup_key="unk:vp19:h9")
    _record(checks, "reconcile_unknown_records_unknown", any(e.entry_type.value == "UNKNOWN" for e in ledger.entries()), "UNKNOWN recorded")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP19_COST_AND_QUOTA_CONTROL_VERIFIED",
        "workstream": "budget_policy",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Receipt 5 — circuit breaker (§19.5)
# ---------------------------------------------------------------------------


def verify_circuit_breaker() -> dict:
    checks = []

    cb = ProviderCircuitBreaker(clock=_clock, id_fn=_id_factory())
    _record(checks, "starts_closed", cb.state == CircuitState.CLOSED, cb.state.value)

    cb.record_insufficient_credits("balance 0")
    _record(checks, "opens_on_insufficient_credits", cb.state == CircuitState.OPEN, cb.state.value)

    cb2 = ProviderCircuitBreaker(failure_threshold=3, clock=_clock, id_fn=_id_factory())
    cb2.record_provider_error("e1")
    cb2.record_provider_error("e2")
    _record(checks, "below_threshold_stays_closed", cb2.state == CircuitState.CLOSED, cb2.state.value)
    cb2.record_provider_error("e3")
    _record(checks, "opens_on_repeated_errors", cb2.state == CircuitState.OPEN, cb2.state.value)

    cb3 = ProviderCircuitBreaker(max_cost_deviation_ratio=1.5, clock=_clock, id_fn=_id_factory())
    _record(checks, "cost_within_policy_stays_closed", cb3.record_cost_deviation(observed=120, estimated=100) == CircuitState.CLOSED,
            "ratio 1.2 <= 1.5")
    cb3b = ProviderCircuitBreaker(max_cost_deviation_ratio=1.5, clock=_clock, id_fn=_id_factory())
    _record(checks, "opens_on_cost_deviation", cb3b.record_cost_deviation(observed=200, estimated=100) == CircuitState.OPEN,
            "ratio 2.0 > 1.5")

    cb4 = ProviderCircuitBreaker(clock=_clock, id_fn=_id_factory())
    _record(checks, "opens_on_unknown_config", cb4.record_unknown_config() == CircuitState.OPEN, "unknown config/cost")
    cb5 = ProviderCircuitBreaker(clock=_clock, id_fn=_id_factory())
    _record(checks, "opens_on_account_challenge", cb5.record_account_challenge("repeated") == CircuitState.OPEN, "account challenge")

    # never continuous auto-reset: OPEN -> HALF_OPEN after cooldown, never CLOSED by time
    cbt = ProviderCircuitBreaker(cooldown_seconds=300, clock=_clock, id_fn=_id_factory())
    cbt.record_insufficient_credits()
    _record(checks, "open_before_cooldown", cbt.maybe_reset() == CircuitState.OPEN, "cooldown not elapsed")
    # trip at FIXED_CLOCK, THEN advance the clock past the cooldown, then reset
    clock = {"now": FIXED_CLOCK}
    cbt2 = ProviderCircuitBreaker(cooldown_seconds=300, clock=lambda: clock["now"], id_fn=_id_factory())
    cbt2.record_insufficient_credits()
    clock["now"] = FIXED_CLOCK + 400.0
    _record(checks, "half_open_after_cooldown", cbt2.maybe_reset() == CircuitState.HALF_OPEN, "never auto-closes")
    _record(checks, "half_open_stays_until_success", cbt2.maybe_reset() == CircuitState.HALF_OPEN, "no continuous reset")
    cbt2.record_success()
    _record(checks, "closes_on_probe_success", cbt2.state == CircuitState.CLOSED, cbt2.state.value)

    cbh = ProviderCircuitBreaker(cooldown_seconds=3600, clock=_clock, id_fn=_id_factory())
    cbh.record_account_challenge()
    _record(checks, "human_reset_closes", cbh.human_reset(actor="operator", reason="reviewed") == CircuitState.CLOSED,
            "explicit human review closes")

    restored = ProviderCircuitBreaker.from_dict(cbt2.to_dict())
    _record(checks, "serialization_round_trip", restored.state == cbt2.state
            and len(restored.events()) == len(cbt2.events()), f"state={restored.state.value}")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP19_COST_AND_QUOTA_CONTROL_VERIFIED",
        "workstream": "circuit_breaker",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(no_write: bool = False) -> int:
    print("Verifying Phase 19 — Cost, credits and quota control...")
    cc = verify_cost_catalog()
    est = verify_estimate()
    ql = verify_quota_ledger()
    bp = verify_budget_policy()
    cb = verify_circuit_breaker()

    all_workstreams = [cc, est, ql, bp, cb]
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
        "gate": "VP19_COST_AND_QUOTA_CONTROL_VERIFIED",
        "status": overall_status,
        "verified_at": utc_now_iso(),
        "workstreams": {
            "cost_catalog": cc["all_checks_pass"],
            "estimate": est["all_checks_pass"],
            "quota_ledger": ql["all_checks_pass"],
            "budget_policy": bp["all_checks_pass"],
            "circuit_breaker": cb["all_checks_pass"],
        },
        "blocking_reasons": gate_reasons,
    }

    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)
        write_json(PHASE_DIR / "cost_catalog_receipt.json", cc)
        write_json(PHASE_DIR / "estimate_receipt.json", est)
        write_json(PHASE_DIR / "quota_ledger_receipt.json", ql)
        write_json(PHASE_DIR / "budget_policy_receipt.json", bp)
        write_json(PHASE_DIR / "circuit_breaker_receipt.json", cb)
        write_json(PHASE_DIR / "phase_verdict.json", verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(overall_status, cc, est, ql, bp, cb),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_19 artifacts untouched.")

    print(f"Phase 19 verdict: {overall_status}")
    print(f"  cost catalog: {'PASS' if cc['all_checks_pass'] else 'FAIL'}")
    print(f"  estimate: {'PASS' if est['all_checks_pass'] else 'FAIL'}")
    print(f"  quota ledger: {'PASS' if ql['all_checks_pass'] else 'FAIL'}")
    print(f"  budget policy: {'PASS' if bp['all_checks_pass'] else 'FAIL'}")
    print(f"  circuit breaker: {'PASS' if cb['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, cc, est, ql, bp, cb) -> str:
    return f"""# Phase 19 Report — Cost, Credits & Quota Control

- **Gate:** `VP19_COST_AND_QUOTA_CONTROL_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Cost Catalog

- Contract: `docs/video_production/cost_quota/cost_catalog_contract.md`
- Rules carry provenance + effective date; unknown rule -> None (UNKNOWN).
- Checks: {cc.get('check_count')}; all pass: {cc.get('all_checks_pass')}

## Estimate

- Contract: `docs/video_production/cost_quota/estimate_contract.md`
- Bound to plan hash + catalog signature; unknown fails closed.
- Checks: {est.get('check_count')}; all pass: {est.get('all_checks_pass')}

## Quota Ledger

- Contract: `docs/video_production/cost_quota/quota_ledger_contract.md`
- Append-only, replay-safe, observed debit never overwritten.
- Checks: {ql.get('check_count')}; all pass: {ql.get('all_checks_pass')}

## Budget Policy

- Contract: `docs/video_production/cost_quota/budget_policy_contract.md`
- Single gate: reserve before submit, approval bound to estimate hash,
  limits before provider call.
- Checks: {bp.get('check_count')}; all pass: {bp.get('all_checks_pass')}

## Circuit Breaker

- Contract: `docs/video_production/cost_quota/circuit_breaker_contract.md`
- Opens on cost/provider risk; never continuous auto-reset.
- Checks: {cb.get('check_count')}; all pass: {cb.get('all_checks_pass')}

## Evidence

- `cost_catalog_receipt.json`
- `estimate_receipt.json`
- `quota_ledger_receipt.json`
- `budget_policy_receipt.json`
- `circuit_breaker_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
