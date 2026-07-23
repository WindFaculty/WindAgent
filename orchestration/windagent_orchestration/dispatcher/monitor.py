"""
Execution Monitoring & Heartbeat Service for WindAgent Orchestration V2 Dispatcher.
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from windagent_orchestration.ports import (
    ExecutionRuntimePort, ExecutionHandle, RuntimeStatus, RuntimeStatusEnum
)

logger = logging.getLogger("windagent.orchestration.dispatcher.monitor")


class ExecutionMonitorService:
    def __init__(self, runtime_port: ExecutionRuntimePort):
        self.runtime_port = runtime_port

    async def check_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        status = await self.runtime_port.get_status(handle)
        logger.debug(f"Checked status for handle [{handle.handle_id}]: {status.status}")
        return status
