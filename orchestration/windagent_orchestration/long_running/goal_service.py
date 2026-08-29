"""Persistent Goal service — durable goal authority (Phase 5).

Owns the long-running objective independently of worker/UI/API lifetimes.
All mutations are CAS-guarded; illegal/terminal transitions fail closed.
Uses repository ports; no direct SQL in domain logic.

Injected via session_factory + repo factory; no concrete storage import.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Mapping

from windagent_core.domain.persistent_goal import GoalLifecycle, GoalStatus


def _new_id() -> str:
    return str(uuid.uuid4())


class GoalOperationError(RuntimeError):
    pass


class GoalService:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        goal_repo_factory: Callable[[Any], Any],
        multi_repo_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._goal_repo_factory = goal_repo_factory
        self._multi_repo_factory = multi_repo_factory

    def _goal_repo(self, session: Any) -> Any:
        return self._goal_repo_factory(session)

    def _multi_repo(self, session: Any) -> Any | None:
        if self._multi_repo_factory is not None:
            return self._multi_repo_factory(session)
        return None

    async def create_goal(
        self,
        *,
        goal_id: str | None = None,
        objective: str,
        completion_criteria: Mapping[str, Any] | None = None,
        conversation_id: str | None = None,
        parent_task_id: str | None = None,
        agent_run_id: str | None = None,
        harness_version: str | None = None,
    ) -> dict[str, Any]:
        objective = str(objective).strip()
        if not objective:
            raise GoalOperationError("objective must not be empty")
        gid = str(goal_id or f"goal_{uuid.uuid4().hex[:10]}").strip()
        async with self._session_factory() as session:
            repo = self._goal_repo(session)
            multi = self._multi_repo(session)
            row = await repo.create_goal(
                goal_id=gid,
                objective=objective,
                status=GoalStatus.ACTIVE.value,
                progress_summary="",
                completion_criteria=dict(completion_criteria or {}),
                conversation_id=conversation_id,
                parent_task_id=parent_task_id,
                agent_run_id=agent_run_id,
                harness_version=harness_version,
            )
            if multi is not None and conversation_id:
                try:
                    await multi.append_event(
                        event_id=_new_id(),
                        conversation_id=str(conversation_id),
                        event_type="persistent_goal_created",
                        data={"goal_id": gid, "objective": objective, "agent_run_id": agent_run_id},
                        agent_instance_id=agent_run_id or gid,
                    )
                except Exception:
                    pass
            await session.commit()
            return row

    async def get_goal(self, goal_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            repo = self._goal_repo(session)
            return await repo.get_goal(str(goal_id))

    async def list_goals(
        self,
        *,
        conversation_id: str | None = None,
        parent_task_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            repo = self._goal_repo(session)
            return await repo.list_goals(
                conversation_id=conversation_id, parent_task_id=parent_task_id, status=status
            )

    async def update_progress(self, *, goal_id: str, progress_summary: str) -> dict[str, Any]:
        goal_id = str(goal_id).strip()
        progress_summary = str(progress_summary or "")
        async with self._session_factory() as session:
            repo = self._goal_repo(session)
            cur = await repo.get_goal(goal_id)
            if cur is None:
                raise GoalOperationError(f"goal not found: {goal_id}")
            # Blocked/completed goals cannot receive progress without explicit unblock transition
            if cur.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
                raise GoalOperationError(f"cannot update progress for terminal goal {goal_id} [{cur.get('status')}]")
            updated = await repo.update_progress(
                goal_id=goal_id, expected_version=int(cur["version"]), progress_summary=progress_summary
            )
            if updated is None:
                raise GoalOperationError(f"CAS conflict updating progress for {goal_id}")
            multi = self._multi_repo(session)
            if multi is not None and cur.get("conversation_id"):
                try:
                    await multi.append_event(
                        event_id=_new_id(),
                        conversation_id=str(cur["conversation_id"]),
                        event_type="persistent_goal_progress",
                        data={"goal_id": goal_id, "progress_summary": progress_summary[:500]},
                        agent_instance_id=cur.get("agent_run_id") or goal_id,
                    )
                except Exception:
                    pass
            await session.commit()
            return updated

    async def transition(
        self,
        *,
        goal_id: str,
        target_status: str,
        reason: str | None = None,
        blocked_reason: str | None = None,
    ) -> dict[str, Any]:
        goal_id = str(goal_id).strip()
        try:
            tgt = GoalStatus(str(target_status).upper())
        except ValueError as exc:
            raise GoalOperationError(f"unknown goal status {target_status}") from exc
        async with self._session_factory() as session:
            repo = self._goal_repo(session)
            cur = await repo.get_goal(goal_id)
            if cur is None:
                raise GoalOperationError(f"goal not found: {goal_id}")
            cur_status = GoalStatus(str(cur["status"]).upper())
            # CAS guard + legal transition validation
            GoalLifecycle.transition(
                aggregate_id=goal_id,
                current=cur_status,
                target=tgt,
                current_version=int(cur["version"]),
                expected_version=int(cur["version"]),
                reason=reason or blocked_reason,
            )
            # terminal correction: do not allow progress_summary to survive BLOCKED without reason?
            updated = await repo.transition_status(
                goal_id=goal_id,
                expected_version=int(cur["version"]),
                target_status=tgt.value,
                reason=reason,
                blocked_reason=blocked_reason or reason,
            )
            if updated is None:
                raise GoalOperationError(f"CAS conflict transitioning {goal_id} -> {tgt.value}")
            multi = self._multi_repo(session)
            if multi is not None and cur.get("conversation_id"):
                try:
                    await multi.append_event(
                        event_id=_new_id(),
                        conversation_id=str(cur["conversation_id"]),
                        event_type=f"persistent_goal_{tgt.value.lower()}",
                        data={"goal_id": goal_id, "from": cur_status.value, "to": tgt.value, "reason": reason, "blocked_reason": blocked_reason},
                        agent_instance_id=cur.get("agent_run_id") or goal_id,
                    )
                except Exception:
                    pass
            await session.commit()
            return updated

    # convenience wrappers -------------------------------------------------
    async def mark_in_progress(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        return await self.transition(goal_id=goal_id, target_status="IN_PROGRESS", reason=reason)

    async def block(self, goal_id: str, blocked_reason: str) -> dict[str, Any]:
        if not str(blocked_reason).strip():
            raise GoalOperationError("blocked_reason must not be empty")
        return await self.transition(goal_id=goal_id, target_status="BLOCKED", blocked_reason=blocked_reason)

    async def unblock(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        return await self.transition(goal_id=goal_id, target_status="IN_PROGRESS", reason=reason or "unblocked")

    async def pause(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        return await self.transition(goal_id=goal_id, target_status="PAUSED", reason=reason)

    async def resume(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        cur = await self.get_goal(goal_id)
        if cur is None:
            raise GoalOperationError(f"goal not found: {goal_id}")
        if cur["status"] == "PAUSED":
            return await self.transition(goal_id=goal_id, target_status="ACTIVE", reason=reason or "resumed")
        if cur["status"] == "BLOCKED":
            return await self.unblock(goal_id, reason=reason or "resumed")
        return await self.transition(goal_id=goal_id, target_status="IN_PROGRESS", reason=reason or "resumed")

    async def complete(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        return await self.transition(goal_id=goal_id, target_status="COMPLETED", reason=reason)

    async def fail(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        return await self.transition(goal_id=goal_id, target_status="FAILED", reason=reason)

    async def cancel(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        return await self.transition(goal_id=goal_id, target_status="CANCELLED", reason=reason)
