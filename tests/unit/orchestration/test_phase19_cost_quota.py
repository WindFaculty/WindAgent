"""
Phase 19 — Cost, credits and quota management unit tests (plan 05 §20).

Covers the gate test matrix:
- unknown cost/credit state fails closed;
- exact boundary and exceeding project/daily/monthly limits;
- candidate / retry reserve;
- estimate stale when plan or cost catalog changes;
- duplicate result does not double-debit;
- crash after reserve/submission and ledger reconciliation;
- insufficient credits opens the circuit;
- human approval matches the estimate hash.
"""

from __future__ import annotations

import pytest

from windagent_core.errors.exceptions import ValidationError

from windagent_orchestration.production import (
    CircuitState,
    CostCatalog,
    CostCatalogEntry,
    CostEstimate,
    CreditEstimator,
    DailyLimit,
    EstimateLine,
    GenerationBudgetPolicy,
    MonthlyLimit,
    ProjectLimit,
    ProviderCircuitBreaker,
    QuotaLedger,
    QuotaEntryType,
    RetryBudget,
    SubmitVerdict,
)

PLAN_HASH = "p" * 64
REQ_HASH = "r" * 64


def _catalog() -> CostCatalog:
    return CostCatalog(
        entries=[
            CostCatalogEntry(
                provider="flow",
                model="video-v2",
                operation="video_generation",
                mode="standard",
                candidate_semantics="per_candidate",
                base_credits=50,
                per_second_credits=5,
                per_reference_credits=2,
                post_production_credits=10,
                effective_at="2026-01-01",
                source="observed",
                confidence=0.9,
            ),
            CostCatalogEntry(
                provider="flow",
                model="video-v2",
                operation="video_generation",
                mode="quality",
                candidate_semantics="per_candidate",
                base_credits=100,
                per_second_credits=8,
                per_reference_credits=2,
                post_production_credits=10,
                effective_at="2026-01-01",
                source="observed",
                confidence=0.8,
            ),
            CostCatalogEntry(
                provider="flow",
                model="image-v2",
                operation="image_generation",
                mode="standard",
                candidate_semantics="per_candidate",
                base_credits=10,
                per_second_credits=0,
                effective_at="2026-01-01",
                source="vendor_doc",
                confidence=1.0,
            ),
        ]
    )


def _estimator(catalog: CostCatalog | None = None) -> CreditEstimator:
    return CreditEstimator(catalog or _catalog(), retry_reserve_ratio=0.25, contingency_ratio=1.2, approval_threshold=100)


def _estimate(estimator: CreditEstimator | None = None, **kw) -> CostEstimate:
    est = estimator or _estimator()
    lines = kw.pop("lines", None) or [
        EstimateLine(
            provider="flow",
            model="video-v2",
            operation="video_generation",
            mode="standard",
            duration_seconds=10.0,
            candidate_count=2,
        )
    ]
    return est.estimate(plan_hash=kw.pop("plan_hash", PLAN_HASH), request_hashes=kw.pop("request_hashes", [REQ_HASH]), lines=lines)


def _policy(ledger: QuotaLedger | None = None, **kw) -> GenerationBudgetPolicy:
    est = kw.pop("estimator", None) or _estimator()
    return GenerationBudgetPolicy(
        estimator=est,
        ledger=ledger or QuotaLedger(),
        **kw,
    )


# ---------------------------------------------------------------------------
# Cost catalog (§19.1)
# ---------------------------------------------------------------------------


def test_catalog_unknown_rule_returns_none():
    cat = _catalog()
    assert cat.rule_for(provider="flow", model="unknown-model", operation="video_generation") is None


def test_catalog_rule_for_effective_date():
    cat = _catalog()
    rule = cat.rule_for(provider="flow", model="video-v2", operation="video_generation", effective_at="2026-06-01")
    assert rule is not None and rule.mode == "standard"


def test_catalog_signature_changes_with_entries():
    cat1 = _catalog()
    cat2 = _catalog()
    cat2.add(
        CostCatalogEntry(
            provider="flow", model="video-v3", operation="video_generation",
            base_credits=80, effective_at="2026-02-01",
        )
    )
    assert cat1.signature() != cat2.signature()


# ---------------------------------------------------------------------------
# Estimator (§19.2)
# ---------------------------------------------------------------------------


