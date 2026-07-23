"""
Routing Events for Phase 7 — emitted by RouteLockService on every state change.

Events capture the full audit trail required by the plan:
    ModelSelected
    RouteLocked
    RouteReused
    RouteReleased
    ModelReselectionRequested
    ModelReselected
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RoutingEvent:
    """Base class for all routing events."""
    event_type: str
    scope_id: str
    scope_type: str
    lock_id: Optional[str]
    timestamp: float = field(default_factory=time.time)


@dataclass
class ModelSelected(RoutingEvent):
    """Emitted when the rule matcher selects a canonical model for the first time."""
    canonical_model_id: str = ""
    rule_id: str = ""
    rule_version: int = 0
    reason: str = ""

    def __init__(
        self,
        scope_id: str,
        scope_type: str,
        lock_id: Optional[str],
        canonical_model_id: str,
        rule_id: str,
        rule_version: int,
        reason: str = "",
    ):
        super().__init__(
            event_type="ModelSelected",
            scope_id=scope_id,
            scope_type=scope_type,
            lock_id=lock_id,
        )
        self.canonical_model_id = canonical_model_id
        self.rule_id = rule_id
        self.rule_version = rule_version
        self.reason = reason


@dataclass
class RouteLocked(RoutingEvent):
    """Emitted when the route lock record is atomically committed."""
    canonical_model_id: str = ""

    def __init__(
        self,
        scope_id: str,
        scope_type: str,
        lock_id: str,
        canonical_model_id: str,
    ):
        super().__init__(
            event_type="RouteLocked",
            scope_id=scope_id,
            scope_type=scope_type,
            lock_id=lock_id,
        )
        self.canonical_model_id = canonical_model_id


@dataclass
class RouteReused(RoutingEvent):
    """Emitted on every subsequent turn that reads an existing lock."""
    canonical_model_id: str = ""
    turn_number: int = 0

    def __init__(
        self,
        scope_id: str,
        scope_type: str,
        lock_id: str,
        canonical_model_id: str,
        turn_number: int = 0,
    ):
        super().__init__(
            event_type="RouteReused",
            scope_id=scope_id,
            scope_type=scope_type,
            lock_id=lock_id,
        )
        self.canonical_model_id = canonical_model_id
        self.turn_number = turn_number


@dataclass
class RouteReleased(RoutingEvent):
    """Emitted when a lock is explicitly unlocked."""
    canonical_model_id: str = ""

    def __init__(
        self,
        scope_id: str,
        scope_type: str,
        lock_id: str,
        canonical_model_id: str,
    ):
        super().__init__(
            event_type="RouteReleased",
            scope_id=scope_id,
            scope_type=scope_type,
            lock_id=lock_id,
        )
        self.canonical_model_id = canonical_model_id


@dataclass
class ModelReselectionRequested(RoutingEvent):
    """Emitted when caller requests an explicit model reselection."""
    previous_canonical_model_id: str = ""
    reason: str = ""

    def __init__(
        self,
        scope_id: str,
        scope_type: str,
        lock_id: Optional[str],
        previous_canonical_model_id: str,
        reason: str = "",
    ):
        super().__init__(
            event_type="ModelReselectionRequested",
            scope_id=scope_id,
            scope_type=scope_type,
            lock_id=lock_id,
        )
        self.previous_canonical_model_id = previous_canonical_model_id
        self.reason = reason


@dataclass
class ModelReselected(RoutingEvent):
    """Emitted when reselection completes and a new lock is committed."""
    previous_canonical_model_id: str = ""
    new_canonical_model_id: str = ""
    rule_id: str = ""
    rule_version: int = 0
    reason: str = ""

    def __init__(
        self,
        scope_id: str,
        scope_type: str,
        lock_id: str,
        previous_canonical_model_id: str,
        new_canonical_model_id: str,
        rule_id: str,
        rule_version: int,
        reason: str = "",
    ):
        super().__init__(
            event_type="ModelReselected",
            scope_id=scope_id,
            scope_type=scope_type,
            lock_id=lock_id,
        )
        self.previous_canonical_model_id = previous_canonical_model_id
        self.new_canonical_model_id = new_canonical_model_id
        self.rule_id = rule_id
        self.rule_version = rule_version
        self.reason = reason
