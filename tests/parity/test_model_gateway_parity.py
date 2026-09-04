"""Frozen model-gateway semantics extracted from WindAgent commit 01695ca4.

The old implementation is a specification only and is never imported.  These
oracles capture the behavior of the production routing authority
(``providers/windagent_providers/routing/*``, ``base/errors.py``) and the
model normalizer (``core/windagent_core/contracts/providers/*``) that Phase 11
must keep:

- model-ID normalization fingerprints and equivalence classification,
- the endpoint score component sum (6.0 healthy / 5.0 quota-exhausted),
- the binding filter chain (exact-revision, credential fail-closed,
  ollama exemption),
- the same-model failover decision matrix,
- the bounded exponential cooldown backoff and Retry-After parsing,
- the rule matcher's priority-first, AND/ANY-OF predicate semantics.

Intentional V2 change (documented, not parity): the duplicate scoring
authority in ``intelligence/model_router/policy.py`` (base score 100,
+50 preferred, mock fallback) is NOT carried over — the providers routing
authority is the single survivor, per plan section 17.
"""

from __future__ import annotations

from windagent.modules.model_gateway.domain.cooldown import (
    COOLDOWN_CEILING_SECONDS,
    calculate_backoff_cooldown_seconds,
    retry_after_seconds_from_headers,
)
from windagent.modules.model_gateway.domain.errors import (
    AuthenticationFailure,
    CancellationFailure,
    ContextOverflowFailure,
    InvalidRequestFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    PermissionFailure,
    ProviderUnavailableFailure,
    QuotaExhaustedFailure,
    RateLimitFailure,
    TimeoutFailure,
)
from windagent.modules.model_gateway.domain.failover import (
    FailoverDecision,
    SameModelFailoverPolicy,
)
from windagent.modules.model_gateway.domain.normalization import (
    EquivalenceLevel,
    classify_equivalence,
    normalize_model_id,
)
from windagent.modules.model_gateway.domain.rules import (
    RoutingRule,
    RoutingRuleSet,
    RuleMatchContext,
    RuleMatcher,
)
from windagent.modules.model_gateway.domain.selection import (
    EndpointCandidate,
    binding_is_selectable,
    score_candidate,
)


