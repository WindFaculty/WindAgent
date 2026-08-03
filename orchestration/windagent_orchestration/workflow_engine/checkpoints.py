"""
Durable Checkpoint and State Resume Manager for Orchestration V2 Workflow Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork


@dataclass
class WorkflowCheckpoint:
    checkpoint_id: str
    run_id: str
    step_id: str
    cursor: int
    completed_steps: Dict[str, Any] = field(default_factory=dict)
    context_data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CheckpointManager:
    def __init__(self, uow_factory: Optional[Any] = None):
        self.uow_factory = uow_factory
        self._in_memory_checkpoints: Dict[str, WorkflowCheckpoint] = {}

    async def save_checkpoint(
        self,
        checkpoint_id: str,
        run_id: str,
        step_id: str,
        cursor: int,
        completed_steps: Dict[str, Any],
        context_data: Dict[str, Any],
    ) -> None:
        ckpt = WorkflowCheckpoint(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            step_id=step_id,
            cursor=cursor,
            completed_steps=completed_steps,
            context_data=context_data,
        )
        self._in_memory_checkpoints[run_id] = ckpt

        if self.uow_factory:
            async with SqlUnitOfWork(self.uow_factory) as uow:
                await uow.checkpoints.save_checkpoint(
                    checkpoint_id=checkpoint_id,
                    run_id=run_id,
                    step_id=step_id,
                    cursor=cursor,
                    state_data={"completed": completed_steps, "context": context_data},
                )
                await uow.commit()

    async def load_latest_checkpoint(self, run_id: str) -> Optional[WorkflowCheckpoint]:
        if not self.uow_factory:
            return self._in_memory_checkpoints.get(run_id)

        async with SqlUnitOfWork(self.uow_factory) as uow:
            raw = await uow.checkpoints.get_latest_checkpoint(run_id)
            if not raw:
                return self._in_memory_checkpoints.get(run_id)

            state = raw["state_data"]
            ckpt = WorkflowCheckpoint(
                checkpoint_id=raw["id"],
                run_id=raw["run_id"],
                step_id=raw["step_id"],
                cursor=raw["cursor"],
                completed_steps=state.get("completed", {}),
                context_data=state.get("context", {}),
            )
            self._in_memory_checkpoints[run_id] = ckpt
            return ckpt
