"""Routing-policy projection from SQL ModelRules (Phase 10).

``RoutingPolicyProjection`` maps the durable per-role ``ModelRuleRecord`` rows
into the runtime ``RoutingRuleSet`` consumed by ``RouteLockService``. The SQL
role rules are authoritative when no explicit override is supplied; the
projection is a rebuildable runtime cache, never a second authority.
"""

from __future__ import annotations

import json

from windagent_core.contracts.providers.provider_management import (
    ModelRuleRecord,
    ProviderManagementRepositoryPort,
)
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet


class RoutingPolicyProjection:
    """Project enabled SQL ModelRules into a RouteLockService ruleset."""

    def __init__(self, repository: ProviderManagementRepositoryPort) -> None:
        self._repository = repository

    def load_ruleset(self) -> RoutingRuleSet:
        """Load enabled SQL role rules deterministically into a ruleset."""
        rules = [
            self._rule_to_routing_rule(r)
            for r in self._repository.list_enabled_model_rules()
        ]
        return RoutingRuleSet(rules=rules)

    def has_sql_rules(self) -> bool:
        """True when the SQL authority holds at least one enabled role rule."""
        return bool(self._repository.list_enabled_model_rules())

    @staticmethod
    def _rule_to_routing_rule(r: ModelRuleRecord) -> RoutingRule:
        policy: dict = {}
        try:
            policy = json.loads(r.policy_json) if r.policy_json else {}
        except (TypeError, ValueError):
            policy = {}
        return RoutingRule(
            rule_id=f"role-{r.role}",
            rule_version=int(policy.get("version", 1)),
            canonical_model_id=r.primary_canonical_model_id,
            description=r.description or r.name,
            enabled=r.enabled,
            priority=r.priority,
            agent_types=policy.get("agent_types", []),
            # RouteLockedModelPort exposes the requested role/capability as a
            # task label. A dedicated SQL role therefore matches Worker
            # requests without relying on an unset agent_type field.
            task_labels=policy.get("task_labels") or [r.role],
            workflow_types=policy.get("workflow_types", []),
            required_capabilities=policy.get("required_capabilities", []),
            min_context_tokens=int(policy.get("min_context_tokens", 0)),
            requires_tools=bool(policy.get("requires_tools", False)),
            requires_vision=bool(policy.get("requires_vision", False)),
            cost_classes=policy.get("cost_classes", []),
            requires_local=bool(policy.get("requires_local", False)),
            requires_private=bool(policy.get("requires_private", False)),
            user_preference_model=policy.get("user_preference_model"),
        )


__all__ = ["RoutingPolicyProjection"]
