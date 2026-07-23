"""
Rule Matcher — evaluates a RoutingRuleSet against a RuleMatchContext.

RuleMatchContext carries all signal inputs defined by the plan:
    * task label
    * agent type
    * workflow type
    * required capabilities
    * estimated context
    * tool requirement
    * vision requirement
    * user-selected preference
    * cost class
    * privacy/local requirement

The matcher returns the first matching enabled rule in priority order, or
None if no rule matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet


@dataclass
class RuleMatchContext:
    """
    All context signals available to the rule matcher.

    All fields are optional / have safe defaults so callers only need to
    supply signals they have.
    """

    # Scope identity (informational; not used for matching)
    scope_id: str = ""
    scope_type: str = "session"

    # Routing signal inputs
    task_labels: List[str] = field(default_factory=list)
    agent_type: str = ""
    workflow_type: str = ""

    # Capability signals
    available_capabilities: List[str] = field(default_factory=list)
    estimated_context_tokens: int = 0
    has_tools: bool = False
    has_vision: bool = False

    # Cost / privacy signals
    cost_class: str = ""
    requires_local: bool = False
    requires_private: bool = False

    # User explicit model preference (model name string, not canonical ID)
    user_preference_model: Optional[str] = None


class RuleMatcher:
    """
    Stateless rule evaluator.

    Usage::

        matcher = RuleMatcher()
        rule = matcher.find_first_match(ruleset, context)
        if rule is None:
            raise NoMatchingRuleError(...)
    """

    def find_first_match(
        self,
        ruleset: RoutingRuleSet,
        context: RuleMatchContext,
    ) -> Optional[RoutingRule]:
        """
        Evaluate rules in priority order and return the first match.

        Returns None if no enabled rule matches the context.
        """
        for rule in ruleset.sorted_rules():
            if rule.matches(context):
                return rule
        return None

    def find_all_matches(
        self,
        ruleset: RoutingRuleSet,
        context: RuleMatchContext,
    ) -> List[RoutingRule]:
        """
        Return all matching enabled rules in priority order.
        Useful for diagnostics.
        """
        return [rule for rule in ruleset.sorted_rules() if rule.matches(context)]
