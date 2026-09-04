"""Rule-based policy engine contracts (fail-closed evaluation)."""

from __future__ import annotations

import pytest
from windagent.kernel.ids import ActorId
from windagent.platform.security import (
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
    PolicyRule,
    RuleBasedPolicyEngine,
)


def _request(action: str = "job:submit", resource_type: str = "job") -> PolicyRequest:
    return PolicyRequest(action=action, resource_type=resource_type, actor_id=ActorId.new())


def _engine() -> RuleBasedPolicyEngine:
    return RuleBasedPolicyEngine(
        rules=(
            PolicyRule(
                policy_id="ops-submit",
                action="job:submit",
                resource_type="job",
                effect=PolicyEffect.ALLOW,
                priority=10,
                reason="ops may submit",
            ),
            PolicyRule(
                policy_id="freeze-deny",
                action="job:submit",
                resource_type="job",
                effect=PolicyEffect.DENY,
                priority=100,
                reason="submit frozen",
            ),
            PolicyRule(
                policy_id="approval-gate",
                action="tool:shell",
                resource_type="*",
                effect=PolicyEffect.REQUIRE_APPROVAL,
            ),
        )
    )


async def test_engine_is_a_policy_engine() -> None:
    assert isinstance(_engine(), PolicyEngine)


async def test_first_matching_rule_by_priority_wins() -> None:
    decision = await _engine().decide(_request())
    assert decision.effect is PolicyEffect.DENY
    assert decision.policy_id == "freeze-deny"
    assert decision.reason == "submit frozen"


async def test_unmatched_operations_fail_closed() -> None:
    decision = await _engine().decide(_request(action="episode:delete"))
    assert decision.effect is PolicyEffect.DENY
    assert decision.policy_id == "default-deny"


async def test_resource_wildcard_matches_every_resource() -> None:
    decision = await _engine().decide(
        _request(action="tool:shell", resource_type="shell")
    )
    assert decision.effect is PolicyEffect.REQUIRE_APPROVAL
    assert decision.policy_id == "approval-gate"


async def test_action_wildcard_covers_all_actions() -> None:
    engine = RuleBasedPolicyEngine(
        rules=(
            PolicyRule(
                policy_id="read-only",
                action="*",
                resource_type="report",
                effect=PolicyEffect.ALLOW,
            ),
        )
    )
    assert (await engine.decide(_request(action="x", resource_type="report"))).effect is (
        PolicyEffect.ALLOW
    )


def test_ties_break_by_policy_id_for_determinism() -> None:
    engine = RuleBasedPolicyEngine(
        rules=(
            PolicyRule(
                policy_id="b-rule",
                action="job:submit",
                resource_type="job",
                effect=PolicyEffect.ALLOW,
            ),
            PolicyRule(
                policy_id="a-rule",
                action="job:submit",
                resource_type="job",
                effect=PolicyEffect.DENY,
            ),
        )
    )
    assert engine.rules[0].policy_id == "a-rule"


async def test_empty_rule_engine_denies_everything() -> None:
    decision = await RuleBasedPolicyEngine(rules=()).decide(_request())
    assert decision.effect is PolicyEffect.DENY


def test_rule_validation() -> None:
    with pytest.raises(TypeError):
        PolicyRule(policy_id="x", action="a", resource_type="r", effect="allow")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PolicyRule(policy_id=" ", action="a", resource_type="r", effect=PolicyEffect.ALLOW)


async def test_engine_rejects_non_requests() -> None:
    with pytest.raises(TypeError):
        await _engine().decide("not-a-request")  # type: ignore[arg-type]


def test_decision_requires_reason_discipline() -> None:
    with pytest.raises(TypeError):
        PolicyDecision(effect="allow")  # type: ignore[arg-type]
