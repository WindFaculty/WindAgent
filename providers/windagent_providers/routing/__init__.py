"""
WindAgent Provider Routing Package.

Phase 7: Rule Selection and Sticky Route Lock.

Exports:
    RoutingRule, RoutingRuleSet, RulePriority, CostClass
    RouteLock, RouteLockRecord, LockScope, LockStatus
    RuleMatcher, RuleMatchContext
    RouteLockService
    NoMatchingRuleError, CanonicalModelDisabledError, LockNotFoundError
    RoutingEvent, ModelSelected, RouteLocked, RouteReused, RouteReleased,
    ModelReselectionRequested, ModelReselected
"""

from windagent_providers.routing.rules import (
    RoutingRule,
    RoutingRuleSet,
    RulePriority,
    CostClass,
)
from windagent_providers.routing.route_lock import (
    RouteLock,
    RouteLockRecord,
    LockScope,
    LockStatus,
)
from windagent_providers.routing.rule_matcher import RuleMatcher, RuleMatchContext
from windagent_providers.routing.route_lock_service import (
    RouteLockService,
    NoMatchingRuleError,
    CanonicalModelDisabledError,
    LockNotFoundError,
)
from windagent_providers.routing.events import (
    RoutingEvent,
    ModelSelected,
    RouteLocked,
    RouteReused,
    RouteReleased,
    ModelReselectionRequested,
    ModelReselected,
)

__all__ = [
    # Rules
    "RoutingRule",
    "RoutingRuleSet",
    "RulePriority",
    "CostClass",
    # Lock
    "RouteLock",
    "RouteLockRecord",
    "LockScope",
    "LockStatus",
    # Matching
    "RuleMatcher",
    "RuleMatchContext",
    # Service
    "RouteLockService",
    "NoMatchingRuleError",
    "CanonicalModelDisabledError",
    "LockNotFoundError",
    # Events
    "RoutingEvent",
    "ModelSelected",
    "RouteLocked",
    "RouteReused",
    "RouteReleased",
    "ModelReselectionRequested",
    "ModelReselected",
]

