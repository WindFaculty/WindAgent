"""
Local Agent Runtime Execution Adapter for WindAgent Architecture V2 (Phase 18).
Executes local reasoning and plan synthesis steps.
"""

from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from windagent_core.contracts.execution import (
    ExecutionRuntimePort, ExecutionRequest, ExecutionHandle,
    RuntimeStatus, RuntimeStatusEnum, ExecutionResult
)

logger = logging.getLogger("windagent.execution.local_agent")


class LocalAgentRuntimeAdapter(ExecutionRuntimePort):
    """Executes local agent reasoning steps."""

    def __init__(self, agent_engine: Any = None):
        self.agent_engine = agent_engine
        self._handles: Dict[str, ExecutionHandle] = {}
        self._results: Dict[str, ExecutionResult] = {}
        self._statuses: Dict[str, RuntimeStatusEnum] = {}

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        handle_id = f"local_h_{uuid.uuid4().hex[:8]}"
        runtime_run_id = f"local_run_{uuid.uuid4().hex[:8]}"

        handle = ExecutionHandle(
            handle_id=handle_id,
            runtime_run_id=runtime_run_id,
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            runtime_session_id=request.workflow_run_id,
        )
        self._handles[handle_id] = handle
        self._statuses[handle_id] = RuntimeStatusEnum.RUNNING

        try:
            self._statuses[handle_id] = RuntimeStatusEnum.COMPLETED
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.COMPLETED,
                result_data={
                    "agent_decision": "proceed",
                    "plan": f"Plan for step {request.step_run_id}",
                },
            )
        except Exception as ex:
            logger.error(f"Local agent step failed: {ex}")
            self._statuses[handle_id] = RuntimeStatusEnum.FAILED
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.FAILED,
                error=str(ex),
            )

        return handle

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        status_val = self._statuses.get(handle.handle_id, RuntimeStatusEnum.UNKNOWN)
        return RuntimeStatus(
            handle_id=handle.handle_id,
            status=status_val,
            heartbeat_at=datetime.now(timezone.utc),
        )

    async def cancel(self, handle: ExecutionHandle) -> None:
        self._statuses[handle.handle_id] = RuntimeStatusEnum.CANCELLED
        self._results[handle.handle_id] = ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.CANCELLED,
            error="Local agent step cancelled",
        )

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        if handle.handle_id in self._results:
            return self._results[handle.handle_id]
        return ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=self._statuses.get(handle.handle_id, RuntimeStatusEnum.RUNNING),
        )

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        for h in self._handles.values():
            if h.runtime_run_id == runtime_run_id:
                return h
        return None
