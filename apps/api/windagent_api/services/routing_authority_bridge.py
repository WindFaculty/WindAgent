"""Routing authority bridge — maps the durable V3 routing-rules authority onto
the composed ``RouteLockService`` runtime ruleset.

Phase 4 (P4-R4A): ``v3_resources:routing_rules`` is the durable canonical
authority for API-managed routing rules. ``RouteLockService``'s
``RoutingRuleSet`` is only a rebuildable runtime projection/cache of those SQL
rules. This bridge maps every durable ``routing_rules`` record to a
``RoutingRule`` (preserving all supported predicates and using the durable
record version as ``rule_version``) and rebuilds the composed ruleset at the
required seams.

The ruleset is deliberately non-authoritative: if SQL has no API-managed rules,
the composed immutable deployment fallback ruleset is restored rather than
inventing demo data in production or leaving the runtime projection empty.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_api.services.v3_demo_seed import NS_ROUTING_RULES
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet


class RoutingAuthorityBridge:
    """Bridges the durable SQL routing-rules authority to the runtime ruleset."""

    def __init__(
        self,
        resource_service: V3ResourceService,
        route_lock_service: RouteLockService,
    ) -> None:
        self._resource_service = resource_service
        self._route_lock_service = route_lock_service
        # Capture an immutable copy of the composed deployment fallback
        # ruleset. SQL rules replace the runtime projection while any exist;
        # when SQL becomes empty this captured fallback is restored (never an
        # empty ruleset, never a stale deleted API rule).
        self._deployment_fallback = route_lock_service.current_ruleset

    @staticmethod
    def _rule_to_routing_rule(r: Dict[str, Any]) -> RoutingRule:
        """Map a durable ``routing_rules`` record to a ``RoutingRule``.

        Every supported predicate is preserved and the durable record version
        becomes ``rule_version``. No demo rule IDs are hardcoded here.
        """
        return RoutingRule(
            rule_id=r["id"],
            rule_version=r.get("version", 1),
            canonical_model_id=r.get("canonical_model_id", ""),
            description=r.get("description", ""),
            enabled=r.get("enabled", True),
            priority=r.get("priority", 50),
            task_labels=r.get("task_labels", []),
            agent_types=r.get("agent_types", []),
            workflow_types=r.get("workflow_types", []),
            required_capabilities=r.get("required_capabilities", []),
            min_context_tokens=r.get("min_context_tokens", 0),
            requires_tools=r.get("requires_tools", False),
            requires_vision=r.get("requires_vision", False),
            cost_classes=r.get("cost_classes", []),
            requires_local=r.get("requires_local", False),
            requires_private=r.get("requires_private", False),
            user_preference_model=r.get("user_preference_model"),
        )

    async def refresh_ruleset(self) -> RoutingRuleSet:
        """Rebuild the composed ``RouteLockService`` ruleset from the SQL authority.

        The durable SQL ``routing_rules`` records are canonical while any
        exist. When SQL has no API-managed rules, the captured immutable
        deployment fallback ruleset is restored so the runtime projection is
        never empty and deleted API rules are never retained.
        """
        rules = await self._resource_service.list(NS_ROUTING_RULES)
        if rules:
            ruleset = RoutingRuleSet(
                rules=[self._rule_to_routing_rule(r) for r in rules]
            )
        else:
            ruleset = self._deployment_fallback
        self._route_lock_service.update_ruleset(ruleset)
        return ruleset

    async def get_projected_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Resolve projected rule metadata for ``rule_id``.

        Returns the durable SQL record when the rule is API-managed, otherwise
        the matching rule from the captured deployment fallback ruleset. This
        read-only seam lets callers build responses for either a SQL-backed
        rule or the immutable deployment fallback without persisting the
        fallback into generic SQL.
        """
        rule = await self._resource_service.get(NS_ROUTING_RULES, rule_id)
        if rule is not None:
            return rule
        for r in self._deployment_fallback.rules:
            if r.rule_id == rule_id:
                return {
                    "id": r.rule_id,
                    "name": r.rule_id,
                    "version": r.rule_version,
                    "canonical_model_id": r.canonical_model_id,
                    "description": r.description,
                    "enabled": r.enabled,
                    "priority": r.priority,
                    "task_labels": list(r.task_labels),
                    "agent_types": list(r.agent_types),
                    "workflow_types": list(r.workflow_types),
                    "required_capabilities": list(r.required_capabilities),
                    "min_context_tokens": r.min_context_tokens,
                    "requires_tools": r.requires_tools,
                    "requires_vision": r.requires_vision,
                    "cost_classes": list(r.cost_classes),
                    "requires_local": r.requires_local,
                    "requires_private": r.requires_private,
                    "user_preference_model": r.user_preference_model,
                }
        return None


__all__ = ["RoutingAuthorityBridge"]
