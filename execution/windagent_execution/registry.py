"""
Execution Runtime Registry for WindAgent Architecture V2 (Phase 18).
Routes dispatch requests to appropriate execution adapters based on tool capabilities and runtime names.
"""

from __future__ import annotations
import logging
from typing import Dict, Optional

from windagent_core.contracts.execution import (
    ExecutionRuntimePort, ExecutionRequest, ExecutionHandle, RuntimeStatus, ExecutionResult,
    CreateSessionRequest, AttachSessionRequest, CheckpointRequest, RestoreRequest, InspectRequest, TerminateRequest,
    RuntimeSession, CheckpointResult, RestoreResult, InspectResult, TerminateResult
)
from windagent_core.contracts.studio.errors import StudioCapabilityUnavailableError
from windagent_execution.factory import (
    create_browser_runtime_adapter,
    create_local_agent_runtime_adapter,
    create_subprocess_runtime_adapter,
    create_tool_runtime_adapter,
)

logger = logging.getLogger("windagent.execution.registry")


class ExecutionRuntimeRegistry(ExecutionRuntimePort):
    """Canonical registry mapping execution capabilities and tool names to durable runtime adapters.

    Phase 3: optionally hosts a StatefulExecutionRuntime for session-oriented
    operations (create/attach/execute/checkpoint/restore/inspect/cancel/terminate).
    Legacy dispatch/reattach/get_status/cancel/get_result behavior is fully preserved.
    """

    def __init__(
        self,
        default_adapter: Optional[ExecutionRuntimePort] = None,
        *,
        allow_tool_simulation: bool = False,
        stateful_runtime: Optional[object] = None,
    ) -> None:
        self.default_adapter = default_adapter or create_tool_runtime_adapter(
            allow_simulation=allow_tool_simulation
        )
        self._capability_map: Dict[str, ExecutionRuntimePort] = {
            "tool": self.default_adapter,
            "browser": create_browser_runtime_adapter(),
            "local_agent": create_local_agent_runtime_adapter(),
            "subprocess": create_subprocess_runtime_adapter(),
        }
        self._handles_adapter_map: Dict[str, ExecutionRuntimePort] = {}
        self._stateful_runtime: Optional[object] = stateful_runtime
        if self._stateful_runtime is None:
            try:
                from windagent_execution.stateful_runtime import InMemoryStatefulRuntime
                self._stateful_runtime = InMemoryStatefulRuntime()
                self._capability_map["stateful"] = self._stateful_runtime  # type: ignore[assignment]
            except Exception:
                pass

    def register_capability(self, capability: str, adapter: ExecutionRuntimePort) -> None:
        """Registers a custom runtime adapter for a capability prefix."""
        self._capability_map[capability.lower()] = adapter
        logger.info(f"Registered execution runtime adapter for capability [{capability}]")

    def register_stateful_runtime(self, adapter: object) -> None:
        """Registers the stateful session runtime (Phase 3)."""
        self._stateful_runtime = adapter
        self._capability_map["stateful"] = adapter  # type: ignore[assignment]
        logger.info("Registered stateful execution runtime")

    @property
    def stateful_runtime(self) -> Optional[object]:
        return self._stateful_runtime

    def _require_stateful(self):
        if self._stateful_runtime is None:
            raise RuntimeError("Stateful runtime not registered; host must provide session substrate")
        return self._stateful_runtime

    def resolve_adapter(self, tool_name: str) -> ExecutionRuntimePort:
        """Resolves target execution adapter based on tool name prefix or registered capability."""
        name_lower = tool_name.lower()
        if name_lower.startswith("browser_") or name_lower in ("browser", "playwright"):
            return self._capability_map.get("browser", self.default_adapter)
        elif name_lower.startswith("hermes_") or name_lower in ("hermes", "hermes_chat"):
            return self._capability_map.get("hermes", self.default_adapter)
        elif name_lower.startswith("studio."):
            adapter = self._capability_map.get("studio")
            if adapter is None:
                raise StudioCapabilityUnavailableError(
                    "Studio runtime capability is not registered; generic fallback is forbidden.",
                    details={"tool_name": tool_name, "capability": "studio"},
                )
            return adapter
        elif name_lower.startswith("run_command") or name_lower.startswith("subproc_") or name_lower in ("exec_command", "bash"):
            return self._capability_map.get("subprocess", self.default_adapter)
        elif name_lower.startswith("agent_") or name_lower in ("reason", "plan"):
            return self._capability_map.get("local_agent", self.default_adapter)
        elif name_lower.startswith("stateful_") or name_lower == "stateful":
            candidate = self._capability_map.get("stateful", self._stateful_runtime)
            if candidate is not None and hasattr(candidate, "dispatch"):
                return candidate  # type: ignore[return-value]
        return self._capability_map.get("tool", self.default_adapter)

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        adapter = self.resolve_adapter(request.tool_name)
        handle = await adapter.dispatch(request)
        self._handles_adapter_map[handle.handle_id] = adapter
        return handle

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        # Check stateful runtime first for handles created via stateful execute
        if self._stateful_runtime is not None and hasattr(self._stateful_runtime, "get_status"):
            try:
                # If handle exists in stateful store, delegate
                if hasattr(self._stateful_runtime, "_handles") and handle.handle_id in getattr(self._stateful_runtime, "_handles", {}):
                    return await self._stateful_runtime.get_status(handle)  # type: ignore[operator]
                if hasattr(self._stateful_runtime, "_statuses") and handle.handle_id in getattr(self._stateful_runtime, "_statuses", {}):
                    return await self._stateful_runtime.get_status(handle)  # type: ignore[operator]
            except Exception:
                pass
        adapter = self._handles_adapter_map.get(handle.handle_id, self.default_adapter)
        return await adapter.get_status(handle)

    async def cancel(self, handle: ExecutionHandle) -> None:
        # Try stateful first
        if self._stateful_runtime is not None and hasattr(self._stateful_runtime, "cancel"):
            try:
                if hasattr(self._stateful_runtime, "_handles") and handle.handle_id in getattr(self._stateful_runtime, "_handles", {}):
                    await self._stateful_runtime.cancel(handle)  # type: ignore[operator]
                    return
                if hasattr(self._stateful_runtime, "_statuses") and handle.handle_id in getattr(self._stateful_runtime, "_statuses", {}):
                    await self._stateful_runtime.cancel(handle)  # type: ignore[operator]
                    return
            except Exception:
                pass
        adapter = self._handles_adapter_map.get(handle.handle_id, self.default_adapter)
        await adapter.cancel(handle)

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        if self._stateful_runtime is not None and hasattr(self._stateful_runtime, "get_result"):
            try:
                if hasattr(self._stateful_runtime, "_handles") and handle.handle_id in getattr(self._stateful_runtime, "_handles", {}):
                    return await self._stateful_runtime.get_result(handle)  # type: ignore[operator]
            except Exception:
                pass
        adapter = self._handles_adapter_map.get(handle.handle_id, self.default_adapter)
        return await adapter.get_result(handle)

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        for adapter in self._capability_map.values():
            h = await adapter.reattach(runtime_run_id)
            if h:
                self._handles_adapter_map[h.handle_id] = adapter
                return h
        if self._stateful_runtime is not None and hasattr(self._stateful_runtime, "reattach"):
            try:
                h = await self._stateful_runtime.reattach(runtime_run_id)  # type: ignore[operator]
                if h:
                    return h
            except Exception:
                pass
        return None

    # Phase 3: Stateful eight-operation dispatch (host-owned substrate)

    async def create_session(self, request: CreateSessionRequest) -> RuntimeSession:
        runtime = self._require_stateful()
        return await runtime.create_session(request)

    async def attach_session(self, request: AttachSessionRequest) -> RuntimeSession | None:
        runtime = self._require_stateful()
        return await runtime.attach_session(request)

    async def execute(self, request: ExecutionRequest) -> ExecutionHandle:
        """Stateful execute - routes through stateful substrate when available and stores handle mapping."""
        if self._stateful_runtime is not None and hasattr(self._stateful_runtime, "execute"):
            try:
                handle = await self._stateful_runtime.execute(request)  # type: ignore[operator]
                # Store mapping for later cancel/get_status
                self._handles_adapter_map[handle.handle_id] = self._stateful_runtime  # type: ignore[assignment]
                return handle
            except Exception:
                raise
        return await self.dispatch(request)

    async def checkpoint(self, request: CheckpointRequest) -> CheckpointResult:
        runtime = self._require_stateful()
        return await runtime.checkpoint(request)

    async def restore(self, request: RestoreRequest) -> RestoreResult:
        runtime = self._require_stateful()
        return await runtime.restore(request)

    async def inspect(self, request: InspectRequest) -> InspectResult:
        runtime = self._require_stateful()
        return await runtime.inspect(request)

    async def terminate(self, request: TerminateRequest) -> TerminateResult:
        runtime = self._require_stateful()
        return await runtime.terminate(request)
