"""
Hermes Execution Runtime Production Adapter for WindAgent Orchestration V2.
Adapts Hermes session bridge, API client, and runtime manager to the ExecutionRuntimePort protocol.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Any, Dict

from windagent_core.contracts.execution import (
    ExecutionRuntimePort, ExecutionRequest, ExecutionHandle,
    RuntimeStatus, RuntimeStatusEnum, ExecutionResult
)

logger = logging.getLogger("windagent.execution.hermes_adapter")


class HermesRuntimeAdapter(ExecutionRuntimePort):
    def __init__(self, bridge: Any, api_client: Any = None, runtime_manager: Any = None):
        self.bridge = bridge
        self.api_client = api_client
        self.runtime_manager = runtime_manager
        self._handles: Dict[str, ExecutionHandle] = {}

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        handle_id = f"hermes_h_{uuid.uuid4().hex[:8]}"
        runtime_run_id = f"hermes_run_{uuid.uuid4().hex[:8]}"
        
        windagent_session_id = request.workflow_run_id
        
        # Submit message / action to Hermes bridge
        try:
            if hasattr(self.bridge, "submit_message"):
                run_info = await self.bridge.submit_message(
                    windagent_session_id=windagent_session_id,
                    agent_id="default_hermes_agent",
                    content=f"Execute step {request.step_run_id} tool {request.tool_name}",
                    workspace_root=request.context.get("workspace_root") if request.context else None,
                )
                if isinstance(run_info, dict) and "run_id" in run_info:
                    runtime_run_id = run_info["run_id"]
        except Exception as ex:
            logger.warning(f"Hermes bridge dispatch fallback to simulated handle: {ex}")

        handle = ExecutionHandle(
            handle_id=handle_id,
            runtime_run_id=runtime_run_id,
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            runtime_session_id=windagent_session_id,
        )
        self._handles[handle_id] = handle
        return handle

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        if self.api_client and hasattr(self.api_client, "get_run_status"):
            try:
                res = await self.api_client.get_run_status(handle.runtime_run_id)
                status_str = res.get("status", "running")
                status_enum = {
                    "completed": RuntimeStatusEnum.COMPLETED,
                    "failed": RuntimeStatusEnum.FAILED,
                    "cancelled": RuntimeStatusEnum.CANCELLED,
                    "running": RuntimeStatusEnum.RUNNING,
                }.get(status_str, RuntimeStatusEnum.UNKNOWN)
                return RuntimeStatus(handle_id=handle.handle_id, status=status_enum, heartbeat_at=datetime.now(timezone.utc))
            except Exception as ex:
                logger.warning(f"Error checking status for Hermes run [{handle.runtime_run_id}]: {ex}")
                return RuntimeStatus(handle_id=handle.handle_id, status=RuntimeStatusEnum.UNKNOWN, heartbeat_at=datetime.now(timezone.utc))

        return RuntimeStatus(handle_id=handle.handle_id, status=RuntimeStatusEnum.RUNNING, heartbeat_at=datetime.now(timezone.utc))

    async def cancel(self, handle: ExecutionHandle) -> None:
        logger.info(f"Cancelling Hermes execution handle [{handle.handle_id}], run [{handle.runtime_run_id}]")
        if self.api_client and hasattr(self.api_client, "stop_run"):
            try:
                await self.api_client.stop_run(handle.runtime_run_id)
            except Exception as ex:
                logger.error(f"Failed to cancel Hermes run [{handle.runtime_run_id}]: {ex}")
        elif self.runtime_manager and hasattr(self.runtime_manager, "stop"):
            try:
                await self.runtime_manager.stop()
            except Exception as ex:
                logger.error(f"Failed to stop Hermes runtime manager: {ex}")

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        status = await self.get_status(handle)
        return ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=status.status,
            result_data={"runtime_run_id": handle.runtime_run_id},
        )

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        for h in self._handles.values():
            if h.runtime_run_id == runtime_run_id:
                return h
        return None
