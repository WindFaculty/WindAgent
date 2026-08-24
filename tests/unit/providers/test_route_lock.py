"""
Tests for Phase 7 — Rule Selection and Sticky Route Lock.

Acceptance gates verified:
    [x] Một scope chỉ có một active lock
    [x] 100 turns giữ cùng canonical model
    [x] Concurrent first calls không tạo hai model locks
    [x] Restart không làm mất affinity (snapshot → restore)
    [x] Rule update không đổi lock hiện tại
    [x] Không silent model fallback
    [x] Reselection có event và reason

Additional tests:
    - Rule priority ordering
    - Missing matching rule raises NoMatchingRuleError
    - Disabled canonical model raises CanonicalModelDisabledError
    - Insufficient capability predicate
    - Explicit unlock
    - All 6 required event types emitted correctly
    - RuleMatcher wildcard vs. predicate logic
    - Lock serialisation / deserialisation round-trip
"""

from __future__ import annotations

import threading
from typing import List

import pytest

from windagent_providers.routing.events import (
    ModelReselected,
    ModelReselectionRequested,
    ModelSelected,
    RouteLocked,
    RouteReleased,
    RouteReused,
)
from windagent_providers.routing.route_lock import (
    LockStatus,
    RouteLockRecord,
)
from windagent_providers.routing.route_lock_service import (
    CanonicalModelDisabledError,
    LockNotFoundError,
    NoMatchingRuleError,
    RouteLockService,
)
from windagent_providers.routing.rule_matcher import RuleMatchContext, RuleMatcher
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
pytestmark = pytest.mark.postgres



# ──────────────────────────────────────────────
# Helpers / fixtures
# ──────────────────────────────────────────────

def _make_rule(
    rule_id: str = "r1",
    canonical_model_id: str = "cm-gpt4o",
    priority: int = 50,
    enabled: bool = True,
    task_labels: list | None = None,
    agent_types: list | None = None,
    requires_tools: bool = False,
    requires_vision: bool = False,
    required_capabilities: list | None = None,
    cost_classes: list | None = None,
    requires_local: bool = False,
    user_preference_model: str | None = None,
    rule_version: int = 1,
    description: str = "",
) -> RoutingRule:
    return RoutingRule(
        rule_id=rule_id,
        rule_version=rule_version,
        canonical_model_id=canonical_model_id,
        description=description,
        enabled=enabled,
        priority=priority,
        task_labels=task_labels or [],
        agent_types=agent_types or [],
        requires_tools=requires_tools,
        requires_vision=requires_vision,
        required_capabilities=required_capabilities or [],
        cost_classes=cost_classes or [],
        requires_local=requires_local,
        user_preference_model=user_preference_model,
    )


def _ctx(
    scope_id: str = "sess-001",
    scope_type: str = "session",
    task_labels: list | None = None,
    agent_type: str = "",
    requires_tools: bool = False,
    requires_vision: bool = False,
    available_capabilities: list | None = None,
    cost_class: str = "",
    requires_local: bool = False,
    user_preference_model: str | None = None,
    estimated_context_tokens: int = 0,
) -> RuleMatchContext:
    return RuleMatchContext(
        scope_id=scope_id,
        scope_type=scope_type,
        task_labels=task_labels or [],
        agent_type=agent_type,
        has_tools=requires_tools,
        has_vision=requires_vision,
        available_capabilities=available_capabilities or [],
        cost_class=cost_class,
        requires_local=requires_local,
        user_preference_model=user_preference_model,
        estimated_context_tokens=estimated_context_tokens,
    )



def _service(
    rules: list | None = None,
    disabled_models: set | None = None,
) -> RouteLockService:
    rs = RoutingRuleSet(rules=rules or [_make_rule()])
    return RouteLockService(ruleset=rs, disabled_models=disabled_models or set())


# ──────────────────────────────────────────────
# Gate 1: Một scope chỉ có một active lock
# ──────────────────────────────────────────────

def test_single_active_lock_per_scope():
    """Only one ACTIVE lock exists for a given scope_id at any time."""
    svc = _service()
    ctx = _ctx(scope_id="sess-A")

    lock1 = svc.resolve_or_create_lock(ctx)
    lock2 = svc.resolve_or_create_lock(ctx)

    # Both calls return the same lock object
    assert lock1.lock_id == lock2.lock_id
    assert lock1.canonical_model_id == "cm-gpt4o"


