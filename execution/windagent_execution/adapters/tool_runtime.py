"""
Tool Runtime Execution Adapter for WindAgent Architecture V2 (Phase 18).
Executes windagent_tools within isolated runtime context and handles fencing tokens.
"""

from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from windagent_core.config.certification import certification_mode_enabled
from windagent_core.contracts.execution import (
    ExecutionRuntimePort, ExecutionRequest, ExecutionHandle,
    RuntimeStatus, RuntimeStatusEnum, ExecutionResult
)

logger = logging.getLogger("windagent.execution.tool_runtime")


class ToolRuntimeAdapter(ExecutionRuntimePort):
    """Executes registered tools via ToolRegistry."""

    def __init__(self, tool_registry: Any = None, *, allow_simulation: bool = False):
        self.tool_registry = tool_registry
        self.allow_simulation = allow_simulation
        self._handles: Dict[str, ExecutionHandle] = {}
        self._results: Dict[str, ExecutionResult] = {}
        self._statuses: Dict[str, RuntimeStatusEnum] = {}

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        handle_id = f"tool_h_{uuid.uuid4().hex[:8]}"
        runtime_run_id = f"tool_run_{uuid.uuid4().hex[:8]}"

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

        # Defense in depth: Studio tasks are exclusively authorized by the
        # explicitly registered StudioRuntimeAdapter.  Even a caller that
        # bypasses ExecutionRuntimeRegistry cannot obtain a generic success.
        if request.tool_name.lower().startswith("studio."):
            error = (
                "STUDIO_CAPABILITY_UNAVAILABLE: studio.* cannot execute through "
                "ToolRuntimeAdapter"
            )
            self._statuses[handle_id] = RuntimeStatusEnum.FAILED
            self._results[handle_id] = ExecutionResult(
                handle_id=handle_id,
                step_run_id=request.step_run_id,
                status=RuntimeStatusEnum.FAILED,
                error=error,
            )
            return handle

        # Execute tool if registry is provided
        try:
            if self.tool_registry and hasattr(self.tool_registry, "execute_tool"):
                res = await self.tool_registry.execute_tool(request.tool_name, request.parameters)
                self._statuses[handle_id] = RuntimeStatusEnum.COMPLETED
                self._results[handle_id] = ExecutionResult(
                    handle_id=handle_id,
                    step_run_id=request.step_run_id,
                    status=RuntimeStatusEnum.COMPLETED,
                    result_data=res if isinstance(res, dict) else {"output": str(res)},
                )
            elif self.allow_simulation and not certification_mode_enabled(os.environ):
                # Explicit test/development compatibility seam. Certification
                # mode always rejects it, even if a caller enables the flag.
                self._statuses[handle_id] = RuntimeStatusEnum.COMPLETED
                self._results[handle_id] = ExecutionResult(
                    handle_id=handle_id,
                    step_run_id=request.step_run_id,
                    status=RuntimeStatusEnum.COMPLETED,
                    result_data={"output": f"Executed tool [{request.tool_name}] with params {request.parameters}"},
                )
            else:
                error = "TOOL_RUNTIME_UNAVAILABLE: no ToolRegistry execution authority"
                if self.allow_simulation and certification_mode_enabled(os.environ):
                    error = (
                        "CERTIFICATION_VIOLATION: tool runtime simulation is forbidden "
                        "in certification mode"
                    )
                self._statuses[handle_id] = RuntimeStatusEnum.FAILED
                self._results[handle_id] = ExecutionResult(
                    handle_id=handle_id,
                    step_run_id=request.step_run_id,
                    status=RuntimeStatusEnum.FAILED,
                    error=error,
                )
        except Exception as ex:
            logger.error(f"Tool execution failed for tool [{request.tool_name}]: {ex}")
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
            error="Tool execution cancelled by request",
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
