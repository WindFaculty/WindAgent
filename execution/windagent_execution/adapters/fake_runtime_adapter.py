"""
Fake Execution Runtime Adapter for Testing WindAgent Orchestration V2.
Implements ExecutionRuntimePort for unit/integration/crash tests without external dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from windagent_core.contracts.execution import (
    ExecutionRuntimePort, ExecutionRequest, ExecutionHandle,
    RuntimeStatus, RuntimeStatusEnum, ExecutionResult
)
from windagent_core.domain.types import EventId


class FakeRuntimeAdapter(ExecutionRuntimePort):
    def __init__(self, default_mode: str = "success"):
        self.default_mode = default_mode  # success | failure | timeout | cancel | lost | unknown
        self._handles: Dict[str, ExecutionHandle] = {}
        self._statuses: Dict[str, RuntimeStatusEnum] = {}
        self._results: Dict[str, ExecutionResult] = {}
        self._canceled: Dict[str, bool] = {}

    def set_mode_for_step(self, step_run_id: str, mode: str) -> None:
        """Override behavior mode for a specific step."""
        self.default_mode = mode

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        runtime_run_id = f"fake_run_{uuid.uuid4().hex[:8]}"
        handle_id = f"handle_{uuid.uuid4().hex[:8]}"
        
        handle = ExecutionHandle(
            handle_id=handle_id,
            runtime_run_id=runtime_run_id,
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            runtime_session_id=f"sess_{request.workflow_run_id}",
        )
        self._handles[handle_id] = handle

        if self.default_mode == "success":
            self._statuses[handle_id] = RuntimeStatusEnum.COMPLETED
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.COMPLETED,
                result_data={"output": f"Fake output for tool {request.tool_name}", "params": request.parameters},
                result_ref=f"ref_{handle_id}",
            )
        elif self.default_mode == "failure":
            self._statuses[handle_id] = RuntimeStatusEnum.FAILED
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.FAILED,
                error=f"Simulated execution error for tool {request.tool_name}",
            )
        elif self.default_mode == "lost":
            self._statuses[handle_id] = RuntimeStatusEnum.LOST
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.LOST,
                error="Runtime process disappeared unexpectedly",
            )
        elif self.default_mode == "unknown":
            self._statuses[handle_id] = RuntimeStatusEnum.UNKNOWN
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.UNKNOWN,
                error="Runtime status unknown / unconfirmed",
            )
        elif self.default_mode == "running":
            self._statuses[handle_id] = RuntimeStatusEnum.RUNNING
        else:
            self._statuses[handle_id] = RuntimeStatusEnum.DISPATCHED

        return handle

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        status_val = self._statuses.get(handle.handle_id, RuntimeStatusEnum.UNKNOWN)
        return RuntimeStatus(
            handle_id=handle.handle_id,
            status=status_val,
            heartbeat_at=datetime.now(timezone.utc),
        )

    async def cancel(self, handle: ExecutionHandle) -> None:
        self._canceled[handle.handle_id] = True
        self._statuses[handle.handle_id] = RuntimeStatusEnum.CANCELLED
        self._results[handle.handle_id] = ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.CANCELLED,
            error="Cancelled by user request",
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
