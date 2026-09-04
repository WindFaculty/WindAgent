"""Thin command/query/job handlers — identical structure to studio/model_gateway."""

from __future__ import annotations

from typing import Any

from ..domain.definition import RuntimeType, ToolDefinition, ToolRiskLevel
from ..domain.errors import AutomationValidationError
from .commands import DeregisterTool, ExecuteTool, RegisterBuiltinTools, RegisterTool, UpdateTool
from .queries import (
    GetCapabilities,
    GetTool,
    GetToolByName,
    GetToolRun,
    GetToolRunByInvocation,
    ListRuntimeTypes,
    ListToolRuns,
    ListTools,
)
from .runtime import AutomationServices, resolve_services


def _require_text(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutomationValidationError(f"{field} cannot be blank.")
    return value.strip()


class RegisterToolHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: RegisterTool) -> Any:
        services = resolve_services(self._services)
        # Validate enums
        try:
            risk = ToolRiskLevel(cmd.risk_level)
        except ValueError as exc:
            raise AutomationValidationError(f"unknown risk_level {cmd.risk_level!r}") from exc
        try:
            rt = RuntimeType(cmd.runtime_type)
        except ValueError as exc:
            raise AutomationValidationError(f"unknown runtime_type {cmd.runtime_type!r}") from exc
        definition = ToolDefinition(
            name=_require_text(cmd.name, "name"),
            description=_require_text(cmd.description, "description"),
            version=_require_text(cmd.version, "version"),
            risk_level=risk,
            capability=_require_text(cmd.capability, "capability"),
            runtime_type=rt,
            side_effect_class=cmd.side_effect_class,
            is_idempotent=cmd.is_idempotent,
            is_destructive=cmd.is_destructive,
            is_reversible=cmd.is_reversible,
            timeout_seconds=cmd.timeout_seconds,
            required_permissions=tuple(cmd.required_permissions),
            sandbox_requirement=cmd.sandbox_requirement,
            artifact_outputs=tuple(cmd.artifact_outputs),
            retry_eligible=cmd.retry_eligible,
            redaction_policy=cmd.redaction_policy,
            parameters_schema=dict(cmd.parameters_schema),
            output_schema=dict(cmd.output_schema),
            enabled=cmd.enabled,
        )
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.register_tool(definition)


class UpdateToolHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: UpdateTool) -> Any:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.update_tool(
            tool_id=_require_text(cmd.tool_id, "tool_id"),
            description=cmd.description,
            version=cmd.version,
            risk_level=cmd.risk_level,
            capability=cmd.capability,
            runtime_type=cmd.runtime_type,
            enabled=cmd.enabled,
            expected_version=cmd.expected_version,
        )


class DeregisterToolHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: DeregisterTool) -> None:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        await container.automation.deregister_tool(_require_text(cmd.tool_id, "tool_id"))


class ExecuteToolHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: ExecuteTool) -> Any:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.execute_tool(
            tool_name=_require_text(cmd.tool_name, "tool_name"),
            params=dict(cmd.params),
            workspace_root=cmd.workspace_root,
            actor_id=cmd.actor_id,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            trace_id=cmd.trace_id,
            user_approved=cmd.user_approved,
            invocation_id=cmd.invocation_id,
        )


