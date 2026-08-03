"""
Cancellation Propagation and Signal Broadcaster for WindAgent Execution V2 (Phase 18).
Propagates cancellation requests to active runtime execution handles.
"""

from __future__ import annotations
import logging
from typing import Dict
from windagent_core.contracts.execution import ExecutionHandle, ExecutionRuntimePort

logger = logging.getLogger("windagent.execution.cancellation")


class CancellationBroadcaster:
    """Manages active execution handles and broadcasts cancellation requests across runtime adapters."""

    def __init__(self) -> None:
        self._active_handles: Dict[str, ExecutionHandle] = {}
        self._adapters: Dict[str, ExecutionRuntimePort] = {}

    def register_handle(self, handle: ExecutionHandle, adapter: ExecutionRuntimePort) -> None:
        self._active_handles[handle.handle_id] = handle
        self._adapters[handle.handle_id] = adapter

    def unregister_handle(self, handle_id: str) -> None:
        self._active_handles.pop(handle_id, None)
        self._adapters.pop(handle_id, None)

    async def cancel_handle(self, handle_id: str) -> bool:
        handle = self._active_handles.get(handle_id)
        adapter = self._adapters.get(handle_id)
        if handle and adapter:
            logger.info(f"Broadcasting cancellation to runtime handle [{handle_id}], step [{handle.step_run_id}]")
            await adapter.cancel(handle)
            self.unregister_handle(handle_id)
            return True
        return False

    async def cancel_step(self, step_run_id: str) -> int:
        cancelled_count = 0
        matching = [hid for hid, h in self._active_handles.items() if h.step_run_id == step_run_id]
        for hid in matching:
            if await self.cancel_handle(hid):
                cancelled_count += 1
        return cancelled_count
