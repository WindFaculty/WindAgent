"""
Execution Runtime Registry for WindAgent Architecture V2 (Phase 18).
Routes dispatch requests to appropriate execution adapters based on tool capabilities and runtime names.
"""

from __future__ import annotations
import logging
from typing import Dict, Optional

from windagent_core.contracts.execution import (
    ExecutionRuntimePort, ExecutionRequest, ExecutionHandle, RuntimeStatus, ExecutionResult
)
from windagent_execution.adapters.tool_runtime import ToolRuntimeAdapter
from windagent_execution.adapters.browser_runtime import BrowserRuntimeAdapter
from windagent_execution.adapters.local_agent import LocalAgentRuntimeAdapter
from windagent_execution.adapters.subprocess_runtime import SubprocessRuntimeAdapter

logger = logging.getLogger("windagent.execution.registry")


class ExecutionRuntimeRegistry(ExecutionRuntimePort):
    """Canonical registry mapping execution capabilities and tool names to durable runtime adapters."""

    def __init__(self, default_adapter: Optional[ExecutionRuntimePort] = None) -> None:
        self.default_adapter = default_adapter or ToolRuntimeAdapter()
        self._capability_map: Dict[str, ExecutionRuntimePort] = {
            "tool": self.default_adapter,
            "browser": BrowserRuntimeAdapter(),
            "local_agent": LocalAgentRuntimeAdapter(),
            "subprocess": SubprocessRuntimeAdapter(),
        }
        self._handles_adapter_map: Dict[str, ExecutionRuntimePort] = {}

    def register_capability(self, capability: str, adapter: ExecutionRuntimePort) -> None:
        """Registers a custom runtime adapter for a capability prefix."""
        self._capability_map[capability.lower()] = adapter
        logger.info(f"Registered execution runtime adapter for capability [{capability}]")

    def resolve_adapter(self, tool_name: str) -> ExecutionRuntimePort:
        """Resolves target execution adapter based on tool name prefix or registered capability."""
        name_lower = tool_name.lower()
        if name_lower.startswith("browser_") or name_lower in ("browser", "playwright"):
            return self._capability_map.get("browser", self.default_adapter)
        elif name_lower.startswith("hermes_") or name_lower in ("hermes", "hermes_chat"):
            return self._capability_map.get("hermes", self.default_adapter)
        elif name_lower.startswith("studio."):
            return self._capability_map.get("studio", self.default_adapter)
        elif name_lower.startswith("run_command") or name_lower.startswith("subproc_") or name_lower in ("exec_command", "bash"):
            return self._capability_map.get("subprocess", self.default_adapter)
        elif name_lower.startswith("agent_") or name_lower in ("reason", "plan"):
            return self._capability_map.get("local_agent", self.default_adapter)
        return self._capability_map.get("tool", self.default_adapter)

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        adapter = self.resolve_adapter(request.tool_name)
        handle = await adapter.dispatch(request)
        self._handles_adapter_map[handle.handle_id] = adapter
        return handle

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        adapter = self._handles_adapter_map.get(handle.handle_id, self.default_adapter)
        return await adapter.get_status(handle)

    async def cancel(self, handle: ExecutionHandle) -> None:
        adapter = self._handles_adapter_map.get(handle.handle_id, self.default_adapter)
        await adapter.cancel(handle)

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        adapter = self._handles_adapter_map.get(handle.handle_id, self.default_adapter)
        return await adapter.get_result(handle)

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        for adapter in self._capability_map.values():
            h = await adapter.reattach(runtime_run_id)
            if h:
                self._handles_adapter_map[h.handle_id] = adapter
                return h
        return None
