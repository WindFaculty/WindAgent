"""
Runtime Dispatch Service for WindAgent Orchestration V2 Dispatcher.
Dispatches step requests to ExecutionRuntimePort and persists runtime handles.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Any, Dict

from windagent_orchestration.ports import (
    ExecutionRuntimePort, ExecutionRequest, ExecutionHandle
)
from windagent_orchestration.dispatcher.leases import ExecutionLease

logger = logging.getLogger("windagent.orchestration.dispatcher.dispatch")


class StepDispatchService:
    def __init__(self, runtime_port: ExecutionRuntimePort, uow_factory: Optional[Any] = None):
        self.runtime_port = runtime_port
        self.uow_factory = uow_factory

    async def dispatch_to_runtime(
        self,
        lease: ExecutionLease,
        tool_name: str,
        parameters: Dict[str, Any],
        is_destructive: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionHandle:
        attempt_id = f"att_{uuid.uuid4().hex[:8]}"
        req = ExecutionRequest(
            step_run_id=lease.step_run_id,
            workflow_run_id=lease.run_id,
            tool_name=tool_name,
            parameters=parameters,
            attempt_id=attempt_id,
            lease_generation=lease.lease_generation,
            fencing_token=lease.fencing_token,
            is_destructive=is_destructive,
            context=context,
        )

        logger.info(f"Dispatching step [{lease.step_run_id}] (tool: {tool_name}) to runtime port")
        handle = await self.runtime_port.dispatch(req)

        if self.uow_factory:
            async with self.uow_factory() as uow:
                if hasattr(uow, "runtime_executions"):
                    exec_id = f"exec_{uuid.uuid4().hex[:8]}"
                    await uow.runtime_executions.create_execution(
                        execution_id=exec_id,
                        runtime_run_id=handle.runtime_run_id,
                        attempt_id=attempt_id,
                        step_run_id=lease.step_run_id,
                        lease_generation=lease.lease_generation,
                        fencing_token=lease.fencing_token,
                        runtime_session_id=handle.runtime_session_id,
                    )
                    await uow.commit()

        return handle
