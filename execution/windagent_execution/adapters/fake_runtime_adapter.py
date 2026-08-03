"""
Fake Execution Runtime Adapter for Testing WindAgent Orchestration V2.
Implements ExecutionRuntimePort for unit/integration/crash tests without external dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from windagent_core.contracts.execution import (
    ExecutionRuntimePort, ExecutionRequest, ExecutionHandle,
    RuntimeStatus, RuntimeStatusEnum, ExecutionResult
)


class FakeRuntimeAdapter(ExecutionRuntimePort):
    def __init__(self, default_mode: str = "success"):
        self.default_mode = default_mode  # success | failure | timeout | cancel | lost | unknown | running
        self._handles: Dict[str, ExecutionHandle] = {}
        self._statuses: Dict[str, RuntimeStatusEnum] = {}
        self._results: Dict[str, ExecutionResult] = {}
        self._canceled: Dict[str, bool] = {}
        self._modes_by_step: Dict[str, str] = {}
        self._modes_by_tool: Dict[str, str] = {}
        self._crashed_run_ids: set[str] = set()
        self.dispatched_requests: list[ExecutionRequest] = []

    def set_mode_for_step(self, step_run_id: str, mode: str) -> None:
        """Override behavior for one dispatched step without changing other runs."""
        self._modes_by_step[step_run_id] = mode

    def set_mode_for_tool(self, tool_name: str, mode: str) -> None:
        """Override behavior for future requests of a tool type."""
        self._modes_by_tool[tool_name] = mode

    def complete(self, runtime_run_id: str, result_data: Dict[str, Any] | None = None) -> None:
        """Advance an already-dispatched fake runtime to a successful terminal state."""
        handle = self._handle_for_run(runtime_run_id)
        self._statuses[handle.handle_id] = RuntimeStatusEnum.COMPLETED
        self._results[handle.handle_id] = ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.COMPLETED,
            result_data=result_data or {},
        )

    def fail(self, runtime_run_id: str, error: str = "Simulated execution error") -> None:
        """Advance an already-dispatched fake runtime to a failed terminal state."""
        handle = self._handle_for_run(runtime_run_id)
        self._statuses[handle.handle_id] = RuntimeStatusEnum.FAILED
        self._results[handle.handle_id] = ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.FAILED,
            error=error,
        )

    def crash(self, runtime_run_id: str) -> None:
        """Simulate a process disappearance: status is lost and reattach fails."""
        handle = self._handle_for_run(runtime_run_id)
        self._crashed_run_ids.add(runtime_run_id)
        self._statuses[handle.handle_id] = RuntimeStatusEnum.LOST
        self._results[handle.handle_id] = ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=RuntimeStatusEnum.LOST,
            error="Runtime process disappeared unexpectedly",
        )

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
        self.dispatched_requests.append(request)

        mode = self._modes_by_step.get(
            request.step_run_id,
            self._modes_by_tool.get(request.tool_name, self.default_mode),
        )
        if mode == "success":
            self._statuses[handle_id] = RuntimeStatusEnum.COMPLETED
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.COMPLETED,
                result_data={"output": f"Fake output for tool {request.tool_name}", "params": request.parameters},
                result_ref=f"ref_{handle_id}",
            )
        elif mode == "failure":
            self._statuses[handle_id] = RuntimeStatusEnum.FAILED
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.FAILED,
                error=f"Simulated execution error for tool {request.tool_name}",
            )
        elif mode in {"lost", "crash"}:
            self._statuses[handle_id] = RuntimeStatusEnum.LOST
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.LOST,
                error="Runtime process disappeared unexpectedly",
            )
            if mode == "crash":
                self._crashed_run_ids.add(runtime_run_id)
        elif mode == "unknown":
            self._statuses[handle_id] = RuntimeStatusEnum.UNKNOWN
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.UNKNOWN,
                error="Runtime status unknown / unconfirmed",
            )
        elif mode == "running":
            self._statuses[handle_id] = RuntimeStatusEnum.RUNNING
        elif mode in {"cancel", "cancelled"}:
            self._statuses[handle_id] = RuntimeStatusEnum.CANCELLED
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.CANCELLED,
                error="Cancelled by scripted fake runtime",
            )
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
        if runtime_run_id in self._crashed_run_ids:
            return None
        for h in self._handles.values():
            if h.runtime_run_id == runtime_run_id:
                return h
        return None

    def _handle_for_run(self, runtime_run_id: str) -> ExecutionHandle:
        for handle in self._handles.values():
            if handle.runtime_run_id == runtime_run_id:
                return handle
        raise KeyError(f"unknown fake runtime run: {runtime_run_id}")
