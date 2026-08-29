"""Durable parent->child delegation controller (Phase 4)."""
from __future__ import annotations
import uuid
from typing import Any, Callable, Mapping
from windagent_core.domain.agent_loop import AgentBudgetLimits, AgentLoopState, BudgetScope
from windagent_core.domain.delegation import ChildFailurePolicy, DelegationContext, DelegationHandle, DelegationRecord, DelegationSummary, project_bounded_context, resolve_root_and_depth
def _new_id() -> str:
    return str(uuid.uuid4())
class DelegationError(RuntimeError):
    pass
class DelegationController:
    def __init__(self, session_factory: Callable[[], Any], delegation_repo_factory: Callable[[Any], Any], agent_loop_repo_factory: Callable[[Any], Any] | None = None, multi_repo_factory: Callable[[Any], Any] | None = None, budget_controller_factory: Callable[[], Any] | None = None) -> None:
        self._session_factory = session_factory
        self._delegation_repo_factory = delegation_repo_factory
        self._agent_loop_repo_factory = agent_loop_repo_factory
        self._multi_repo_factory = multi_repo_factory
        self._budget_controller_factory = budget_controller_factory
    def _delegation_repo(self, session: Any) -> Any:
        return self._delegation_repo_factory(session)
    def _loop_repo(self, session: Any) -> Any | None:
        if self._agent_loop_repo_factory is not None:
            return self._agent_loop_repo_factory(session)
        return None
    def _multi_repo(self, session: Any) -> Any | None:
        if self._multi_repo_factory is not None:
            return self._multi_repo_factory(session)
        return None
    def _budget_controller(self) -> Any | None:
        if self._budget_controller_factory is not None:
            try:
                return self._budget_controller_factory()
            except Exception:
                return None
        if self._agent_loop_repo_factory is not None:
            from windagent_orchestration.agent_loop.budget_controller import AgentBudgetController
            return AgentBudgetController(session_factory=self._session_factory, repo_factory=self._agent_loop_repo_factory, multi_repo_factory=self._multi_repo_factory)
        return None
    async def spawn_child(self, *, parent_agent_run_id: str, child_agent_run_id: str | None = None, goal: str, subtask: str, delegation_reason: str, relevant_artifacts: list[str] | tuple[str, ...] | None = None, selected_memory: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None, policy: Mapping[str, Any] | None = None, skills: list[str] | tuple[str, ...] | None = None, requested_budget: AgentBudgetLimits | Mapping[str, Any] | None = None, failure_policy: ChildFailurePolicy | str = ChildFailurePolicy.FAIL_PARENT) -> DelegationHandle:
        if isinstance(failure_policy, str):
            try:
                failure_policy = ChildFailurePolicy(failure_policy)
            except ValueError as exc:
                raise DelegationError(f"unknown failure_policy {failure_policy}") from exc
        parent_agent_run_id = str(parent_agent_run_id).strip()
        if not parent_agent_run_id:
            raise DelegationError("parent_agent_run_id must not be empty")
        delegation_reason = str(delegation_reason).strip() or subtask.strip()
        if not delegation_reason:
            raise DelegationError("delegation_reason must not be empty")
        child_id = str(child_agent_run_id or _new_id()).strip()
        if not child_id:
            child_id = _new_id()
        async with self._session_factory() as session:
            repo = self._delegation_repo(session)
            parent_delegation_row = None
            try:
                parent_delegation_row = await repo.get_delegation_by_child(parent_agent_run_id)
            except Exception:
                parent_delegation_row = None
            parent_record: DelegationRecord | None = None
            if parent_delegation_row is not None:
                try:
                    parent_record = DelegationRecord(child_agent_run_id=str(parent_delegation_row["child_agent_run_id"]), parent_agent_run_id=str(parent_delegation_row["parent_agent_run_id"]), root_agent_run_id=str(parent_delegation_row["root_agent_run_id"]), delegation_depth=int(parent_delegation_row["delegation_depth"]), delegation_reason=str(parent_delegation_row["delegation_reason"]), failure_policy=ChildFailurePolicy(str(parent_delegation_row.get("failure_policy") or "fail_parent")), allocated_budget=AgentBudgetLimits(**(parent_delegation_row.get("allocated_budget") or {})) if parent_delegation_row.get("allocated_budget") else None)
                except Exception:
                    parent_record = None
            root_id, depth = resolve_root_and_depth(parent_record, parent_agent_run_id)
        allocated: AgentBudgetLimits | None = None
        budget_controller = self._budget_controller()
        if budget_controller is not None:
            try:
                parent_snap = await budget_controller.get_snapshot(parent_agent_run_id)
                if parent_snap is None:
                    parent_snap = await budget_controller.ensure_loop(parent_agent_run_id, initial_state=AgentLoopState.RUNNING.value)
                child_snap = await budget_controller.derive_child_budget(parent_agent_run_id, child_id, requested_limits=requested_budget, scope=BudgetScope.CHILD)
                allocated = child_snap.limits
            except Exception as exc:
                from windagent_orchestration.agent_loop.budget_controller import BudgetExhaustedError
                if isinstance(exc, BudgetExhaustedError):
                    raise DelegationError(f"budget exhausted: {exc.reason}") from exc
                if "no such table" in str(exc).lower():
                    allocated = None
                    if isinstance(requested_budget, AgentBudgetLimits):
                        allocated = requested_budget
                    elif isinstance(requested_budget, Mapping):
                        try:
                            allocated = AgentBudgetLimits(**{k: v for k, v in requested_budget.items() if k in AgentBudgetLimits.model_fields})
                        except Exception:
                            allocated = None
                else:
                    raise
        else:
            if isinstance(requested_budget, AgentBudgetLimits):
                allocated = requested_budget
            elif isinstance(requested_budget, Mapping) and requested_budget:
                try:
                    allocated = AgentBudgetLimits(**{k: v for k, v in requested_budget.items() if k in AgentBudgetLimits.model_fields})
                except Exception:
                    allocated = None
        bounded: DelegationContext = project_bounded_context(goal=goal, subtask=subtask, relevant_artifacts=tuple(relevant_artifacts or ()), selected_memory=tuple(selected_memory or ()), policy=dict(policy or {}), skills=tuple(skills or ()), allocated_budget=allocated)
        bounded_dict = bounded.model_dump()
        if self._agent_loop_repo_factory is not None:
            async with self._session_factory() as session:
                loop_repo = self._loop_repo(session)
                if loop_repo is not None:
                    try:
                        await loop_repo.ensure_loop_state(agent_run_id=child_id, default_state="CREATED", limits=allocated.model_dump() if allocated else {}, scope="child")
                    except Exception:
                        pass
                    await session.commit()
        async with self._session_factory() as session:
            delegation_repo = self._delegation_repo(session)
            loop_repo = self._loop_repo(session)
            multi_repo = self._multi_repo(session)
            existing = await delegation_repo.get_delegation_by_child(child_id)
            if existing is not None:
                allocated_existing = existing.get("allocated_budget") or {}
                try:
                    allocated_budget_obj = AgentBudgetLimits(**allocated_existing) if allocated_existing else None
                except Exception:
                    allocated_budget_obj = allocated
                handle = DelegationHandle(child_agent_run_id=str(existing["child_agent_run_id"]), parent_agent_run_id=str(existing["parent_agent_run_id"]), root_agent_run_id=str(existing["root_agent_run_id"]), delegation_depth=int(existing["delegation_depth"]), delegation_reason=str(existing["delegation_reason"]), allocated_budget=allocated_budget_obj, failure_policy=ChildFailurePolicy(str(existing.get("failure_policy") or failure_policy.value)))
                await session.commit()
                return handle
            allocated_dict = allocated.model_dump(exclude_none=False) if allocated else {}
            await delegation_repo.create_delegation(child_agent_run_id=child_id, parent_agent_run_id=parent_agent_run_id, root_agent_run_id=root_id, delegation_depth=int(depth), delegation_reason=str(delegation_reason), failure_policy=str(failure_policy.value), allocated_budget=allocated_dict, bounded_context=bounded_dict)
            if multi_repo is not None:
                try:
                    conv_id = None
                    try:
                        if hasattr(multi_repo, "conversation_id_for_agent"):
                            conv_id = await multi_repo.conversation_id_for_agent(parent_agent_run_id)
                    except Exception:
                        conv_id = None
                    if conv_id:
                        await multi_repo.append_event(event_id=_new_id(), conversation_id=str(conv_id), event_type="delegation_child_spawned", data={"parent_agent_run_id": parent_agent_run_id, "child_agent_run_id": child_id, "root_agent_run_id": root_id, "delegation_depth": depth, "delegation_reason": delegation_reason, "failure_policy": str(failure_policy.value)}, agent_instance_id=parent_agent_run_id)
                except Exception:
                    pass
            if loop_repo is not None:
                try:
                    parent_row = await loop_repo.get_loop_state(parent_agent_run_id)
                    if parent_row is not None and str(parent_row.get("state")) == AgentLoopState.RUNNING.value:
                        from windagent_core.domain.agent_loop import AgentLoopLifecycle
                        AgentLoopLifecycle.transition(agent_run_id=parent_agent_run_id, current=str(parent_row["state"]), target=AgentLoopState.WAITING_CHILD.value, current_version=int(parent_row["version"]), expected_version=int(parent_row["version"]))
                        await loop_repo.transition_loop_state(agent_run_id=parent_agent_run_id, expected_version=int(parent_row["version"]), target_state=AgentLoopState.WAITING_CHILD.value)
                except Exception:
                    pass
            await session.commit()
            return DelegationHandle(child_agent_run_id=child_id, parent_agent_run_id=parent_agent_run_id, root_agent_run_id=root_id, delegation_depth=int(depth), delegation_reason=str(delegation_reason), allocated_budget=allocated, failure_policy=failure_policy)
    async def publish_child_result(self, *, child_agent_run_id: str, summary_text: str, artifact_refs: list[str] | tuple[str, ...] | None = None, status: str = "completed", metrics: Mapping[str, Any] | None = None) -> DelegationSummary:
        child_agent_run_id = str(child_agent_run_id).strip()
        if not child_agent_run_id:
            raise DelegationError("child_agent_run_id must not be empty")
        summary_text = str(summary_text or "")
        if len(summary_text) > 4000:
            summary_text = summary_text[:4000]
        refs = tuple(str(r) for r in (artifact_refs or ()))
        # Publish delegation result in its own transaction so it is durable even if
        # subsequent budget/loop/event writes fail.  This mirrors the Phase 2
        # pattern where budget exhaustion is committed before loop transition.
        async with self._session_factory() as session:
            delegation_repo = self._delegation_repo(session)
            row = await delegation_repo.get_delegation_by_child(child_agent_run_id)
            if row is None:
                raise DelegationError(f"delegation not found for child {child_agent_run_id}")
            parent_id = str(row["parent_agent_run_id"])
            version = int(row["version"])
            summary_dict = {"status": status, "summary_text": summary_text, "metrics": dict(metrics or {})}
            updated = await delegation_repo.publish_child_result(child_agent_run_id=child_agent_run_id, expected_version=version, summary=summary_dict, artifact_refs=list(refs))
            if updated is None:
                raise DelegationError(f"CAS conflict publishing result for {child_agent_run_id}")
            await session.commit()
        # Best-effort side-effects (events, loop transitions, budget) in separate
        # transactions so a failure there does not roll back the durable delegation.
        async with self._session_factory() as session:
            delegation_repo = self._delegation_repo(session)
            multi_repo = self._multi_repo(session)
            loop_repo = self._loop_repo(session)
            # Re-fetch parent_id for side-effects (already known)
            if multi_repo is not None:
                try:
                    conv_id = None
                    try:
                        if hasattr(multi_repo, "conversation_id_for_agent"):
                            conv_id = await multi_repo.conversation_id_for_agent(child_agent_run_id)
                        else:
                            conv_id = await multi_repo.conversation_id_for_agent(parent_id)
                    except Exception:
                        conv_id = None
                    if conv_id:
                        await multi_repo.append_event(event_id=_new_id(), conversation_id=str(conv_id), event_type="delegation_child_completed" if status == "completed" else "delegation_child_failed", data={"child_agent_run_id": child_agent_run_id, "parent_agent_run_id": parent_id, "status": status, "artifact_refs": list(refs)}, agent_instance_id=child_agent_run_id)
                    await session.commit()
                except Exception:
                    await session.rollback()
            if loop_repo is not None:
                try:
                    child_loop = await loop_repo.get_loop_state(child_agent_run_id)
                    if child_loop is not None:
                        from windagent_core.domain.agent_loop import AgentLoopLifecycle
                        target = AgentLoopState.COMPLETED.value if status == "completed" else AgentLoopState.FAILED.value
                        cur_state = str(child_loop.get("state"))
                        if not AgentLoopLifecycle.is_terminal(cur_state):
                            try:
                                AgentLoopLifecycle.transition(agent_run_id=child_agent_run_id, current=cur_state, target=target, current_version=int(child_loop["version"]), expected_version=int(child_loop["version"]))
                                await loop_repo.transition_loop_state(agent_run_id=child_agent_run_id, expected_version=int(child_loop["version"]), target_state=target)
                            except Exception:
                                pass
                    await session.commit()
                except Exception:
                    await session.rollback()
            bc = self._budget_controller()
            if bc is not None:
                try:
                    await bc.release_parallel_slot(parent_id)
                except Exception:
                    pass
            try:
                children = await delegation_repo.list_children(parent_id)
                all_terminal = True
                for ch in children:
                    cs = ch.get("child_result_summary") or {}
                    if not cs:
                        all_terminal = False
                        break
                    st = str(cs.get("status") or "")
                    if st not in ("completed", "failed", "skipped"):
                        all_terminal = False
                        break
                if all_terminal and loop_repo is not None:
                    parent_loop = await loop_repo.get_loop_state(parent_id)
                    if parent_loop is not None and str(parent_loop.get("state")) == AgentLoopState.WAITING_CHILD.value:
                        from windagent_core.domain.agent_loop import AgentLoopLifecycle
                        try:
                            AgentLoopLifecycle.transition(agent_run_id=parent_id, current=str(parent_loop["state"]), target=AgentLoopState.RUNNING.value, current_version=int(parent_loop["version"]), expected_version=int(parent_loop["version"]))
                            await loop_repo.transition_loop_state(agent_run_id=parent_id, expected_version=int(parent_loop["version"]), target_state=AgentLoopState.RUNNING.value)
                        except Exception:
                            pass
                    await session.commit()
                else:
                    await session.commit()
            except Exception:
                try:
                    await session.rollback()
                except Exception:
                    pass
            return DelegationSummary(child_agent_run_id=child_agent_run_id, parent_agent_run_id=parent_id, status=status, summary_text=summary_text, artifact_refs=refs, metrics=dict(metrics or {}) if metrics else None)
    async def get_delegation(self, child_agent_run_id: str) -> DelegationRecord | None:
        async with self._session_factory() as session:
            repo = self._delegation_repo(session)
            row = await repo.get_delegation_by_child(str(child_agent_run_id))
            if row is None:
                return None
            return self._row_to_record(row)
    async def list_children(self, parent_agent_run_id: str) -> list[DelegationRecord]:
        async with self._session_factory() as session:
            repo = self._delegation_repo(session)
            rows = await repo.list_children(str(parent_agent_run_id))
            return [self._row_to_record(r) for r in rows]
    async def list_tree(self, root_agent_run_id: str) -> list[DelegationRecord]:
        async with self._session_factory() as session:
            repo = self._delegation_repo(session)
            rows = await repo.list_tree(str(root_agent_run_id))
            return [self._row_to_record(r) for r in rows]
    async def collect_child_summaries(self, parent_agent_run_id: str) -> list[DelegationSummary]:
        async with self._session_factory() as session:
            repo = self._delegation_repo(session)
            rows = await repo.list_children(str(parent_agent_run_id))
            out: list[DelegationSummary] = []
            for r in rows:
                summary = r.get("child_result_summary") or {}
                if not summary:
                    continue
                refs = tuple(str(x) for x in (r.get("child_artifact_refs") or []))
                out.append(DelegationSummary(child_agent_run_id=str(r["child_agent_run_id"]), parent_agent_run_id=str(r["parent_agent_run_id"]), status=str(summary.get("status") or "unknown"), summary_text=str(summary.get("summary_text") or ""), artifact_refs=refs, metrics=summary.get("metrics")))
            return out
    async def apply_failure_policy(self, *, parent_agent_run_id: str, child_agent_run_id: str, error: str | None = None) -> dict[str, Any]:
        async with self._session_factory() as session:
            delegation_repo = self._delegation_repo(session)
            loop_repo = self._loop_repo(session)
            multi_repo = self._multi_repo(session)
            row = await delegation_repo.get_delegation_by_child(str(child_agent_run_id))
            if row is None:
                raise DelegationError(f"delegation not found for child {child_agent_run_id}")
            policy = str(row.get("failure_policy") or ChildFailurePolicy.FAIL_PARENT.value)
            try:
                pol = ChildFailurePolicy(policy)
            except ValueError:
                pol = ChildFailurePolicy.FAIL_PARENT
            action: dict[str, Any] = {"policy": pol.value, "child_agent_run_id": str(child_agent_run_id), "parent_agent_run_id": str(parent_agent_run_id)}
            if pol == ChildFailurePolicy.RETRY:
                action["action"] = "retry_child"
            elif pol == ChildFailurePolicy.REPLACE:
                action["action"] = "replace_child"
                existing_summary = row.get("child_result_summary") or {}
                if not existing_summary:
                    await delegation_repo.publish_child_result(child_agent_run_id=str(child_agent_run_id), expected_version=int(row["version"]), summary={"status": "failed", "summary_text": error or "replaced", "metrics": {}}, artifact_refs=list(row.get("child_artifact_refs") or []))
            elif pol == ChildFailurePolicy.PARTIAL_SUCCESS:
                action["action"] = "partial_success_proceed"
            elif pol == ChildFailurePolicy.SKIP:
                action["action"] = "skip_child"
            elif pol == ChildFailurePolicy.ESCALATE:
                action["action"] = "escalate"
                if multi_repo is not None:
                    try:
                        conv_id = await multi_repo.conversation_id_for_agent(str(parent_agent_run_id))
                        await multi_repo.append_event(event_id=_new_id(), conversation_id=str(conv_id), event_type="delegation_child_escalated", data={"child_agent_run_id": str(child_agent_run_id), "parent_agent_run_id": str(parent_agent_run_id), "error": error}, agent_instance_id=str(parent_agent_run_id))
                    except Exception:
                        pass
            elif pol == ChildFailurePolicy.FAIL_PARENT:
                action["action"] = "fail_parent"
                if loop_repo is not None:
                    try:
                        parent_loop = await loop_repo.get_loop_state(str(parent_agent_run_id))
                        if parent_loop is not None:
                            from windagent_core.domain.agent_loop import AgentLoopLifecycle
                            cur = str(parent_loop.get("state"))
                            if not AgentLoopLifecycle.is_terminal(cur):
                                try:
                                    AgentLoopLifecycle.transition(agent_run_id=str(parent_agent_run_id), current=cur, target=AgentLoopState.FAILED.value, current_version=int(parent_loop["version"]), expected_version=int(parent_loop["version"]), reason=error or "child_failed")
                                    await loop_repo.transition_loop_state(agent_run_id=str(parent_agent_run_id), expected_version=int(parent_loop["version"]), target_state=AgentLoopState.FAILED.value, exhaustion_reason=error or "child_failed")
                                except Exception:
                                    pass
                    except Exception:
                        pass
            else:
                action["action"] = "unknown"
            await session.commit()
            return action
    async def pause_parent(self, parent_agent_run_id: str, reason: str | None = None) -> None:
        async with self._session_factory() as session:
            loop_repo = self._loop_repo(session)
            if loop_repo is None:
                return
            row = await loop_repo.get_loop_state(str(parent_agent_run_id))
            if row is None:
                return
            cur = str(row.get("state"))
            try:
                from windagent_core.domain.agent_loop import AgentLoopLifecycle
                AgentLoopLifecycle.transition(agent_run_id=str(parent_agent_run_id), current=cur, target=AgentLoopState.PAUSED.value, current_version=int(row["version"]), expected_version=int(row["version"]), reason=reason)
                await loop_repo.transition_loop_state(agent_run_id=str(parent_agent_run_id), expected_version=int(row["version"]), target_state=AgentLoopState.PAUSED.value, exhaustion_reason=reason)
                await session.commit()
            except Exception:
                await session.rollback()
    async def resume_parent(self, parent_agent_run_id: str) -> None:
        async with self._session_factory() as session:
            loop_repo = self._loop_repo(session)
            if loop_repo is None:
                return
            row = await loop_repo.get_loop_state(str(parent_agent_run_id))
            if row is None:
                return
            cur = str(row.get("state"))
            if cur != AgentLoopState.PAUSED.value:
                return
            try:
                from windagent_core.domain.agent_loop import AgentLoopLifecycle
                AgentLoopLifecycle.transition(agent_run_id=str(parent_agent_run_id), current=cur, target=AgentLoopState.RUNNING.value, current_version=int(row["version"]), expected_version=int(row["version"]))
                await loop_repo.transition_loop_state(agent_run_id=str(parent_agent_run_id), expected_version=int(row["version"]), target_state=AgentLoopState.RUNNING.value)
                await session.commit()
            except Exception:
                await session.rollback()
    def _row_to_record(self, row: Mapping[str, Any]) -> DelegationRecord:
        budget_raw = row.get("allocated_budget") or {}
        try:
            budget = AgentBudgetLimits(**budget_raw) if budget_raw else None
        except Exception:
            budget = None
        summary = row.get("child_result_summary")
        refs = tuple(str(x) for x in (row.get("child_artifact_refs") or []))
        policy_str = str(row.get("failure_policy") or ChildFailurePolicy.FAIL_PARENT.value)
        try:
            policy = ChildFailurePolicy(policy_str)
        except ValueError:
            policy = ChildFailurePolicy.FAIL_PARENT
        return DelegationRecord(child_agent_run_id=str(row["child_agent_run_id"]), parent_agent_run_id=str(row["parent_agent_run_id"]), root_agent_run_id=str(row["root_agent_run_id"]), delegation_depth=int(row["delegation_depth"]), delegation_reason=str(row["delegation_reason"]), failure_policy=policy, allocated_budget=budget, child_result_summary=dict(summary) if isinstance(summary, Mapping) and summary else None, child_artifact_refs=refs, bounded_context=dict(row["bounded_context"]) if isinstance(row.get("bounded_context"), Mapping) else None, version=int(row.get("version") or 1), created_at=row.get("created_at"), updated_at=row.get("updated_at"))
