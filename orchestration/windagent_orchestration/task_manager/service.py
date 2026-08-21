"""
Durable Task Manager Service for WindAgent Architecture V2.
Manages durable task facts, state machine transitions, and derived UI status.
Supports both in-memory caching and durable UnitOfWork persistence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from windagent_core.domain.types import TaskId, SessionId
from windagent_orchestration.state_machine import TaskState, TaskStateMachine
from windagent_orchestration.task_manager.facts import DurableExecutionFacts

logger = logging.getLogger("windagent.orchestration.task_manager")


class TaskManager:
    def __init__(
        self,
        uow_factory: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        dispatcher: Optional[Any] = None,
        retry_policy: Optional[Any] = None,
        cancellation_manager: Optional[Any] = None,
    ):
        self.uow_factory = uow_factory
        self.scheduler = scheduler
        self.dispatcher = dispatcher
        self.retry_policy = retry_policy
        self.cancellation_manager = cancellation_manager
        self.state_machine = TaskStateMachine()
        self._in_memory_facts: Dict[str, DurableExecutionFacts] = {}

    def get_or_create_facts(self, task_id: TaskId, session_id: SessionId) -> DurableExecutionFacts:
        tid_str = str(task_id)
        if tid_str not in self._in_memory_facts:
            self._in_memory_facts[tid_str] = DurableExecutionFacts(task_id=task_id, session_id=session_id)
        return self._in_memory_facts[tid_str]

    async def save_durable_facts(self, facts: DurableExecutionFacts) -> int:
        if self.uow_factory:
            try:
                async with self.uow_factory() as uow:
                    new_version = await uow.task_runs.save_facts(
                        task_id=str(facts.task_id),
                        session_id=str(facts.session_id),
                        state=facts.current_state.value,
                        version=facts.version,
                        facts=facts.to_dict(),
                    )
                    await uow.commit()
                    facts.version = new_version
                    return new_version
            except Exception as ex:
                logger.warning(f"Durable facts save fallback to in-memory facts: {ex}")
        return facts.version

    async def load_durable_facts(self, task_id: TaskId) -> Optional[DurableExecutionFacts]:
        if not self.uow_factory:
            return self._in_memory_facts.get(str(task_id))

        async with self.uow_factory() as uow:
            raw = await uow.task_runs.get_by_id(str(task_id))
            if not raw:
                return None
            facts = DurableExecutionFacts.from_dict(raw["facts"])
            facts.version = raw["version"]
            self._in_memory_facts[str(task_id)] = facts
            return facts

    async def transition_task_durable(
        self,
        task_id: TaskId,
        session_id: SessionId,
        target_state: TaskState,
        error_msg: Optional[str] = None,
    ) -> DurableExecutionFacts:
        facts = self.get_or_create_facts(task_id, session_id)
        new_state = self.state_machine.transition(facts.current_state, target_state)

        facts.current_state = new_state
        if error_msg:
            facts.last_error = error_msg
        facts.updated_at = datetime.now(timezone.utc)

        if self.uow_factory:
            async with self.uow_factory() as uow:
                new_version = await uow.task_runs.save_facts(
                    task_id=str(task_id),
                    session_id=str(session_id),
                    state=new_state.value,
                    version=facts.version,
                    facts=facts.to_dict(),
                )
                await uow.commit()
                facts.version = new_version

        return facts

    def transition_task(self, task_id: TaskId, session_id: SessionId, target_state: TaskState) -> DurableExecutionFacts:
        """In-memory sync transition for backwards compatibility in unit tests."""
        facts = self.get_or_create_facts(task_id, session_id)
        new_state = self.state_machine.transition(facts.current_state, target_state)
        facts.current_state = new_state
        facts.updated_at = datetime.now(timezone.utc)
        return facts
