"""Narrow AgentBudgetController (Phase 2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Mapping

from windagent_core.domain.agent_loop import AgentBudgetLimits, AgentBudgetSnapshot, AgentBudgetUsage, AgentLoopLifecycle, AgentLoopState, BudgetScope, clamp_limits, utc_now
from windagent_core.errors.exceptions import ConcurrentStateConflictError


def _new_id() -> str:
    return str(uuid.uuid4())


class BudgetExhaustedError(RuntimeError):
    def __init__(self, reason: str, snapshot: Any | None = None):
        super().__init__(f"budget exhausted: {reason}")
        self.reason = reason
        self.snapshot = snapshot


class AgentBudgetController:
    def __init__(self, session_factory: Callable[[], Any], repo_factory: Callable[[Any], Any] | None = None, multi_repo_factory: Callable[[Any], Any] | None = None):
        self._session_factory = session_factory
        self._repo_factory = repo_factory
        self._multi_repo_factory = multi_repo_factory

    def _loop_repo(self, session: Any) -> Any:
        if self._repo_factory is not None:
            return self._repo_factory(session)
        raise RuntimeError("AgentLoopRepository factory not configured")

    def _multi_repo(self, session: Any) -> Any | None:
        if self._multi_repo_factory is not None:
            return self._multi_repo_factory(session)
        return None

    def _to_snapshot(self, row: Mapping[str, Any]) -> AgentBudgetSnapshot:
        limits = AgentBudgetLimits(**(row.get("budget_limits") or {}))
        usage = AgentBudgetUsage(**(row.get("budget_usage") or {}))
        scope_val = str(row.get("budget_scope") or "conversation")
        try:
            scope = BudgetScope(scope_val)
        except ValueError:
            scope = BudgetScope.CONVERSATION
        def _ensure(v: Any) -> Any:
            if isinstance(v, str):
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except Exception:
                    return None
            return v
        return AgentBudgetSnapshot(agent_run_id=str(row["agent_run_id"]), scope=scope, limits=limits, usage=usage, exhaustion_reason=row.get("exhaustion_reason"), version=int(row.get("version") or 1), started_at=_ensure(row.get("started_at")), updated_at=_ensure(row.get("updated_at")))

    async def get_snapshot(self, agent_run_id: str) -> AgentBudgetSnapshot | None:
        async with self._session_factory() as session:
            repo = self._loop_repo(session)
            row = await repo.get_loop_state(agent_run_id)
            return self._to_snapshot(row) if row else None

    async def ensure_loop(self, agent_run_id: str, *, initial_state: str = AgentLoopState.CREATED.value, limits: Any | None = None, scope: Any = BudgetScope.CONVERSATION) -> AgentBudgetSnapshot:
        if isinstance(limits, AgentBudgetLimits):
            lim_dict = limits.model_dump()
        elif isinstance(limits, Mapping):
            lim_dict = dict(limits)
        else:
            lim_dict = {}
        scope_str = scope.value if isinstance(scope, BudgetScope) else str(scope)
        async with self._session_factory() as session:
            repo = self._loop_repo(session)
            row = await repo.ensure_loop_state(agent_run_id=agent_run_id, default_state=initial_state, limits=lim_dict, scope=scope_str)
            await session.commit()
            return self._to_snapshot(row)

    async def authorize_turn(self, agent_run_id: str) -> AgentBudgetSnapshot:
        snap = await self.get_snapshot(agent_run_id)
        if snap is None:
            snap = await self.ensure_loop(agent_run_id, initial_state=AgentLoopState.RUNNING.value)
            return snap
        async with self._session_factory() as session:
            repo = self._loop_repo(session)
            row = await repo.get_loop_state(agent_run_id)
            state_val = str(row["state"]) if row else snap.scope.value
        if AgentLoopLifecycle.is_terminal(state_val):
            raise BudgetExhaustedError(f"loop terminal {state_val}", snap)
        reason = snap.is_exhausted()
        if reason is not None:
            await self._exhaust(agent_run_id, snap, reason)
            raise BudgetExhaustedError(reason, snap)
        return snap

    async def _exhaust(self, agent_run_id: str, snap: AgentBudgetSnapshot, reason: str) -> None:
        async with self._session_factory() as session:
            repo = self._loop_repo(session)
            row = await repo.get_loop_state(agent_run_id)
            if row is None or AgentLoopLifecycle.is_terminal(str(row["state"])):
                return
            try:
                AgentLoopLifecycle.transition(agent_run_id=agent_run_id, current=str(row["state"]), target=AgentLoopState.FAILED.value, current_version=int(row["version"]), expected_version=int(row["version"]), reason=reason)
                await repo.transition_loop_state(agent_run_id=agent_run_id, expected_version=int(row["version"]), target_state=AgentLoopState.FAILED.value, exhaustion_reason=reason)
                after = await repo.get_loop_state(agent_run_id)
                if after is not None:
                    await repo.update_budget_usage(agent_run_id=agent_run_id, expected_version=int(after["version"]), usage_patch=after.get("budget_usage") or {}, exhaustion_reason=reason)
                multi = self._multi_repo(session)
                if multi is not None:
                    try:
                        conv_id = await multi.conversation_id_for_agent(agent_run_id)
                        await multi.append_event(event_id=_new_id(), conversation_id=str(conv_id), event_type="agent_loop_budget_exhausted", data={"agent_run_id": agent_run_id, "reason": reason})
                    except Exception:
                        pass
                await session.commit()
            except Exception:
                await session.rollback()

    async def record_turn_tokens(self, agent_run_id: str, *, tokens: int, cost: float | None = None) -> AgentBudgetSnapshot:
        return await self._increment_usage(agent_run_id, turns_delta=1, tokens_delta=tokens, cost_delta=cost or 0.0)

    async def record_model_failure(self, agent_run_id: str) -> AgentBudgetSnapshot:
        return await self._increment_usage(agent_run_id, model_failures_delta=1)

    async def record_retry(self, agent_run_id: str) -> AgentBudgetSnapshot:
        return await self._increment_usage(agent_run_id, retries_delta=1)

    async def _increment_usage(self, agent_run_id: str, *, turns_delta: int = 0, tokens_delta: int = 0, cost_delta: float = 0.0, model_failures_delta: int = 0, tool_failures_delta: int = 0, retries_delta: int = 0) -> AgentBudgetSnapshot:
        for _ in range(3):
            snap = await self.get_snapshot(agent_run_id)
            if snap is None:
                snap = await self.ensure_loop(agent_run_id, initial_state=AgentLoopState.RUNNING.value)
            new_usage = AgentBudgetUsage(turns_used=snap.usage.turns_used + turns_delta, tokens_used=snap.usage.tokens_used + tokens_delta, cost_used=snap.usage.cost_used + cost_delta, model_failures=snap.usage.model_failures + model_failures_delta, tool_failures=snap.usage.tool_failures + tool_failures_delta, retries_used=snap.usage.retries_used + retries_delta, child_agents_spawned=snap.usage.child_agents_spawned, recursion_depth=snap.usage.recursion_depth, parallel_children_current=snap.usage.parallel_children_current, parallel_children_max_observed=snap.usage.parallel_children_max_observed)
            reason = AgentBudgetSnapshot(agent_run_id=snap.agent_run_id, scope=snap.scope, limits=snap.limits, usage=new_usage, version=snap.version, started_at=snap.started_at).is_exhausted()
            async with self._session_factory() as session:
                repo = self._loop_repo(session)
                updated = await repo.update_budget_usage(agent_run_id=agent_run_id, expected_version=snap.version, usage_patch=new_usage.model_dump(), exhaustion_reason=reason)
                if updated is None:
                    continue
                if reason is not None:
                    cur_state = str(updated["state"])
                    if not AgentLoopLifecycle.is_terminal(cur_state):
                        try:
                            AgentLoopLifecycle.transition(agent_run_id=agent_run_id, current=cur_state, target=AgentLoopState.FAILED.value, current_version=int(updated["version"]), expected_version=int(updated["version"]), reason=reason)
                            await repo.transition_loop_state(agent_run_id=agent_run_id, expected_version=int(updated["version"]), target_state=AgentLoopState.FAILED.value, exhaustion_reason=reason)
                            updated = await repo.get_loop_state(agent_run_id)
                        except Exception:
                            pass
                await session.commit()
                return self._to_snapshot(updated)
        raise ConcurrentStateConflictError(f"failed to update usage for {agent_run_id}")

    async def derive_child_budget(self, parent_agent_run_id: str, child_agent_run_id: str, requested_limits: Any | None = None, *, scope: Any = BudgetScope.CHILD) -> AgentBudgetSnapshot:
        parent_snap = await self.get_snapshot(parent_agent_run_id)
        if parent_snap is None:
            parent_snap = await self.ensure_loop(parent_agent_run_id)
        if isinstance(requested_limits, Mapping) and not isinstance(requested_limits, AgentBudgetLimits):
            req = AgentBudgetLimits(**requested_limits)
        elif isinstance(requested_limits, AgentBudgetLimits):
            req = requested_limits
        else:
            req = AgentBudgetLimits()
        effective = clamp_limits(parent_snap.limits, req)
        if parent_snap.limits.max_parallel_children is not None and parent_snap.usage.parallel_children_current >= parent_snap.limits.max_parallel_children:
            raise BudgetExhaustedError("max_parallel_children_exhausted", parent_snap)
        if parent_snap.limits.max_child_agents is not None and parent_snap.usage.child_agents_spawned >= parent_snap.limits.max_child_agents:
            raise BudgetExhaustedError("max_child_agents_exhausted", parent_snap)
        child_depth = parent_snap.usage.recursion_depth + 1
        if effective.max_recursion_depth is not None and child_depth > effective.max_recursion_depth:
            raise BudgetExhaustedError("max_recursion_depth_exhausted", parent_snap)
        scope_str = scope.value if isinstance(scope, BudgetScope) else str(scope)
        async with self._session_factory() as session:
            repo = self._loop_repo(session)
            row = await repo.create_loop_state(agent_run_id=child_agent_run_id, state=AgentLoopState.CREATED.value, limits=effective.model_dump(), usage=AgentBudgetUsage(recursion_depth=child_depth).model_dump(), scope=scope_str, started_at=utc_now())
            await session.commit()
        for _ in range(3):
            p_snap = await self.get_snapshot(parent_agent_run_id)
            if p_snap is None:
                break
            new_usage = AgentBudgetUsage(turns_used=p_snap.usage.turns_used, tokens_used=p_snap.usage.tokens_used, cost_used=p_snap.usage.cost_used, model_failures=p_snap.usage.model_failures, tool_failures=p_snap.usage.tool_failures, retries_used=p_snap.usage.retries_used, child_agents_spawned=p_snap.usage.child_agents_spawned + 1, recursion_depth=p_snap.usage.recursion_depth, parallel_children_current=p_snap.usage.parallel_children_current + 1, parallel_children_max_observed=max(p_snap.usage.parallel_children_max_observed, p_snap.usage.parallel_children_current + 1))
            async with self._session_factory() as session:
                repo = self._loop_repo(session)
                updated = await repo.update_budget_usage(agent_run_id=parent_agent_run_id, expected_version=p_snap.version, usage_patch=new_usage.model_dump())
                if updated is not None:
                    await session.commit()
                    break
        return self._to_snapshot(row)

    async def release_parallel_slot(self, parent_agent_run_id: str) -> None:
        for _ in range(3):
            snap = await self.get_snapshot(parent_agent_run_id)
            if snap is None:
                return
            new_current = max(0, snap.usage.parallel_children_current - 1)
            new_usage = snap.usage.model_copy(update={"parallel_children_current": new_current})
            async with self._session_factory() as session:
                repo = self._loop_repo(session)
                updated = await repo.update_budget_usage(agent_run_id=parent_agent_run_id, expected_version=snap.version, usage_patch=new_usage.model_dump())
                if updated is not None:
                    await session.commit()
                    return
