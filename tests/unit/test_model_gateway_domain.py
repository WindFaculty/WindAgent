"""Offline unit tests for the model-gateway domain layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from windagent.modules.model_gateway.domain.circuit import (
    CIRCUIT_CLOSED,
    CIRCUIT_OPEN,
    CircuitBreakerPolicy,
    EndpointRuntimeState,
)
from windagent.modules.model_gateway.domain.cooldown import (
    COOLDOWN_CEILING_SECONDS,
    calculate_backoff_cooldown_seconds,
    rate_limit_cooldown_seconds,
    retry_after_seconds_from_headers,
)
from windagent.modules.model_gateway.domain.errors import (
    AuthenticationFailure,
    CancellationFailure,
    ContextOverflowFailure,
    InvalidRequestFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    ProviderUnavailableFailure,
    QuotaExhaustedFailure,
    RateLimitFailure,
    TimeoutFailure,
)
from windagent.modules.model_gateway.domain.failover import (
    FailoverDecision,
    SameModelFailoverPolicy,
)
from windagent.modules.model_gateway.domain.route_lock import (
    LockStatus,
    RouteLockRecord,
    RoutingSnapshot,
)
from windagent.modules.model_gateway.domain.rules import (
    RoutingRule,
    RoutingRuleSet,
    RuleMatchContext,
    RuleMatcher,
    RulePriority,
)
from windagent.modules.model_gateway.domain.selection import (
    EndpointCandidate,
    binding_is_selectable,
    score_candidate,
)

NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)


def _rule(rule_id: str, **overrides: object) -> RoutingRule:
    defaults: dict[str, object] = {
        "rule_id": rule_id,
        "rule_version": 3,
        "canonical_model_id": "windagent/story-default",
    }
    defaults.update(overrides)
    return RoutingRule(**defaults)  # type: ignore[arg-type]


class TestRoutingRules:
    def test_first_enabled_match_in_priority_order_wins(self) -> None:
        low = _rule("low", priority=int(RulePriority.LOW))
        critical = _rule("critical", priority=int(RulePriority.CRITICAL))
        ruleset = RoutingRuleSet(rules=(low, critical))
        match = RuleMatcher().find_first_match(ruleset, RuleMatchContext())
        assert match is not None
        assert match.rule_id == "critical"

    def test_disabled_rules_are_skipped(self) -> None:
        ruleset = RoutingRuleSet(rules=(_rule("off", enabled=False), _rule("on")))
        match = RuleMatcher().find_first_match(ruleset, RuleMatchContext())
        assert match is not None
        assert match.rule_id == "on"

    def test_no_match_returns_none(self) -> None:
        ruleset = RoutingRuleSet(rules=(_rule("r", agent_types=("coder",)),))
        assert RuleMatcher().find_first_match(ruleset, RuleMatchContext()) is None

    def test_task_labels_are_all_of(self) -> None:
        rule = _rule("r", task_labels=("story", "long_form"))
        assert rule.matches(RuleMatchContext(task_labels=("story", "long_form", "x")))
        assert not rule.matches(RuleMatchContext(task_labels=("story",)))

    def test_capability_and_context_predicates(self) -> None:
        rule = _rule(
            "r",
            required_capabilities=("tool_use",),
            min_context_tokens=1000,
            requires_tools=True,
        )
        strong = RuleMatchContext(
            available_capabilities=("tool_use", "vision"),
            estimated_context_tokens=2000,
            has_tools=True,
        )
        weak = RuleMatchContext(estimated_context_tokens=500)
        assert rule.matches(strong)
        assert not rule.matches(weak)

    def test_privacy_and_preference_predicates(self) -> None:
        rule = _rule(
            "r",
            requires_private=True,
            user_preference_model="windagent/private-default",
        )
        assert rule.matches(
            RuleMatchContext(
                requires_private=True, user_preference_model="windagent/private-default"
            )
        )
        assert not rule.matches(RuleMatchContext(requires_private=True))


class TestEndpointScoring:
    def test_healthy_candidate_scores_six(self) -> None:
        candidate = EndpointCandidate(
            endpoint_id="ep-1",
            binding_id="bnd-1",
            provider_name="openai",
            provider_model_id="gpt-4o",
            base_url="https://api.openai.com/v1",
        )
        score, components = score_candidate(candidate, quota_has_quota=True)
        assert score == 6.0
        assert components["health"] == 1.0
        assert components["quota"] == 1.0
        assert components["circuit"] == 1.0

    def test_exhausted_quota_scores_five(self) -> None:
        candidate = EndpointCandidate(
            endpoint_id="ep-1",
            binding_id="bnd-1",
            provider_name="openai",
            provider_model_id="gpt-4o",
            base_url="https://api.openai.com/v1",
        )
        score, components = score_candidate(candidate, quota_has_quota=False)
        assert score == 5.0
        assert components["quota"] == 0.0


class TestBindingFilterChain:
    def test_chain_accepts_a_fully_qualified_binding(self) -> None:
        assert binding_is_selectable(
            enabled=True,
            equivalence_level="exact_revision",
            has_credential=True,
            protocol_mode="openai",
            endpoint_available=True,
        )

    def test_chain_rejects_disabled_or_non_exact_or_unavailable(self) -> None:
        common: dict[str, object] = {
            "enabled": True,
            "equivalence_level": "exact_revision",
            "has_credential": True,
            "protocol_mode": "openai",
            "endpoint_available": True,
        }
        assert not binding_is_selectable(**{**common, "enabled": False})  # type: ignore[arg-type]
        assert not binding_is_selectable(
            **{**common, "equivalence_level": "exact_family_floating_revision"}  # type: ignore[arg-type]
        )
        assert not binding_is_selectable(**{**common, "endpoint_available": False})  # type: ignore[arg-type]

    def test_missing_credential_fails_closed_except_ollama(self) -> None:
        common: dict[str, object] = {
            "enabled": True,
            "equivalence_level": "exact_revision",
            "has_credential": False,
            "endpoint_available": True,
        }
        assert not binding_is_selectable(protocol_mode="openai", **common)  # type: ignore[arg-type]
        assert binding_is_selectable(protocol_mode="ollama", **common)  # type: ignore[arg-type]


class TestFailoverPolicy:
    def setup_method(self) -> None:
        self.policy = SameModelFailoverPolicy()

    def test_rate_limit_and_quota_failover(self) -> None:
        for failure in (RateLimitFailure(), QuotaExhaustedFailure()):
            outcome = self.policy.classify(failure, 0)
            assert outcome.decision is FailoverDecision.FAILOVER

    def test_transient_failures_retry_once_then_failover(self) -> None:
        for failure in (
            ProviderUnavailableFailure(),
            NetworkFailure(),
            TimeoutFailure(),
        ):
            retry = self.policy.classify(failure, 0)
            failover = self.policy.classify(failure, 1)
            assert retry.decision is FailoverDecision.RETRY
            assert failover.decision is FailoverDecision.FAILOVER

    def test_auth_failover_marks_credential_invalid(self) -> None:
        outcome = self.policy.classify(AuthenticationFailure(), 0)
        assert outcome.decision is FailoverDecision.FAILOVER
        assert outcome.mark_credential_invalid is True

    def test_model_not_found_marks_binding_stale(self) -> None:
        outcome = self.policy.classify(ModelNotFoundFailure(), 0)
        assert outcome.decision is FailoverDecision.FAILOVER
        assert outcome.mark_binding_stale is True

    def test_stop_decisions(self) -> None:
        for failure in (
            ContextOverflowFailure(),
            InvalidRequestFailure(),
            CancellationFailure(),
        ):
            assert self.policy.classify(failure, 0).decision is FailoverDecision.STOP


class TestCooldowns:
    def test_backoff_doubles_and_caps(self) -> None:
        assert calculate_backoff_cooldown_seconds(0) == 1.0
        assert calculate_backoff_cooldown_seconds(1) == 2.0
        assert calculate_backoff_cooldown_seconds(2) == 4.0
        assert calculate_backoff_cooldown_seconds(20) == COOLDOWN_CEILING_SECONDS
        assert calculate_backoff_cooldown_seconds(20, base=5.0) == (
            COOLDOWN_CEILING_SECONDS
        )

    def test_retry_after_parsing(self) -> None:
        assert retry_after_seconds_from_headers(None) == 1.0
        assert retry_after_seconds_from_headers({}) == 1.0
        assert retry_after_seconds_from_headers({"retry-after": "7"}) == 7.0
        assert (
            retry_after_seconds_from_headers({"Rate-Limit-Reset": "9"}) == 9.0
        )
        # HTTP-date values clamp to the frozen 1.0s default.
        assert (
            retry_after_seconds_from_headers(
                {"Retry-After": "Wed, 02 Sep 2026 12:00:00 GMT"}
            )
            == 1.0
        )

    def test_rate_limit_cooldown_is_capped(self) -> None:
        assert rate_limit_cooldown_seconds({"retry-after": "9999"}) == (
            COOLDOWN_CEILING_SECONDS
        )


class TestCircuitBreaker:
    def test_circuit_opens_at_threshold_and_recovers_on_success(self) -> None:
        policy = CircuitBreakerPolicy(failure_threshold=3, half_open_timeout_s=30.0)
        state = EndpointRuntimeState()
        for _ in range(2):
            state = policy.after_failure(state, NOW, error_class="network")
        assert state.circuit_state(NOW) == CIRCUIT_CLOSED
        assert policy.is_available(state, NOW)

        state = policy.after_failure(state, NOW, error_class="network")
        assert state.circuit_state(NOW) == CIRCUIT_OPEN
        assert not policy.is_available(state, NOW)
        assert not policy.is_available(state, NOW + timedelta(seconds=29))
        assert policy.is_available(state, NOW + timedelta(seconds=30))

        state = policy.after_success(state, NOW, latency_ms=12.0)
        assert state.circuit_state(NOW) == CIRCUIT_CLOSED
        assert state.consecutive_failures == 0

    def test_cooldown_only_extends(self) -> None:
        policy = CircuitBreakerPolicy()
        state = policy.with_cooldown(
            EndpointRuntimeState(), NOW + timedelta(seconds=10)
        )
        state = policy.with_cooldown(state, NOW + timedelta(seconds=5))
        assert state.cooldown_until == NOW + timedelta(seconds=10)


class TestRouteLockRecord:
    def test_serialization_round_trip(self) -> None:
        lock = RouteLockRecord(
            lock_id="00000000-0000-0000-0000-000000000001",
            scope_type="task",
            scope_id="task-1",
            canonical_model_id="windagent/story-default",
            routing_snapshot=RoutingSnapshot(
                rule_id="story-default",
                rule_version=2,
                canonical_model_id="windagent/story-default",
                selected_at=123.0,
                reason="matched rule story-default",
            ),
            created_at=123.0,
        )
        restored = RouteLockRecord.from_dict(lock.to_dict())
        assert restored.lock_id == lock.lock_id
        assert restored.canonical_model_id == lock.canonical_model_id
        assert restored.routing_snapshot.rule_id == "story-default"
        assert restored.routing_snapshot.rule_version == 2
        assert restored.is_active
        assert restored.status == LockStatus.ACTIVE.value