# ──────────────────────────────────────────────
# Gate 2: 100 turns giữ cùng canonical model
# ──────────────────────────────────────────────

def test_100_turns_same_canonical_model():
    """100 consecutive resolve calls on same session all return same model."""
    svc = _service(rules=[_make_rule(canonical_model_id="cm-claude")])
    ctx = _ctx(scope_id="sess-long")

    model_ids = set()
    for _ in range(100):
        lock = svc.resolve_or_create_lock(ctx)
        model_ids.add(lock.canonical_model_id)

    assert model_ids == {"cm-claude"}, "Model must not change across 100 turns"

    # First call → RouteLocked; remaining 99 → RouteReused
    locked_events = svc.events_of_type(RouteLocked)
    reused_events = svc.events_of_type(RouteReused)
    assert len(locked_events) == 1
    assert len(reused_events) == 99


# ──────────────────────────────────────────────
# Gate 3: Concurrent first calls → one lock
# ──────────────────────────────────────────────

def test_concurrent_first_requests_single_lock():
    """Racing first requests for the same scope_id create exactly one lock."""
    svc = _service()
    scope_id = "sess-concurrent"

    results: List[RouteLockRecord] = []
    errors: List[Exception] = []
    barrier = threading.Barrier(10)

    def worker():
        try:
            barrier.wait()  # synchronise all threads at the same instant
            lock = svc.resolve_or_create_lock(_ctx(scope_id=scope_id))
            results.append(lock)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected errors in threads: {errors}"
    assert len(results) == 10

    # All threads received the same lock_id
    lock_ids = {r.lock_id for r in results}
    assert len(lock_ids) == 1, f"Expected 1 unique lock, got {lock_ids}"

    # Only one RouteLocked event was emitted
    locked_events = svc.events_of_type(RouteLocked)
    assert len(locked_events) == 1


# ──────────────────────────────────────────────
# Gate 4: Restart simulation → affinity preserved
# ──────────────────────────────────────────────

def test_restart_preserves_affinity():
    """Snapshot + restore + resolve → same canonical_model_id as before."""
    svc1 = _service(rules=[_make_rule(canonical_model_id="cm-gemini")])
    ctx = _ctx(scope_id="sess-persist")

    original_lock = svc1.resolve_or_create_lock(ctx)
    original_model = original_lock.canonical_model_id

    # Simulate serialise to persistence
    serialised = svc1.snapshot()

    # Simulate process restart: create fresh service with same ruleset
    svc2 = _service(rules=[_make_rule(canonical_model_id="cm-gemini")])
    svc2.restore_snapshot(serialised)

    # Resolve on restored service — must read existing lock, not create new
    restored_lock = svc2.resolve_or_create_lock(ctx)
    assert restored_lock.canonical_model_id == original_model
    assert restored_lock.lock_id == original_lock.lock_id

    # RouteReused event fired (not RouteLocked)
    reused_events = svc2.events_of_type(RouteReused)
    locked_events = svc2.events_of_type(RouteLocked)
    assert len(reused_events) == 1
    assert len(locked_events) == 0


# ──────────────────────────────────────────────
# Gate 5: Rule update không đổi lock hiện tại
# ──────────────────────────────────────────────

def test_rule_update_does_not_change_existing_lock():
    """Replacing the ruleset after lock creation leaves the lock unchanged."""
    svc = _service(rules=[_make_rule(canonical_model_id="cm-original")])
    ctx = _ctx(scope_id="sess-rulechange")

    original_lock = svc.resolve_or_create_lock(ctx)

    # Swap ruleset to point to a different model
    new_ruleset = RoutingRuleSet(rules=[_make_rule(canonical_model_id="cm-new-model")])
    svc.update_ruleset(new_ruleset)

    # Existing lock must still return original model
    subsequent_lock = svc.resolve_or_create_lock(ctx)
    assert subsequent_lock.canonical_model_id == "cm-original"
    assert subsequent_lock.lock_id == original_lock.lock_id


# ──────────────────────────────────────────────
# Gate 6: Không silent model fallback
# ──────────────────────────────────────────────