def test_estimate_known_math():
    est = _estimator()
    e = _estimate(est)
    # base 50 + 5*10 = 100 per candidate x 2 candidates = 200
    assert e.status == "KNOWN"
    assert e.estimated_credits == 200
    assert e.candidate_count == 2
    assert e.retry_reserve == 50  # 25% of 200
    # maximum = (200 + 50) * 1.2 = 300
    assert e.maximum_credits == 300
    assert e.requires_approval is True  # 300 >= 100


def test_estimate_unknown_when_rule_missing_fails_closed():
    est = _estimator()
    e = est.estimate(
        plan_hash=PLAN_HASH,
        request_hashes=[REQ_HASH],
        lines=[EstimateLine(provider="flow", model="nope", operation="video_generation", duration_seconds=5.0)],
    )
    assert e.status == "UNKNOWN"
    assert e.unknown_reasons


def test_estimate_hash_binds_plan_catalog_and_numbers():
    e1 = _estimate()
    e2 = _estimate(plan_hash="q" * 64)
    e3 = _estimate(lines=[EstimateLine(provider="flow", model="video-v2", operation="video_generation", duration_seconds=10.0, candidate_count=1)])
    assert e1.estimate_hash() != e2.estimate_hash()
    assert e1.estimate_hash() != e3.estimate_hash()
    assert e1.estimate_hash() == _estimate().estimate_hash()  # deterministic


def test_estimate_stale_when_catalog_changes():
    cat1 = _catalog()
    est1 = _estimator(cat1)
    e = _estimate(est1)
    cat2 = _catalog()
    cat2.add(
        CostCatalogEntry(
            provider="flow", model="video-v3", operation="video_generation",
            base_credits=1, effective_at="2026-03-01",
        )
    )
    assert e.is_stale_for(PLAN_HASH, cat2.signature()) is True
    assert e.is_stale_for(PLAN_HASH, cat1.signature()) is False


# ---------------------------------------------------------------------------
# Quota ledger (§19.3) — append-only, replay-safe, no double count
# ---------------------------------------------------------------------------


def test_ledger_append_only_entry_types():
    ledger = QuotaLedger()
    for typ in QuotaEntryType:
        if typ == QuotaEntryType.ADJUSTED:
            ledger.adjust(run_id="r", request_hash="h", amount=5, reason="fix", source="audit")
        elif typ == QuotaEntryType.UNKNOWN:
            ledger.unknown(run_id="r", request_hash="h")
        else:
            ledger.record(entry_type=typ, run_id="r", request_hash="h", amount=10)
    types = {e.entry_type for e in ledger.entries()}
    assert types == set(QuotaEntryType)


def test_ledger_duplicate_observation_no_double_debit():
    ledger = QuotaLedger()
    ledger.observe_debit(run_id="r", request_hash="h1", amount=60, source="billing", dedup_key="obs:h1:ext1")
    second = ledger.observe_debit(run_id="r", request_hash="h1", amount=60, source="billing", dedup_key="obs:h1:ext1")
    # replay returns the EXISTING entry, ledger does not grow
    assert len(ledger.entries()) == 1
    assert second.entry_id == ledger.entries()[0].entry_id
    assert ledger.total_observed_debit() == 60  # never double counted


def test_ledger_replay_reserve_idempotent():
    ledger = QuotaLedger()
    first = ledger.reserve(run_id="r", request_hash="h2", amount=300, estimate_hash="eh", dedup_key="reserve:r:h2")
    replay = ledger.reserve(run_id="r", request_hash="h2", amount=300, estimate_hash="eh", dedup_key="reserve:r:h2")
    assert replay.entry_id == first.entry_id
    assert len(ledger.entries()) == 1
    assert ledger.total_reserved() == 300


def test_ledger_reconcile_after_crash_no_double_reserve():
    """Crash after reserve -> replay the outbox stream -> ledger unchanged."""
    ledger = QuotaLedger()
    ledger.reserve(run_id="r", request_hash="h3", amount=200, estimate_hash="eh3", dedup_key="reserve:r:h3")
    ledger.observe_debit(run_id="r", request_hash="h3", amount=120, source="billing", external_id="ext3", dedup_key="obs:r:h3:ext3")
    before = ledger.to_dict()
    # replay identical stream
    ledger.reserve(run_id="r", request_hash="h3", amount=200, estimate_hash="eh3", dedup_key="reserve:r:h3")
    ledger.observe_debit(run_id="r", request_hash="h3", amount=120, source="billing", external_id="ext3", dedup_key="obs:r:h3:ext3")
    assert ledger.to_dict() == before
    assert ledger.committed() == 200
    assert ledger.balance() == 80


