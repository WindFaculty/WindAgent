"""Tool and runtime registries (Phase 12).

``ToolRegistry`` mirrors the frozen ``windagent_tools.registry.ToolRegistry``
semantics (namespace collision is an error, capability index, audit log) but
is re-expressed without legacy imports.

``RuntimeRegistry`` routes a ``RuntimeType`` to its concrete
``ToolRuntimeAdapter`` implementation (plan section 18: seven adapters).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from ..domain.definition import ToolDefinition
from ..domain.errors import AutomationConflictError

logger = logging.getLogger("windagent.automation.registry")


class ToolRegistry:
    """In-memory registry for tool definitions with collision detection."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._capability_index: dict[str, list[str]] = {}
        self._audit_log: list[dict[str, object]] = []

    def register(self, definition: ToolDefinition, *, override_collision: bool = False) -> None:
        name = definition.name
        if name in self._tools and not override_collision:
            raise AutomationConflictError(
                f"tool namespace collision: [{name}] already registered",
                context={"tool_name": name},
            )
        is_update = name in self._tools
        previous = self._tools.get(name)
        self._tools[name] = definition
        # Update capability index: remove from old capability if update
        if is_update and previous is not None and previous.capability != definition.capability:
            old_cap = previous.capability
            if old_cap in self._capability_index:
                self._capability_index[old_cap] = [n for n in self._capability_index[old_cap] if n != name]
        cap = definition.capability
        if cap not in self._capability_index:
            self._capability_index[cap] = []
        if name not in self._capability_index[cap]:
            self._capability_index[cap].append(name)
        logger.info("Registered tool [%s] (capability=%s risk=%s)", name, cap, definition.risk_level.value)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def require(self, name: str) -> ToolDefinition:
        tool = self.get(name)
        if tool is None:
            from ..domain.errors import AutomationNotFoundError

            raise AutomationNotFoundError(f"tool [{name}] not registered", context={"tool_name": name})
        return tool

    def list_definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools.values())

    def list_by_capability(self, capability: str) -> tuple[ToolDefinition, ...]:
        names = self._capability_index.get(capability, [])
        return tuple(self._tools[n] for n in names)

    def remove(self, name: str) -> bool:
        existing = self._tools.pop(name, None)
        if existing is None:
            return False
        cap = existing.capability
        if cap in self._capability_index:
            self._capability_index[cap] = [n for n in self._capability_index[cap] if n != name]
        return True

    def record_audit(
        self, tool_name: str, call_id: str, success: bool, execution_time_ms: float
    ) -> None:
        self._audit_log.append(
            {
                "tool_name": tool_name,
                "call_id": call_id,
                "success": success,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def get_audit_log(self) -> tuple[dict[str, object], ...]:
        return tuple(self._audit_log)


class RuntimeRegistry:
    """Routes ``RuntimeType`` to a concrete ``ToolRuntimeAdapter``."""

    def __init__(self, adapters: dict[str, object] | None = None) -> None:
        self._adapters: dict[str, object] = {}
        if adapters:
            for rt, adapter in adapters.items():
                self._adapters[rt.lower()] = adapter
        # Lazy import defaults only when not provided, to keep tests deterministic
        if not self._adapters:
            self._load_defaults()

    def _load_defaults(self) -> None:
        from ..infrastructure.adapters.browser import BrowserAdapter
        from ..infrastructure.adapters.container import ContainerAdapter
        from ..infrastructure.adapters.desktop import DesktopAdapter
        from ..infrastructure.adapters.in_process import InProcessAdapter
        from ..infrastructure.adapters.mcp import McpAdapter
        from ..infrastructure.adapters.remote import RemoteAdapter
        from ..infrastructure.adapters.subprocess import SubprocessAdapter

        self._adapters = {
            "in_process": InProcessAdapter(),
            "subprocess": SubprocessAdapter(),
            "browser": BrowserAdapter(),
            "mcp": McpAdapter(),
            "desktop": DesktopAdapter(),
            "container": ContainerAdapter(),
            "remote": RemoteAdapter(),
        }

    def register(self, runtime_type: str, adapter: object) -> None:
        self._adapters[runtime_type.lower()] = adapter

    def get(self, runtime_type: str) -> object | None:
        return self._adapters.get(runtime_type.lower())

    def require(self, runtime_type: str) -> object:
        adapter = self.get(runtime_type)
        if adapter is None:
            from ..domain.errors import AutomationNotFoundError

            raise AutomationNotFoundError(
                f"runtime [{runtime_type}] not registered", context={"runtime_type": runtime_type}
            )
        return adapter

    def list_runtime_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters.keys()))