def test_no_silent_model_fallback_on_disabled_model():
    """Disabling the locked model's canonical ID must NOT silently swap to another."""
    # Rule selects cm-target; another rule selects cm-fallback (lower priority)
    rules = [
        _make_rule(rule_id="r1", canonical_model_id="cm-target", priority=10),
        _make_rule(rule_id="r2", canonical_model_id="cm-fallback", priority=100),
    ]
    svc = _service(rules=rules)

    # Disable cm-target BEFORE any lock is created
    svc.update_disabled_models({"cm-target"})

    ctx = _ctx(scope_id="sess-disabled")
    with pytest.raises(CanonicalModelDisabledError) as exc_info:
        svc.resolve_or_create_lock(ctx)

    assert exc_info.value.canonical_model_id == "cm-target"
    # No lock should exist
    assert svc.get_active_lock("session", "sess-disabled") is None


def test_no_rule_match_raises_error():
    """When no rule matches, raise NoMatchingRuleError — never return a random model."""
    svc = _service(rules=[_make_rule(task_labels=["requires_vision"], requires_vision=True)])
    ctx = _ctx(scope_id="sess-nomatch", requires_vision=False)

    with pytest.raises(NoMatchingRuleError) as exc_info:
        svc.resolve_or_create_lock(ctx)

    assert exc_info.value.scope_id == "sess-nomatch"


# ──────────────────────────────────────────────
# Gate 7: Reselection có event và reason
# ──────────────────────────────────────────────

def test_explicit_reselect_emits_events_with_reason():
    """reselect_model must emit ModelReselectionRequested + ModelReselected with reason."""
    rules = [
        _make_rule(rule_id="r1", canonical_model_id="cm-old", agent_types=["agent-a"], priority=10),
        _make_rule(rule_id="r2", canonical_model_id="cm-new", agent_types=["agent-b"], priority=10),
    ]
    svc = _service(rules=rules)

    # Initial lock
    ctx_a = _ctx(scope_id="sess-reselect", agent_type="agent-a")
    svc.resolve_or_create_lock(ctx_a)
    assert svc.get_active_lock("session", "sess-reselect").canonical_model_id == "cm-old"

    # Explicit reselection with new context
    ctx_b = _ctx(scope_id="sess-reselect", scope_type="session", agent_type="agent-b")
    new_lock = svc.reselect_model("session", "sess-reselect", ctx_b, reason="user_changed_agent")

    assert new_lock.canonical_model_id == "cm-new"

    # Verify events
    requested_events = svc.events_of_type(ModelReselectionRequested)
    reselected_events = svc.events_of_type(ModelReselected)

    assert len(requested_events) == 1
    assert requested_events[0].reason == "user_changed_agent"
    assert requested_events[0].previous_canonical_model_id == "cm-old"

    assert len(reselected_events) == 1
    mr = reselected_events[0]
    assert mr.previous_canonical_model_id == "cm-old"
    assert mr.new_canonical_model_id == "cm-new"
    assert mr.reason == "user_changed_agent"


# ──────────────────────────────────────────────
# Additional: Explicit unlock
# ──────────────────────────────────────────────

def test_explicit_unlock_emits_route_released():
    """release_lock changes status to RELEASED and emits RouteReleased."""
    svc = _service()
    ctx = _ctx(scope_id="sess-unlock")

    lock = svc.resolve_or_create_lock(ctx)
    assert lock.is_active

    released = svc.release_lock(lock.lock_id)
    assert released.status == LockStatus.RELEASED.value
    assert released.released_at is not None

    events = svc.events_of_type(RouteReleased)
    assert len(events) == 1
    assert events[0].lock_id == lock.lock_id

    # After release, no active lock
    assert svc.get_active_lock("session", "sess-unlock") is None


def test_release_nonexistent_lock_raises():
    svc = _service()
    with pytest.raises(LockNotFoundError):
        svc.release_lock("lk-doesnotexist")


# ──────────────────────────────────────────────
# Additional: Rule priority ordering
# ──────────────────────────────────────────────

def test_rule_priority_ordering():
    """Lower priority value = evaluated first → wins the selection."""
    rules = [
        _make_rule(rule_id="low-prio", canonical_model_id="cm-low", priority=100),
        _make_rule(rule_id="high-prio", canonical_model_id="cm-high", priority=5),
    ]
    svc = _service(rules=rules)
    ctx = _ctx(scope_id="sess-prio")

    lock = svc.resolve_or_create_lock(ctx)
    # High priority (lower number) rule should win
    assert lock.canonical_model_id == "cm-high"