class TestNormalizationParity:
    def test_openai_gpt4o_fingerprint(self) -> None:
        info = normalize_model_id("openai/gpt-4o")
        assert info.vendor == "openai"
        assert info.family == "gpt-4o"
        assert info.revision is None
        assert info.parameter_size is None
        assert info.canonical_name == "gpt-4o"
        assert info.equivalence_fingerprint == "openai:gpt-4o:base:floating:standard"

    def test_llama_size_extraction(self) -> None:
        info = normalize_model_id("meta-llama/llama-3.1-8b-instruct")
        assert info.vendor == "meta-llama"
        assert info.parameter_size == "8b"
        assert info.family == "llama-3.1-instruct"
        assert info.canonical_name == "llama-3.1-instruct-8b"
        assert info.equivalence_fingerprint == (
            "meta-llama:llama-3.1-instruct:8b:floating:standard"
        )

    def test_ollama_tag_revision(self) -> None:
        info = normalize_model_id("ollama/llama3.1:latest")
        assert info.vendor == "ollama"
        assert info.revision == "latest"
        assert info.canonical_name == "llama3.1-latest"
        assert info.equivalence_fingerprint == (
            "ollama:llama3.1:base:latest:standard"
        )

    def test_quantization_extraction(self) -> None:
        # "generic" is not a registered vendor prefix, so the raw prefix
        # survives into the family — exactly the frozen algorithm.
        info = normalize_model_id("generic/qwen3-30b-a3b-instruct-2507-fp16")
        assert info.vendor == "generic"
        assert info.quantization == "fp16"
        assert info.parameter_size == "30b"
        assert info.family == "generic/qwen3-a3b-instruct-2507"
        assert info.equivalence_fingerprint == (
            "generic:generic/qwen3-a3b-instruct-2507:30b:floating:fp16"
        )

    def test_unknown_vendor_falls_back_to_default(self) -> None:
        info = normalize_model_id("skynet/terminator-9000", default_vendor="generic")
        assert info.vendor == "generic"
        assert info.family == "skynet/terminator-9000"

    def test_equivalence_exact_fingerprint_is_failover_eligible(self) -> None:
        a = normalize_model_id("openai/gpt-4o")
        b = normalize_model_id("openai/gpt-4o")
        assessment = classify_equivalence(a, b)
        assert assessment.level is EquivalenceLevel.EXACT_REVISION
        assert assessment.confidence == 1.0
        assert assessment.is_failover_eligible is True

    def test_quantization_drift_is_not_failover_eligible(self) -> None:
        a = normalize_model_id("x/model-q4_k_m")
        b = normalize_model_id("x/model-fp16")
        assessment = classify_equivalence(a, b)
        assert assessment.level is EquivalenceLevel.EXACT_FAMILY_FLOATING_REVISION
        assert assessment.confidence == 0.85
        assert assessment.is_failover_eligible is False

    def test_revision_drift_is_not_failover_eligible(self) -> None:
        a = normalize_model_id("x/model-2024-05-13")
        b = normalize_model_id("x/model-2024-11-20")
        assessment = classify_equivalence(a, b)
        assert assessment.level is EquivalenceLevel.EXACT_FAMILY_FLOATING_REVISION
        assert assessment.confidence == 0.80
        assert assessment.is_failover_eligible is False

    def test_cross_vendor_exact_id_match_is_eligible(self) -> None:
        a = normalize_model_id("openai/gpt-4o")
        b = normalize_model_id("openrouter/gpt-4o")
        assessment = classify_equivalence(a, b)
        assert assessment.level is EquivalenceLevel.EXACT_REVISION
        assert assessment.confidence == 1.0
        assert assessment.is_failover_eligible is True

    def test_unrelated_models_are_unknown(self) -> None:
        a = normalize_model_id("openai/gpt-4o")
        b = normalize_model_id("anthropic/claude-3-5-sonnet")
        assessment = classify_equivalence(a, b)
        assert assessment.level is EquivalenceLevel.UNKNOWN
        assert assessment.confidence == 0.0
        assert assessment.is_failover_eligible is False


class TestScoringParity:
    def _candidate(self) -> EndpointCandidate:
        return EndpointCandidate(
            endpoint_id="ep-1",
            binding_id="bnd-1",
            provider_name="openai",
            provider_model_id="gpt-4o",
            base_url="https://api.openai.com/v1",
        )

    def test_component_sum_is_six_when_healthy(self) -> None:
        score, components = score_candidate(self._candidate(), quota_has_quota=True)
        # health(1) + quota(1) + priority(1) + weight(1) + success_rate(1)
        # + circuit(1); latency/cost/recent_429 stay zero placeholders.
        assert score == 6.0
        assert components == {
            "health": 1.0,
            "quota": 1.0,
            "priority": 1.0,
            "weight": 1.0,
            "latency": 0.0,
            "success_rate": 1.0,
            "cost": 0.0,
            "recent_429": 0.0,
            "circuit": 1.0,
        }

    def test_component_sum_drops_to_five_when_quota_exhausted(self) -> None:
        score, components = score_candidate(self._candidate(), quota_has_quota=False)
        assert score == 5.0
        assert components["quota"] == 0.0

    def test_missing_quota_state_is_optimistic(self) -> None:
        score, _ = score_candidate(self._candidate(), quota_has_quota=None)
        assert score == 6.0

    def test_filter_chain_order_is_frozen(self) -> None:
        common: dict[str, object] = {
            "enabled": True,
            "equivalence_level": "exact_revision",
            "has_credential": True,
            "protocol_mode": "openai",
            "endpoint_available": True,
        }
        assert binding_is_selectable(**common)  # type: ignore[arg-type]
        for broken in (
            {"enabled": False},
            {"equivalence_level": "exact_family_floating_revision"},
            {"has_credential": False},
            {"endpoint_available": False},
        ):
            assert not binding_is_selectable(**{**common, **broken})  # type: ignore[arg-type]
        # Ollama exemption is the only credentialless exception.
        assert binding_is_selectable(
            **{**common, "has_credential": False, "protocol_mode": "ollama"}  # type: ignore[arg-type]
        )


