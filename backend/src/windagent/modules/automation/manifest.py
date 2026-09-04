"""Module manifest for Automation (Phase 12).

Discovered automatically by ``PackageModuleDiscovery`` — no bootstrap file
needs to import this module by name except for testing.
"""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_automation_router
from .application.commands import (
    DeregisterTool,
    ExecuteTool,
    RegisterBuiltinTools,
    RegisterTool,
    UpdateTool,
)
from .application.handlers import (
    DeregisterToolHandler,
    ExecuteToolHandler,
    GetCapabilitiesHandler,
    GetToolByNameHandler,
    GetToolHandler,
    GetToolRunByInvocationHandler,
    GetToolRunHandler,
    ListRuntimeTypesHandler,
    ListToolRunsHandler,
    ListToolsHandler,
    RegisterBuiltinToolsHandler,
    RegisterToolHandler,
    UpdateToolHandler,
)
from .application.queries import (
    GetCapabilities,
    GetTool,
    GetToolByName,
    GetToolRun,
    GetToolRunByInvocation,
    ListRuntimeTypes,
    ListToolRuns,
    ListTools,
)
from .application.runtime import AutomationServices
from .jobs.handlers import AutomationToolExecuteJobHandler

AUTOMATION_JOB_TYPES = ("automation.tool.execute",)


def build_automation_manifest(services: AutomationServices | None = None) -> ModuleManifest:
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(RegisterTool, RegisterToolHandler(services)),
            CommandRegistration(UpdateTool, UpdateToolHandler(services)),
            CommandRegistration(DeregisterTool, DeregisterToolHandler(services)),
            CommandRegistration(ExecuteTool, ExecuteToolHandler(services)),
            CommandRegistration(RegisterBuiltinTools, RegisterBuiltinToolsHandler(services)),
        ),
        queries=(
            QueryRegistration(GetTool, GetToolHandler(services)),
            QueryRegistration(GetToolByName, GetToolByNameHandler(services)),
            QueryRegistration(ListTools, ListToolsHandler(services)),
            QueryRegistration(GetToolRun, GetToolRunHandler(services)),
            QueryRegistration(GetToolRunByInvocation, GetToolRunByInvocationHandler(services)),
            QueryRegistration(ListToolRuns, ListToolRunsHandler(services)),
            QueryRegistration(ListRuntimeTypes, ListRuntimeTypesHandler(services)),
            QueryRegistration(GetCapabilities, GetCapabilitiesHandler(services)),
        ),
        jobs=(JobRegistration("automation.tool.execute", AutomationToolExecuteJobHandler(services)),),
        routers=(create_automation_router(),),
        capabilities=(
            "automation",
            "tools",
            "execution",
            "in_process",
            "subprocess",
            "browser",
            "mcp",
            "desktop",
            "container",
            "remote",
        ),
    )


manifest = build_automation_manifest()