def test_ledger_adjust_requires_reason_and_source():
    ledger = QuotaLedger()
    with pytest.raises(ValidationError):
        ledger.adjust(run_id="r", request_hash="h", amount=5, reason="", source="audit")
    with pytest.raises(ValidationError):
        ledger.adjust(run_id="r", request_hash="h", amount=5, reason="fix", source="")


def test_ledger_observed_debit_requires_source():
    ledger = QuotaLedger()
    with pytest.raises(ValidationError):
        ledger.observe_debit(run_id="r", request_hash="h", amount=10, source="")


def test_ledger_never_overwrites_observed_debit():
    """Adjustment appends; it never mutates the observed debit entry."""
    ledger = QuotaLedger()
    observed = ledger.observe_debit(run_id="r", request_hash="h", amount=100, source="billing", dedup_key="o1")
    ledger.adjust(run_id="r", request_hash="h", amount=-20, reason="billing correction", source="audit")
    assert observed.amount == 100  # unchanged
    assert ledger.total_observed_debit() == 100
    assert ledger.total_adjusted() == -20


def test_ledger_serialization_round_trip():
    ledger = QuotaLedger()
    ledger.reserve(run_id="r", request_hash="h", amount=100, dedup_key="k1")
    ledger.observe_debit(run_id="r", request_hash="h", amount=40, source="billing", dedup_key="k2")
    restored = QuotaLedger.from_dict(ledger.to_dict())
    assert restored.to_dict() == ledger.to_dict()


# ---------------------------------------------------------------------------
# Budget policy (§19.4) — gate
# ---------------------------------------------------------------------------


def test_policy_blocks_unknown_estimate():
    est = _estimator()
    e = est.estimate(
        plan_hash=PLAN_HASH,
        request_hashes=[REQ_HASH],
        lines=[EstimateLine(provider="flow", model="missing", operation="video_generation")],
    )
    d = _policy().can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH)
    assert d.verdict == SubmitVerdict.BLOCKED_UNKNOWN_ESTIMATE
    assert not d.allowed


def test_policy_blocks_unknown_credit_state():
    d = _policy().can_submit(estimate=_estimate(), credits_available=None, plan_hash=PLAN_HASH)
    assert d.verdict == SubmitVerdict.BLOCKED_UNKNOWN_CREDIT_STATE


def test_policy_blocks_approval_required_and_approves():
    policy = _policy()
    e = _estimate()
    d = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH)
    assert d.verdict == SubmitVerdict.BLOCKED_APPROVAL_REQUIRED
    policy.approve(estimate=e, actor="human")
    d2 = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH)
    assert d2.verdict == SubmitVerdict.ALLOWED


def test_policy_approval_matches_estimate_hash():
    """Human approval must be for the exact estimate hash (§20)."""
    policy = _policy()
    e1 = _estimate()
    e2 = _estimate(plan_hash="q" * 64)
    policy.approve(estimate=e1, actor="human")
    assert policy.has_approval(e1) is True
    assert policy.has_approval(e2) is False  # different hash -> not approved


def test_policy_blocks_stale_estimate_after_catalog_change():
    cat1 = _catalog()
    est1 = _estimator(cat1)
    e = _estimate(est1)
    # policy uses a NEWER catalog (entry added) -> estimate is stale
    cat2 = _catalog()
    cat2.add(
        CostCatalogEntry(
            provider="flow", model="video-v3", operation="video_generation",
            base_credits=80, effective_at="2026-02-01",
        )
    )
    policy = _policy(estimator=_estimator(cat2), approval_threshold=0)
    # catalog grew -> estimate stale -> blocked even with approval
    d = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH)
    assert d.verdict == SubmitVerdict.BLOCKED_STALE_APPROVAL