class RegisterBuiltinToolsHandler:
    """Registers the canonical 12 built-ins + 7 runtime capabilities."""

    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, cmd: RegisterBuiltinTools) -> tuple[Any, ...]:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        # Catalog mirrors frozen windagent_tools.builtin_registry + extra runtimes
        catalog: list[ToolDefinition] = [
            ToolDefinition(
                name="read_file",
                description="Reads text content from a file safely within workspace sandbox.",
                risk_level=ToolRiskLevel.READ_ONLY,
                capability="filesystem",
                runtime_type=RuntimeType.IN_PROCESS,
                side_effect_class="none",
                is_idempotent=True,
                is_destructive=False,
                sandbox_requirement="path_sandbox",
                parameters_schema={"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]},
            ),
            ToolDefinition(
                name="write_file",
                description="Writes text content atomically to a file within workspace sandbox.",
                risk_level=ToolRiskLevel.WORKSPACE_WRITE,
                capability="filesystem",
                runtime_type=RuntimeType.IN_PROCESS,
                side_effect_class="filesystem",
                is_idempotent=True,
                is_destructive=False,
                sandbox_requirement="path_sandbox",
                required_permissions=("workspace_write",),
                parameters_schema={"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_path", "content"]},
            ),
            ToolDefinition(
                name="exec_shell",
                description="Executes a shell command safely within workspace root with policy enforcement.",
                risk_level=ToolRiskLevel.PROCESS_EXECUTION,
                capability="shell",
                runtime_type=RuntimeType.SUBPROCESS,
                side_effect_class="process",
                is_idempotent=False,
                is_destructive=True,
                is_reversible=False,
                sandbox_requirement="subprocess_sandbox",
                required_permissions=("process_execution",),
            ),
            ToolDefinition(
                name="code_search",
                description="Search code via grep over workspace.",
                risk_level=ToolRiskLevel.READ_ONLY,
                capability="code",
                runtime_type=RuntimeType.IN_PROCESS,
                side_effect_class="none",
            ),
            ToolDefinition(
                name="git",
                description="Git operations scoped to workspace.",
                risk_level=ToolRiskLevel.WORKSPACE_WRITE,
                capability="vcs",
                runtime_type=RuntimeType.SUBPROCESS,
                side_effect_class="process",
                sandbox_requirement="subprocess_sandbox",
            ),
            ToolDefinition(
                name="ast_symbol",
                description="AST symbol extraction.",
                risk_level=ToolRiskLevel.READ_ONLY,
                capability="code",
                runtime_type=RuntimeType.IN_PROCESS,
                side_effect_class="none",
            ),
            ToolDefinition(
                name="lsp",
                description="Language server diagnostics.",
                risk_level=ToolRiskLevel.READ_ONLY,
                capability="code",
                runtime_type=RuntimeType.IN_PROCESS,
                side_effect_class="none",
            ),
            ToolDefinition(
                name="test_runner",
                description="Run test suites.",
                risk_level=ToolRiskLevel.PROCESS_EXECUTION,
                capability="testing",
                runtime_type=RuntimeType.SUBPROCESS,
                side_effect_class="process",
                sandbox_requirement="subprocess_sandbox",
            ),
            ToolDefinition(
                name="open_url",
                description="Open URL in browser.",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
                capability="browser",
                runtime_type=RuntimeType.BROWSER,
                side_effect_class="network",
                sandbox_requirement="browser_sandbox",
            ),
            ToolDefinition(
                name="click_xy",
                description="Click at x,y in browser.",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
                capability="browser",
                runtime_type=RuntimeType.BROWSER,
                side_effect_class="network",
                sandbox_requirement="browser_sandbox",
            ),
            ToolDefinition(
                name="database_query",
                description="Read-only database query.",
                risk_level=ToolRiskLevel.SECRET_ACCESS,
                capability="database",
                runtime_type=RuntimeType.IN_PROCESS,
                side_effect_class="database",
            ),
            ToolDefinition(
                name="github",
                description="GitHub API interaction.",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
                capability="external",
                runtime_type=RuntimeType.REMOTE,
                side_effect_class="network",
            ),
            # Extra runtime probes so all 7 runtimes are visible via capabilities query
            ToolDefinition(
                name="mcp_call",
                description="Model Context Protocol tool invocation.",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
                capability="mcp",
                runtime_type=RuntimeType.MCP,
                side_effect_class="network",
            ),
            ToolDefinition(
                name="desktop_capture",
                description="Desktop native capture (IPC).",
                risk_level=ToolRiskLevel.PRIVILEGED,
                capability="desktop",
                runtime_type=RuntimeType.DESKTOP,
                side_effect_class="process",
            ),
            ToolDefinition(
                name="container_exec",
                description="Execute in isolated container.",
                risk_level=ToolRiskLevel.PROCESS_EXECUTION,
                capability="container",
                runtime_type=RuntimeType.CONTAINER,
                side_effect_class="process",
            ),
            ToolDefinition(
                name="remote_invoke",
                description="Invoke remote tool endpoint.",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
                capability="remote",
                runtime_type=RuntimeType.REMOTE,
                side_effect_class="network",
            ),
        ]
        results = []
        for definition in catalog:
            try:
                view = await container.automation.register_tool(definition)
                results.append(view)
            except Exception:
                # idempotent: if already exists, fetch existing view
                try:
                    view = await container.automation.get_tool_by_name(definition.name)
                    results.append(view)
                except Exception:
                    pass
        return tuple(results)


# -- queries -----------------------------------------------------------------


class GetToolHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetTool) -> Any:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.get_tool(_require_text(query.tool_id, "tool_id"))


class GetToolByNameHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetToolByName) -> Any:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.get_tool_by_name(_require_text(query.name, "name"))


class ListToolsHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListTools) -> tuple[Any, ...]:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.list_tools(
            capability=query.capability, runtime_type=query.runtime_type, enabled_only=query.enabled_only
        )


class GetToolRunHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetToolRun) -> Any:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.get_run(_require_text(query.run_id, "run_id"))


class GetToolRunByInvocationHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetToolRunByInvocation) -> Any:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.get_run_by_invocation(_require_text(query.invocation_id, "invocation_id"))


class ListToolRunsHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListToolRuns) -> tuple[Any, ...]:
        services = resolve_services(self._services)
        from .runtime import container_for

        container = container_for(services)
        return await container.automation.list_runs(tool_name=query.tool_name, status=query.status, limit=query.limit)


class ListRuntimeTypesHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, query: ListRuntimeTypes) -> tuple[str, ...]:
        services = resolve_services(self._services)
        return services.runtime_registry.list_runtime_types()


class GetCapabilitiesHandler:
    def __init__(self, services: AutomationServices | None = None) -> None:
        self._services = services

    async def handle(self, query: GetCapabilities) -> tuple[dict[str, object], ...]:
        services = resolve_services(self._services)
        # Expose capabilities as {capability, tools: [names]}
        tools = await ListToolsHandler(services).handle(ListTools())
        bucket: dict[str, list[str]] = {}
        for view in tools:
            bucket.setdefault(view.capability, []).append(view.name)
        return tuple({"capability": cap, "tools": sorted(names), "count": len(names)} for cap, names in sorted(bucket.items()))