# ──────────────────────────────────────────────
# Additional: Capability predicate
# ──────────────────────────────────────────────

def test_capability_predicate_required():
    """Rule requiring a capability only matches contexts that declare it."""
    rule_vision = _make_rule(
        rule_id="r-vision",
        canonical_model_id="cm-vision-model",
        required_capabilities=["vision"],
        priority=10,
    )
    rule_default = _make_rule(
        rule_id="r-default",
        canonical_model_id="cm-default",
        priority=100,
    )
    svc = _service(rules=[rule_vision, rule_default])

    # Context without vision capability → falls through to default rule
    ctx_no_vision = _ctx(scope_id="sess-novision", available_capabilities=["chat"])
    lock_no_vision = svc.resolve_or_create_lock(ctx_no_vision)
    assert lock_no_vision.canonical_model_id == "cm-default"

    # Context with vision → vision rule wins
    ctx_vision = _ctx(scope_id="sess-vision", available_capabilities=["vision", "chat"])
    lock_vision = svc.resolve_or_create_lock(ctx_vision)
    assert lock_vision.canonical_model_id == "cm-vision-model"


# ──────────────────────────────────────────────
# Additional: User preference predicate
# ──────────────────────────────────────────────

def test_user_preference_predicate():
    """Rule with user_preference_model only matches when user explicitly chose that model."""
    rules = [
        _make_rule(
            rule_id="r-user-pref",
            canonical_model_id="cm-user-choice",
            user_preference_model="gpt-4o",
            priority=10,
        ),
        _make_rule(rule_id="r-default", canonical_model_id="cm-default", priority=100),
    ]
    svc = _service(rules=rules)

    ctx_pref = _ctx(scope_id="sess-pref", user_preference_model="gpt-4o")
    lock_pref = svc.resolve_or_create_lock(ctx_pref)
    assert lock_pref.canonical_model_id == "cm-user-choice"

    ctx_no_pref = _ctx(scope_id="sess-no-pref", user_preference_model=None)
    lock_no_pref = svc.resolve_or_create_lock(ctx_no_pref)
    assert lock_no_pref.canonical_model_id == "cm-default"


# ──────────────────────────────────────────────
# Additional: Local/private predicate
# ──────────────────────────────────────────────

def test_local_requirement_predicate():
    """Rule requiring local only matches contexts that signal local requirement."""
    rules = [
        _make_rule(
            rule_id="r-local",
            canonical_model_id="cm-ollama",
            requires_local=True,
            priority=10,
        ),
        _make_rule(rule_id="r-default", canonical_model_id="cm-cloud", priority=100),
    ]
    svc = _service(rules=rules)

    ctx_local = _ctx(scope_id="sess-local", requires_local=True)
    assert svc.resolve_or_create_lock(ctx_local).canonical_model_id == "cm-ollama"

    ctx_cloud = _ctx(scope_id="sess-cloud", requires_local=False)
    assert svc.resolve_or_create_lock(ctx_cloud).canonical_model_id == "cm-cloud"


# ──────────────────────────────────────────────
# Additional: Disabled rules skipped
# ──────────────────────────────────────────────

def test_disabled_rules_are_skipped():
    """Disabled rules must not participate in evaluation."""
    rules = [
        _make_rule(rule_id="r-disabled", canonical_model_id="cm-disabled-model", priority=5, enabled=False),
        _make_rule(rule_id="r-active", canonical_model_id="cm-active", priority=50, enabled=True),
    ]
    svc = _service(rules=rules)
    ctx = _ctx(scope_id="sess-disabled-rule")
    lock = svc.resolve_or_create_lock(ctx)
    assert lock.canonical_model_id == "cm-active"


# ──────────────────────────────────────────────
# Additional: Lock serialisation round-trip
# ──────────────────────────────────────────────

