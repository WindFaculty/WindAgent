"""
Routing Rules — RoutingRule and RoutingRuleSet for Phase 7.

A RoutingRule maps a RequestContext predicate onto a canonical model selection.
Rules have explicit versions so that rule updates do NOT retroactively affect
existing route locks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set


class RulePriority(int, Enum):
    """Evaluation priority (lower number = evaluated first)."""
    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 100


class CostClass(str, Enum):
    """Budget classification for cost-aware routing."""
    ECONOMY = "economy"
    STANDARD = "standard"
    PREMIUM = "premium"


@dataclass
class RoutingRule:
    """
    Single rule mapping request context predicates → canonical model.

    Fields
    ------
    rule_id         : Stable identifier (survives restart).
    rule_version    : Monotonically increasing. Locked routes remember the
                      version that produced them; rule updates do not
                      retroactively change active locks.
    enabled         : Disabled rules are skipped during evaluation.
    priority        : Lower value = higher priority.
    canonical_model_id : Target canonical model ID to select when this rule
                         matches. Must be registered in CanonicalModelRegistry.

    Predicates (all optional; omitting = wildcard match):
    task_labels     : Required task labels (AND).
    agent_types     : Allowed agent types (ANY-OF).
    workflow_types  : Allowed workflow types (ANY-OF).
    required_capabilities : Required model capabilities (AND).
    min_context_tokens    : Minimum estimated context size.
    requires_tools        : True = model must support tool_use.
    requires_vision       : True = model must support vision.
    cost_classes          : Allowed cost classes (ANY-OF).
    requires_local        : True = only local/Ollama endpoints.
    requires_private      : True = only privacy-safe endpoints.
    user_preference_model : Match when user explicitly requested this model.
    """

    rule_id: str
    rule_version: int
    canonical_model_id: str

    # Metadata
    description: str = ""
    enabled: bool = True
    priority: int = RulePriority.NORMAL

    # Predicates
    task_labels: List[str] = field(default_factory=list)
    agent_types: List[str] = field(default_factory=list)
    workflow_types: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    min_context_tokens: int = 0
    requires_tools: bool = False
    requires_vision: bool = False
    cost_classes: List[str] = field(default_factory=list)
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: Optional[str] = None

    def matches(self, ctx: "RuleMatchContext") -> bool:  # noqa: F821
        """Return True iff this rule's predicates are satisfied by ctx."""
        if not self.enabled:
            return False

        # task_labels: all specified labels must be present in context
        if self.task_labels:
            if not all(lbl in ctx.task_labels for lbl in self.task_labels):
                return False

        # agent_types: any-of
        if self.agent_types:
            if ctx.agent_type not in self.agent_types:
                return False

        # workflow_types: any-of
        if self.workflow_types:
            if ctx.workflow_type not in self.workflow_types:
                return False

        # required_capabilities: all must be present
        if self.required_capabilities:
            if not all(cap in ctx.available_capabilities for cap in self.required_capabilities):
                return False

        # min context size
        if self.min_context_tokens > 0:
            if ctx.estimated_context_tokens < self.min_context_tokens:
                return False

        # tool requirement
        if self.requires_tools and not ctx.has_tools:
            return False

        # vision requirement
        if self.requires_vision and not ctx.has_vision:
            return False

        # cost class
        if self.cost_classes:
            if ctx.cost_class not in self.cost_classes:
                return False

        # local/private
        if self.requires_local and not ctx.requires_local:
            return False
        if self.requires_private and not ctx.requires_private:
            return False

        # user explicit preference
        if self.user_preference_model is not None:
            if ctx.user_preference_model != self.user_preference_model:
                return False

        return True


@dataclass
class RoutingRuleSet:
    """
    An ordered collection of RoutingRules.

    Rules are evaluated in ascending priority order.  The first matching
    *enabled* rule wins.  The ruleset itself is immutable after construction
    (individual rules may be enabled/disabled by replacing the set).
    """

    rules: List[RoutingRule] = field(default_factory=list)

    def sorted_rules(self) -> List[RoutingRule]:
        """Return enabled rules sorted by priority ascending."""
        return sorted(
            [r for r in self.rules if r.enabled],
            key=lambda r: r.priority,
        )
