"""Public surface of the Automation bounded context."""

from ..api.routes import AUTOMATION_PREFIX, MODULE_ID, MODULE_VERSION, create_automation_router
from ..application.models import ToolRunView, ToolView
from ..application.registry import RuntimeRegistry, ToolRegistry
from ..application.runtime import AutomationServices, bind_services
from ..domain.definition import RuntimeType, ToolDefinition, ToolRiskLevel
from ..domain.invocation import ToolExecutionContext, ToolInvocation
from ..domain.result import ToolResult
from ..infrastructure.adapters.base import ToolRuntimeAdapter
from ..infrastructure.memory import InMemoryAutomationStore, memory_scope_factory
from ..infrastructure.repository import SqlAutomationStore, sql_scope_factory
from ..manifest import AUTOMATION_JOB_TYPES, build_automation_manifest, manifest

__all__ = [
    "AUTOMATION_JOB_TYPES",
    "AUTOMATION_PREFIX",
    "AutomationServices",
    "InMemoryAutomationStore",
    "MODULE_ID",
    "MODULE_VERSION",
    "RuntimeRegistry",
    "RuntimeType",
    "SqlAutomationStore",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolInvocation",
    "ToolRegistry",
    "ToolResult",
    "ToolRiskLevel",
    "ToolRunView",
    "ToolRuntimeAdapter",
    "ToolView",
    "bind_services",
    "build_automation_manifest",
    "create_automation_router",
    "manifest",
    "memory_scope_factory",
    "sql_scope_factory",
]