class TestFailoverParity:
    def setup_method(self) -> None:
        self.policy = SameModelFailoverPolicy()

    def test_frozen_decision_matrix(self) -> None:
        cases: tuple[tuple[object, FailoverDecision, bool, bool], ...] = (
            (RateLimitFailure(), FailoverDecision.FAILOVER, False, False),
            (QuotaExhaustedFailure(), FailoverDecision.FAILOVER, False, False),
            (AuthenticationFailure(), FailoverDecision.FAILOVER, True, False),
            (PermissionFailure(), FailoverDecision.FAILOVER, True, False),
            (ModelNotFoundFailure(), FailoverDecision.FAILOVER, False, True),
            (ContextOverflowFailure(), FailoverDecision.STOP, False, False),
            (InvalidRequestFailure(), FailoverDecision.STOP, False, False),
            (CancellationFailure(), FailoverDecision.STOP, False, False),
        )
        for failure, decision, credential, stale in cases:
            outcome = self.policy.classify(failure, 0)  # type: ignore[arg-type]
            assert outcome.decision is decision, type(failure).__name__
            assert outcome.mark_credential_invalid is credential, type(failure).__name__
            assert outcome.mark_binding_stale is stale, type(failure).__name__

    def test_transient_retry_budget_is_one_per_endpoint(self) -> None:
        for failure in (ProviderUnavailableFailure(), NetworkFailure(), TimeoutFailure()):
            assert self.policy.classify(failure, 0).decision is FailoverDecision.RETRY
            assert self.policy.classify(failure, 1).decision is FailoverDecision.FAILOVER


class TestBackoffParity:
    def test_bounded_exponential_backoff(self) -> None:
        assert calculate_backoff_cooldown_seconds(0) == 1.0
        assert calculate_backoff_cooldown_seconds(1) == 2.0
        assert calculate_backoff_cooldown_seconds(3) == 8.0
        assert calculate_backoff_cooldown_seconds(12) == COOLDOWN_CEILING_SECONDS

    def test_retry_after_defaults_and_caps(self) -> None:
        assert retry_after_seconds_from_headers(None) == 1.0
        assert retry_after_seconds_from_headers({"retry-after": "42"}) == 42.0


class TestRuleMatchingParity:
    def test_priority_order_and_first_match(self) -> None:
        rules = RoutingRuleSet(
            rules=(
                RoutingRule(
                    rule_id="default",
                    rule_version=1,
                    canonical_model_id="m0",
                    priority=50,
                ),
                RoutingRule(
                    rule_id="critical",
                    rule_version=1,
                    canonical_model_id="m1",
                    priority=0,
                    task_labels=("story",),
                ),
            )
        )
        match = RuleMatcher().find_first_match(rules, RuleMatchContext(task_labels=("story",)))
        assert match is not None and match.rule_id == "critical"
        fallback = RuleMatcher().find_first_match(rules, RuleMatchContext())
        assert fallback is not None and fallback.rule_id == "default"

    def test_no_match_yields_none(self) -> None:
        rules = RoutingRuleSet(
            rules=(
                RoutingRule(
                    rule_id="r",
                    rule_version=1,
                    canonical_model_id="m",
                    requires_local=True,
                ),
            )
        )
        assert RuleMatcher().find_first_match(rules, RuleMatchContext()) is None