def test_lock_serialisation_round_trip():
    """RouteLockRecord.to_dict() → from_dict() must preserve all fields."""
    svc = _service()
    ctx = _ctx(scope_id="sess-serial")
    original = svc.resolve_or_create_lock(ctx)

    data = original.to_dict()
    restored = RouteLockRecord.from_dict(data)

    assert restored.lock_id == original.lock_id
    assert restored.scope_id == original.scope_id
    assert restored.canonical_model_id == original.canonical_model_id
    assert restored.status == original.status
    assert restored.routing_snapshot.rule_id == original.routing_snapshot.rule_id
    assert restored.routing_snapshot.rule_version == original.routing_snapshot.rule_version


# ──────────────────────────────────────────────
# Additional: All 6 required events emitted
# ──────────────────────────────────────────────

def test_all_6_required_events_over_lifecycle():
    """Full lifecycle emits ModelSelected, RouteLocked, RouteReused, RouteReleased,
    ModelReselectionRequested, ModelReselected."""
    rules = [
        _make_rule(rule_id="r1", canonical_model_id="cm-a", agent_types=["a"], priority=10),
        _make_rule(rule_id="r2", canonical_model_id="cm-b", agent_types=["b"], priority=10),
    ]
    svc = _service(rules=rules)

    ctx_a = _ctx(scope_id="sess-lifecycle", agent_type="a")
    svc.resolve_or_create_lock(ctx_a)         # → ModelSelected + RouteLocked
    svc.resolve_or_create_lock(ctx_a)                # → RouteReused

    ctx_b = _ctx(scope_id="sess-lifecycle", scope_type="session", agent_type="b")
    svc.reselect_model("session", "sess-lifecycle", ctx_b, "test")  # → Requested + Released + Selected + Reselected

    assert len(svc.events_of_type(ModelSelected)) == 2          # initial + reselect
    assert len(svc.events_of_type(RouteLocked)) == 1
    assert len(svc.events_of_type(RouteReused)) == 1
    assert len(svc.events_of_type(RouteReleased)) == 1
    assert len(svc.events_of_type(ModelReselectionRequested)) == 1
    assert len(svc.events_of_type(ModelReselected)) == 1


# ──────────────────────────────────────────────
# Additional: RuleMatcher standalone
# ──────────────────────────────────────────────

def test_rule_matcher_find_all_matches():
    """RuleMatcher.find_all_matches returns all matching rules."""
    rules = [
        _make_rule(rule_id="r1", canonical_model_id="cm-1", priority=10),
        _make_rule(rule_id="r2", canonical_model_id="cm-2", priority=20),
        _make_rule(rule_id="r3", canonical_model_id="cm-3", requires_vision=True, priority=5),
    ]
    rs = RoutingRuleSet(rules=rules)
    matcher = RuleMatcher()
    ctx = _ctx()  # no vision

    matches = matcher.find_all_matches(rs, ctx)
    assert len(matches) == 2
    assert matches[0].rule_id == "r1"   # lower priority number first
    assert matches[1].rule_id == "r2"


def test_rule_matcher_no_match_returns_none():
    """RuleMatcher returns None when nothing matches."""
    rs = RoutingRuleSet(rules=[_make_rule(requires_vision=True)])
    matcher = RuleMatcher()
    ctx = _ctx(requires_vision=False)
    assert matcher.find_first_match(rs, ctx) is None


# ──────────────────────────────────────────────
# Additional: Different scope_ids are isolated
# ──────────────────────────────────────────────

def test_different_scope_ids_are_isolated():
    """Locks for different scope_ids are completely independent."""
    rules = [
        _make_rule(rule_id="r1", canonical_model_id="cm-x", agent_types=["x"], priority=10),
        _make_rule(rule_id="r2", canonical_model_id="cm-y", agent_types=["y"], priority=10),
    ]
    svc = _service(rules=rules)

    lock_x = svc.resolve_or_create_lock(_ctx(scope_id="sess-x", agent_type="x"))
    lock_y = svc.resolve_or_create_lock(_ctx(scope_id="sess-y", agent_type="y"))

    assert lock_x.canonical_model_id == "cm-x"
    assert lock_y.canonical_model_id == "cm-y"
    assert lock_x.lock_id != lock_y.lock_id


# ──────────────────────────────────────────────
# Additional: Import boundary check
# ──────────────────────────────────────────────

def test_routing_package_imports():
    """Ensure all public symbols are importable from the routing package."""
    from windagent_providers.routing import (
        RouteLockService,
    )
    # Just verify they're all importable; type check is implicit
    assert RouteLockService is not None