def test_policy_blocks_retry_budget_exhausted():
    policy = _policy()
    e = _estimate()
    policy.approve(estimate=e, actor="human")
    budget = RetryBudget(max_retries=2, used_retries=2)
    d = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH, is_retry=True, retry_budget=budget)
    assert d.verdict == SubmitVerdict.BLOCKED_RETRY_BUDGET
    ok = RetryBudget(max_retries=2, used_retries=1)
    d2 = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH, is_retry=True, retry_budget=ok)
    assert d2.allowed


def test_policy_blocks_candidate_limit():
    policy = _policy(candidate_limit=2)
    est = _estimator()
    e = est.estimate(
        plan_hash=PLAN_HASH,
        request_hashes=[REQ_HASH],
        lines=[EstimateLine(provider="flow", model="video-v2", operation="video_generation", duration_seconds=5.0, candidate_count=5)],
    )
    policy.approve(estimate=e, actor="human")
    d = policy.can_submit(estimate=e, credits_available=10000, plan_hash=PLAN_HASH)
    assert d.verdict == SubmitVerdict.BLOCKED_CANDIDATE_LIMIT


def test_policy_exact_boundary_and_exceeding_limits():
    policy = _policy(approval_threshold=0)
    est = _estimator()
    e = est.estimate(
        plan_hash=PLAN_HASH,
        request_hashes=[REQ_HASH],
        lines=[EstimateLine(provider="flow", model="video-v2", operation="video_generation", duration_seconds=1.0, candidate_count=1)],
    )
    # base 50 + 5 = 55; reserve 14 (25% of 55=13.75 -> 14); max = (55+14)*1.2 = 82.8 -> 83
    assert e.maximum_credits == 83
    policy.approve(estimate=e, actor="human")

    # daily exact boundary: used 83-83 -> 0 remaining, amount 83 fits
    d_boundary = policy.can_submit(
        estimate=e, credits_available=1000, plan_hash=PLAN_HASH,
        daily=DailyLimit(max_credits=166, used_credits=83),
    )
    assert d_boundary.verdict == SubmitVerdict.ALLOWED
    # daily exceeded: used 83 + 83 > 166
    d_exceed = policy.can_submit(
        estimate=e, credits_available=1000, plan_hash=PLAN_HASH,
        daily=DailyLimit(max_credits=166, used_credits=84),
    )
    assert d_exceed.verdict == SubmitVerdict.BLOCKED_DAILY_LIMIT
    # monthly exceeded
    d_month = policy.can_submit(
        estimate=e, credits_available=1000, plan_hash=PLAN_HASH,
        monthly=MonthlyLimit(max_credits=100, used_credits=90),
    )
    assert d_month.verdict == SubmitVerdict.BLOCKED_MONTHLY_LIMIT
    # project exceeded
    d_proj = policy.can_submit(
        estimate=e, credits_available=1000, plan_hash=PLAN_HASH,
        project=ProjectLimit(max_credits=200, used_credits=150),
    )
    assert d_proj.verdict == SubmitVerdict.BLOCKED_PROJECT_LIMIT
    # run limit exceeded
    policy_run = _policy(approval_threshold=0, run_limit_credits=50)
    policy_run.approve(estimate=e, actor="human")
    d_run = policy_run.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH)
    assert d_run.verdict == SubmitVerdict.BLOCKED_RUN_LIMIT


def test_policy_blocks_insufficient_credits():
    policy = _policy()
    e = _estimate()
    policy.approve(estimate=e, actor="human")
    d = policy.can_submit(estimate=e, credits_available=10, plan_hash=PLAN_HASH)
    assert d.verdict == SubmitVerdict.BLOCKED_INSUFFICIENT_CREDITS


def test_policy_blocks_parallel_submit():
    policy = _policy(max_parallel_submits=1)
    e = _estimate()
    policy.approve(estimate=e, actor="human")
    d = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH, in_flight_submits=1)
    assert d.verdict == SubmitVerdict.BLOCKED_PARALLEL_SUBMIT
    d2 = policy.can_submit(estimate=e, credits_available=1000, plan_hash=PLAN_HASH, in_flight_submits=0)
    assert d2.allowed


