"""The rule-based policy engine: explicit rules, fail-closed by default.

Evaluation is deterministic: rules are ordered by descending priority and
then by stable ``policy_id``; the first match wins.  When no rule matches,
the engine returns DENY — a missing rule can never silently authorize an
operation (plan section 13: tool execution must pass the Policy Engine).
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import PolicyDecision, PolicyEffect, PolicyEngine, PolicyRequest

DEFAULT_DENY_POLICY_ID = "default-deny"


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """One authorization rule over (action, resource_type) pairs.

    ``action`` and ``resource_type`` are exact matches or the ``*``
    wildcard; nothing fancier, so rule sets stay auditable.
    """

    policy_id: str
    action: str
    resource_type: str
    effect: PolicyEffect
    priority: int = 0
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _required_text(self.policy_id, "policy_id"))
        object.__setattr__(self, "action", _required_text(self.action, "action"))
        object.__setattr__(
            self, "resource_type", _required_text(self.resource_type, "resource_type")
        )
        if not isinstance(self.effect, PolicyEffect):
            raise TypeError("effect must be a PolicyEffect")
        if self.reason is not None:
            object.__setattr__(self, "reason", _required_text(self.reason, "reason"))

    def matches(self, request: PolicyRequest) -> bool:
        """Return whether this rule covers ``request``."""
        action_ok = self.action == "*" or self.action == request.action
        resource_ok = (
            self.resource_type == "*" or self.resource_type == request.resource_type
        )
        return action_ok and resource_ok


@dataclass(frozen=True, slots=True)
class RuleBasedPolicyEngine(PolicyEngine):
    """Evaluate an immutable rule set with deny-by-default semantics."""

    rules: tuple[PolicyRule, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.rules, tuple):
            raise TypeError("rules must be a tuple")
        if any(not isinstance(rule, PolicyRule) for rule in self.rules):
            raise TypeError("rules must contain only PolicyRule values")
        object.__setattr__(
            self,
            "rules",
            tuple(
                sorted(self.rules, key=lambda rule: (-rule.priority, rule.policy_id))
            ),
        )

    async def decide(self, request: PolicyRequest) -> PolicyDecision:
        if not isinstance(request, PolicyRequest):
            raise TypeError("request must be a PolicyRequest")
        for rule in self.rules:
            if rule.matches(request):
                return PolicyDecision(
                    effect=rule.effect,
                    reason=rule.reason,
                    policy_id=rule.policy_id,
                )
        return PolicyDecision(
            effect=PolicyEffect.DENY,
            reason="no policy rule matched this operation",
            policy_id=DEFAULT_DENY_POLICY_ID,
        )
