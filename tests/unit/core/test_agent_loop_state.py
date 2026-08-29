"""Unit tests for durable agent loop state machine (Phase 2)."""

import pytest

from windagent_core.domain.agent_loop import (
    AgentLoopState,
    AgentLoopLifecycle,
    AgentBudgetLimits,
    AgentBudgetUsage,
    AgentBudgetSnapshot,
    BudgetScope,
    clamp_limits,
    inherit_snapshot,
)
from windagent_core.errors.exceptions import (
    InvalidStateTransitionError,
    TerminalStateMutationError,
    ConcurrentStateConflictError,
)


def test_legal_transitions_all_required_paths():
    for src, dst in [
        (AgentLoopState.CREATED, AgentLoopState.READY),
        (AgentLoopState.READY, AgentLoopState.RUNNING),
        (AgentLoopState.RUNNING, AgentLoopState.WAITING_TOOL),
        (AgentLoopState.RUNNING, AgentLoopState.WAITING_CHILD),
        (AgentLoopState.RUNNING, AgentLoopState.WAITING_SCHEDULE),
        (AgentLoopState.RUNNING, AgentLoopState.COMPACTING),
        (AgentLoopState.RUNNING, AgentLoopState.PAUSED),
        (AgentLoopState.RUNNING, AgentLoopState.COMPLETED),
        (AgentLoopState.WAITING_TOOL, AgentLoopState.RUNNING),
        (AgentLoopState.WAITING_CHILD, AgentLoopState.RUNNING),
        (AgentLoopState.WAITING_SCHEDULE, AgentLoopState.RUNNING),
        (AgentLoopState.COMPACTING, AgentLoopState.RUNNING),
        (AgentLoopState.PAUSED, AgentLoopState.RUNNING),
        (AgentLoopState.RUNNING, AgentLoopState.FAILED),
        (AgentLoopState.RUNNING, AgentLoopState.CANCELLED),
        (AgentLoopState.RUNNING, AgentLoopState.ORPHANED),
    ]:
        assert AgentLoopLifecycle.can_transition(src, dst) is True
        res = AgentLoopLifecycle.transition(
            agent_run_id="run-legal", current=src, target=dst, current_version=1
        )
        assert res.new_version == 2


def test_illegal_transitions_rejected():
    illegal = [
        (AgentLoopState.CREATED, AgentLoopState.RUNNING),
        (AgentLoopState.READY, AgentLoopState.WAITING_TOOL),
        (AgentLoopState.COMPLETED, AgentLoopState.RUNNING),
        (AgentLoopState.FAILED, AgentLoopState.RUNNING),
        (AgentLoopState.CANCELLED, AgentLoopState.RUNNING),
        (AgentLoopState.ORPHANED, AgentLoopState.READY),
        (AgentLoopState.PAUSED, AgentLoopState.COMPACTING),
    ]
    for src, dst in illegal:
        with pytest.raises((InvalidStateTransitionError, TerminalStateMutationError)):
            AgentLoopLifecycle.transition(
                agent_run_id="run-illegal", current=src, target=dst, current_version=1
            )


def test_terminal_states_have_no_outgoing():
    for terminal in [
        AgentLoopState.COMPLETED,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
        AgentLoopState.ORPHANED,
    ]:
        assert AgentLoopLifecycle.is_terminal(terminal) is True
        with pytest.raises(TerminalStateMutationError):
            AgentLoopLifecycle.transition(
                agent_run_id="run-terminal",
                current=terminal,
                target=AgentLoopState.RUNNING,
                current_version=1,
            )


def test_cas_stale_version_rejected():
    with pytest.raises(ConcurrentStateConflictError):
        AgentLoopLifecycle.transition(
            agent_run_id="run-cas",
            current=AgentLoopState.RUNNING,
            target=AgentLoopState.PAUSED,
            current_version=2,
            expected_version=1,
        )


def test_budget_clamping_tightens_only():
    parent = AgentBudgetLimits(max_turns=10, max_tokens=1000, max_cost_usd=5.0)
    child_loose = AgentBudgetLimits(max_turns=20, max_tokens=5000)
    clamped = clamp_limits(parent, child_loose)
    assert clamped.max_turns == 10
    assert clamped.max_tokens == 1000
    parent_unlimited = AgentBudgetLimits(max_turns=None)
    child_tight = AgentBudgetLimits(max_turns=5)
    assert clamp_limits(parent_unlimited, child_tight).max_turns == 5
    child_none = AgentBudgetLimits(max_turns=None)
    assert clamp_limits(parent, child_none).max_turns == 10


def test_child_cannot_self_create_unlimited_when_parent_finite():
    parent = AgentBudgetLimits(max_parallel_children=2)
    child_req = AgentBudgetLimits(max_parallel_children=None)
    clamped = clamp_limits(parent, child_req)
    assert clamped.max_parallel_children == 2


def test_inherit_snapshot_sets_recursion_and_scope():
    parent_snap = AgentBudgetSnapshot(
        agent_run_id="parent",
        scope=BudgetScope.CONVERSATION,
        limits=AgentBudgetLimits(max_recursion_depth=3, max_child_agents=5),
        usage=AgentBudgetUsage(recursion_depth=1, child_agents_spawned=0),
        version=1,
    )
    child = inherit_snapshot(
        parent_snapshot=parent_snap,
        child_agent_run_id="child",
        child_requested_limits=AgentBudgetLimits(max_recursion_depth=10),
        child_scope=BudgetScope.CHILD,
    )
    assert child.limits.max_recursion_depth == 3
    assert child.usage.recursion_depth == 2
    assert child.scope == BudgetScope.CHILD


def test_budget_exhaustion_detection():
    snap = AgentBudgetSnapshot(
        agent_run_id="run-exhaust",
        limits=AgentBudgetLimits(max_turns=2, max_tokens=10),
        usage=AgentBudgetUsage(turns_used=2, tokens_used=5),
        version=1,
    )
    assert snap.is_exhausted() == "max_turns_exhausted"
    snap2 = AgentBudgetSnapshot(
        agent_run_id="run-exhaust2",
        limits=AgentBudgetLimits(max_tokens=10),
        usage=AgentBudgetUsage(tokens_used=10),
        version=1,
    )
    assert snap2.is_exhausted() == "max_tokens_exhausted"