def test_policy_reserve_and_reconcile():
    ledger = QuotaLedger()
    policy = _policy(ledger=ledger)
    e = _estimate()
    policy.approve(estimate=e, actor="human")
    key = policy.reserve(run_id="r1", request_hash=REQ_HASH, estimate=e)
    assert ledger.total_reserved() == e.maximum_credits
    # crash after reserve: replay the same reserve -> no double reserve
    policy.reserve(run_id="r1", request_hash=REQ_HASH, estimate=e, dedup_key=key)
    assert ledger.total_reserved() == e.maximum_credits
    policy.reconcile(run_id="r1", request_hash=REQ_HASH, observed=120, external_id="ext1", source="billing")
    assert ledger.total_observed_debit() == 120


def test_policy_reconcile_unknown_when_no_observation():
    ledger = QuotaLedger()
    policy = _policy(ledger=ledger)
    policy.reconcile(run_id="r1", request_hash=REQ_HASH, observed=None, external_id="ext9", source="billing")
    assert any(e.entry_type == QuotaEntryType.UNKNOWN for e in ledger.entries())


# ---------------------------------------------------------------------------
# Circuit breaker (§19.5)
# ---------------------------------------------------------------------------


def test_breaker_opens_on_insufficient_credits():
    cb = ProviderCircuitBreaker()
    state = cb.record_insufficient_credits("balance 0")
    assert state == CircuitState.OPEN
    assert cb.is_open()


def test_breaker_opens_after_repeated_errors():
    cb = ProviderCircuitBreaker(failure_threshold=3)
    cb.record_provider_error("e1")
    cb.record_provider_error("e2")
    assert not cb.is_open()
    cb.record_provider_error("e3")
    assert cb.is_open()
    assert cb.state == CircuitState.OPEN


def test_breaker_opens_on_cost_deviation():
    cb = ProviderCircuitBreaker(max_cost_deviation_ratio=1.5)
    assert cb.record_cost_deviation(observed=200, estimated=100) == CircuitState.OPEN
    cb2 = ProviderCircuitBreaker(max_cost_deviation_ratio=1.5)
    assert cb2.record_cost_deviation(observed=120, estimated=100) == CircuitState.CLOSED


def test_breaker_opens_on_unknown_config_and_challenge():
    cb = ProviderCircuitBreaker()
    assert cb.record_unknown_config() == CircuitState.OPEN
    cb2 = ProviderCircuitBreaker()
    assert cb2.record_account_challenge("challenge again") == CircuitState.OPEN


def test_breaker_never_continuous_auto_reset():
    """OPEN -> HALF_OPEN only after cooldown; never closes automatically."""
    clock = {"now": 1000.0}
    cb = ProviderCircuitBreaker(cooldown_seconds=300, clock=lambda: clock["now"])
    cb.record_insufficient_credits()
    assert cb.is_open()
    # before cooldown -> stays OPEN
    clock["now"] = 1100.0
    assert cb.maybe_reset() == CircuitState.OPEN
    # after cooldown -> HALF_OPEN, NOT closed
    clock["now"] = 1400.0
    assert cb.maybe_reset() == CircuitState.HALF_OPEN
    assert not cb.is_open()
    # HALF_OPEN without a probe success stays HALF_OPEN (no continuous reset)
    assert cb.maybe_reset() == CircuitState.HALF_OPEN


def test_breaker_half_open_closes_only_on_success():
    clock = {"now": 1000.0}
    cb = ProviderCircuitBreaker(cooldown_seconds=1, clock=lambda: clock["now"])
    cb.record_insufficient_credits()
    clock["now"] = 2000.0
    cb.maybe_reset()  # HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.consecutive_failures() == 0


def test_breaker_human_reset():
    cb = ProviderCircuitBreaker(cooldown_seconds=3600)
    cb.record_account_challenge()
    assert cb.is_open()
    state = cb.human_reset(actor="operator", reason="reviewed")
    assert state == CircuitState.CLOSED
    reasons = [e.reason for e in cb.events()]
    assert "HUMAN_RESET" in reasons


def test_breaker_serialization_round_trip():
    cb = ProviderCircuitBreaker(cooldown_seconds=300, clock=lambda: 1000.0)
    cb.record_insufficient_credits()
    restored = ProviderCircuitBreaker.from_dict(cb.to_dict())
    assert restored.state == cb.state
    assert len(restored.events()) == len(cb.events())
