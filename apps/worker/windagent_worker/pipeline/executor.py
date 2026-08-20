"""Executor stage for the Production Worker pipeline (Architecture V3 Phase 9).

Builds the ``ExecutionRequest``, dispatches it through the execution runtime
registry, registers the handle with the cancellation broadcaster, and retrieves
the terminal result.  This stage performs no SQL/UoW work and never persists
terminal task state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from windagent_core.contracts.execution import ExecutionRequest

from windagent_worker.pipeline.context import TaskExecutionContext


class ExecutorStage:
    """Dispatch/register/get-result only; no persistence and no UoW imports."""

    async def execute(
        self,
        ctx: TaskExecutionContext,
        *,
        execution_registry: Any,
        cancellation_broadcaster: Any,
    ) -> None:
        """Dispatch the task, register the handle, and fetch the result.

        The result is stored on ``ctx.result`` and the handle on ``ctx.handle``
        for the downstream validation stage.
        """
        exec_req = ExecutionRequest(
            step_run_id=ctx.task_id,
            workflow_run_id=f"wf_{ctx.task_id}",
            tool_name=ctx.tool_name,
            parameters={**ctx.parameters, "task_id": ctx.task_id, "prompt": ctx.prompt},
            attempt_id=ctx.attempt_id,
            fencing_token=ctx.fencing_token,
        )

        handle = await execution_registry.dispatch(exec_req)
        cancellation_broadcaster.register_handle(handle, execution_registry)
        ctx.handle = handle
        ctx.result = await execution_registry.get_result(handle)
        ctx.execution_finished_at = datetime.now(timezone.utc)


__all__ = ["ExecutorStage"]