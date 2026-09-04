"""Routing rules and the stateless rule matcher.

REWRITE of the frozen ``providers/windagent_providers/routing/rules.py`` and
``rule_matcher.py``.  Matching semantics are preserved exactly: enabled rules
evaluate in ascending priority order, the first match wins, predicates are
AND within a field and ANY-OF across list fields.  Rule updates never
retroactively change active locks because locks capture the rule version
that produced them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class RulePriority(IntEnum):
    """Evaluation priority (lower number = evaluated first)."""

    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 100


class CostClass(StrEnum):
    """Budget classification for cost-aware routing."""

    ECONOMY = "economy"
    STANDARD = "standard"
    PREMIUM = "premium"


@dataclass(frozen=True, slots=True)
class RuleMatchContext:
    """All context signals available to the rule matcher.

    Fields default to wildcard/empty so callers only supply signals they
    have.  ``scope_type``/``scope_id`` are informational and never matched.
    """

    scope_id: str = ""
    scope_type: str = "session"

    task_labels: tuple[str, ...] = ()
    agent_type: str = ""
    workflow_type: str = ""

    available_capabilities: tuple[str, ...] = ()
    estimated_context_tokens: int = 0
    has_tools: bool = False
    has_vision: bool = False

    cost_class: str = ""
    requires_local: bool = False
    requires_private: bool = False

    user_preference_model: str | None = None


@dataclass(frozen=True, slots=True)
class RoutingRule:
    """One rule mapping request-context predicates onto a canonical model.

    ``rule_version`` is monotonic: a lock remembers the version that created
    it, so updating a rule never rewrites history.  ``fallback_model_id`` is
    never used for matching — it is carried so the executor may fail over to
    another model on eligible transient failures (P0.3.5 semantics).
    """

    rule_id: str
    rule_version: int
    canonical_model_id: str

    description: str = ""
    enabled: bool = True
    priority: int = int(RulePriority.NORMAL)

    fallback_model_id: str | None = None

    task_labels: tuple[str, ...] = ()
    agent_types: tuple[str, ...] = ()
    workflow_types: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    min_context_tokens: int = 0
    requires_tools: bool = False
    requires_vision: bool = False
    cost_classes: tuple[str, ...] = ()
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: str | None = None

    def matches(self, ctx: RuleMatchContext) -> bool:
        """Return True iff every configured predicate is satisfied."""
        if not self.enabled:
            return False

        if self.task_labels and not all(label in ctx.task_labels for label in self.task_labels):
            return False

        if self.agent_types and ctx.agent_type not in self.agent_types:
            return False

        if self.workflow_types and ctx.workflow_type not in self.workflow_types:
            return False

        if self.required_capabilities and not all(
            capability in ctx.available_capabilities
            for capability in self.required_capabilities
        ):
            return False

        if self.min_context_tokens > 0 and ctx.estimated_context_tokens < self.min_context_tokens:
            return False

        if self.requires_tools and not ctx.has_tools:
            return False

        if self.requires_vision and not ctx.has_vision:
            return False

        if self.cost_classes and ctx.cost_class not in self.cost_classes:
            return False

        if self.requires_local and not ctx.requires_local:
            return False

        if self.requires_private and not ctx.requires_private:
            return False

        if self.user_preference_model is not None and (
            ctx.user_preference_model != self.user_preference_model
        ):
            return False

        return True


@dataclass(frozen=True, slots=True)
class RoutingRuleSet:
    """An immutable, ordered collection of routing rules."""

    rules: tuple[RoutingRule, ...] = field(default=())

    def sorted_rules(self) -> tuple[RoutingRule, ...]:
        """Return enabled rules sorted by ascending priority."""
        return tuple(
            sorted(
                (rule for rule in self.rules if rule.enabled),
                key=lambda rule: rule.priority,
            )
        )


class RuleMatcher:
    """Stateless rule evaluator: first enabled match in priority order wins."""

    def find_first_match(
        self, ruleset: RoutingRuleSet, context: RuleMatchContext
    ) -> RoutingRule | None:
        """Return the first matching enabled rule, or ``None``."""
        for rule in ruleset.sorted_rules():
            if rule.matches(context):
                return rule
        return None

    def find_all_matches(
        self, ruleset: RoutingRuleSet, context: RuleMatchContext
    ) -> tuple[RoutingRule, ...]:
        """Return every matching enabled rule in priority order (diagnostics)."""
        return tuple(
            rule for rule in ruleset.sorted_rules() if rule.matches(context)
        )
