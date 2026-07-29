"""Canonical browser tools backed by ``vercel-labs/agent-browser``."""

from __future__ import annotations

import hashlib
import time
from typing import Callable, Optional, Sequence

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_tools.base import (
    BaseTool,
    ToolDefinition,
    ToolExecutionContext,
    ToolRiskLevel,
)
from windagent_tools.browser.agent_browser import (
    AgentBrowserClient,
    AgentBrowserConfig,
    AgentBrowserError,
    SOCIAL_PLATFORM_DOMAINS,
    platform_for_url,
    resolve_workspace_artifact_path,
)


ClientFactory = Callable[[AgentBrowserConfig], AgentBrowserClient]


def _context_env(ctx: ToolExecutionContext) -> dict[str, str]:
    return {str(key): str(value) for key, value in ctx.env_vars.items()}


def _domains_for_request(
    url: str,
    platform: Optional[str],
    requested_domains: Optional[Sequence[str]],
) -> tuple[str, ...]:
    if requested_domains:
        return tuple(str(item).strip().lower() for item in requested_domains if str(item).strip())
    resolved_platform = platform or platform_for_url(url)
    if resolved_platform in SOCIAL_PLATFORM_DOMAINS:
        return SOCIAL_PLATFORM_DOMAINS[resolved_platform]
    return ()


class OpenURLTool(BaseTool):
    """Navigate with agent-browser and return rendered agent-readable text."""

    def __init__(self, client_factory: Optional[ClientFactory] = None):
        super().__init__(
            ToolDefinition(
                name="open_url",
                description=(
                    "Navigates with vercel-labs/agent-browser, waits for rendered DOM, "
                    "and returns bounded agent-readable page text with provenance."
                ),
                version="3.0.0",
                risk_level=ToolRiskLevel.EXTERNAL_NETWORK,
                capability="browser",
                side_effect_class="network",
                is_idempotent=True,
                is_destructive=False,
                is_reversible=True,
                timeout_seconds=90.0,
                required_permissions=["external_network"],
                sandbox_requirement="browser_sandbox",
                artifact_outputs=["screenshot", "dom_snapshot"],
                retry_eligible=True,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target web page URL"},
                        "platform": {
                            "type": "string",
                            "enum": ["facebook", "youtube", "tiktok", "generic"],
                        },
                        "session": {"type": "string"},
                        "allowed_domains": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "wait_until": {
                            "type": "string",
                            "enum": ["load", "domcontentloaded", "networkidle", "none"],
                            "default": "domcontentloaded",
                        },
                        "max_chars": {
                            "type": "integer",
                            "minimum": 1000,
                            "maximum": 2000000,
                        },
                        "screenshot_path": {
                            "type": "string",
                            "description": "Workspace-relative screenshot output path",
                        },
                        "close_session": {"type": "boolean", "default": True},
                        "allow_private_network": {"type": "boolean", "default": False},
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "final_url": {"type": "string"},
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "content_sha256": {"type": "string"},
                        "content_chars": {"type": "integer"},
                        "platform": {"type": ["string", "null"]},
                        "browser_backend": {"type": "string"},
                        "screenshot_path": {"type": ["string", "null"]},
                    },
                },
            )
        )
        self._client_factory = client_factory or (lambda config: AgentBrowserClient(config))

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        started = time.perf_counter()
        url = invocation.params.get("url")
        if not isinstance(url, str) or not url.strip():
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameter 'url' is required.",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )

        platform = invocation.params.get("platform")
        if platform == "generic":
            platform = None
        allowed_domains = _domains_for_request(
            url,
            platform,
            invocation.params.get("allowed_domains"),
        )
        screenshot_path = invocation.params.get("screenshot_path")
        resolved_screenshot = None
        if screenshot_path:
            try:
                resolved_screenshot = resolve_workspace_artifact_path(
                    ctx.workspace_root, str(screenshot_path)
                )
            except AgentBrowserError as exc:
                return ToolResult(
                    call_id=invocation.id,
                    success=False,
                    error=str(exc),
                    execution_time_ms=(time.perf_counter() - started) * 1000,
                )

        env = _context_env(ctx)
        try:
            config = AgentBrowserConfig.from_env(
                env,
                session=invocation.params.get("session"),
                allowed_domains=allowed_domains,
                timeout_seconds=invocation.timeout_seconds,
                max_output_chars=invocation.params.get("max_chars"),
                allow_private_network=bool(
                    invocation.params.get("allow_private_network", False)
                ),
            )
            client = self._client_factory(config)
            capture = await client.open_and_read(
                url.strip(),
                wait_until=invocation.params.get("wait_until", "domcontentloaded"),
                max_chars=invocation.params.get("max_chars"),
                screenshot_path=str(resolved_screenshot) if resolved_screenshot else None,
                close_session=bool(invocation.params.get("close_session", True)),
            )
            digest = hashlib.sha256(capture.text.encode("utf-8")).hexdigest()
            return ToolResult(
                call_id=invocation.id,
                success=True,
                data={
                    "url": capture.requested_url,
                    "final_url": capture.final_url,
                    "title": capture.title,
                    "content": capture.text,
                    "content_sha256": digest,
                    "content_chars": len(capture.text),
                    "platform": platform or platform_for_url(capture.final_url),
                    "browser_backend": "vercel-labs/agent-browser",
                    "session": config.session,
                    "screenshot_path": capture.screenshot_path,
                },
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )
        except (AgentBrowserError, ValueError, TypeError) as exc:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=f"Browser navigation failed: {type(exc).__name__}: {exc}",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )


class ClickXYTool(BaseTool):
    def __init__(self, client_factory: Optional[ClientFactory] = None):
        super().__init__(
            ToolDefinition(
                name="click_xy",
                description=(
                    "Clicks screen coordinates in an existing agent-browser session "
                    "using native mouse events."
                ),
                version="3.0.0",
                risk_level=ToolRiskLevel.WORKSPACE_WRITE,
                capability="browser",
                side_effect_class="process",
                is_idempotent=False,
                is_destructive=False,
                is_reversible=False,
                timeout_seconds=10.0,
                required_permissions=[],
                sandbox_requirement="browser_sandbox",
                artifact_outputs=["screenshot"],
                retry_eligible=False,
                redaction_policy="secrets_only",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "minimum": 0},
                        "y": {"type": "integer", "minimum": 0},
                        "session": {"type": "string"},
                    },
                    "required": ["x", "y"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "clicked_x": {"type": "integer"},
                        "clicked_y": {"type": "integer"},
                        "browser_backend": {"type": "string"},
                    },
                },
            )
        )
        self._client_factory = client_factory or (lambda config: AgentBrowserClient(config))

    async def execute(self, invocation: ToolInvocation, ctx: ToolExecutionContext) -> ToolResult:
        started = time.perf_counter()
        x = invocation.params.get("x")
        y = invocation.params.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameters 'x' and 'y' must be integers.",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )
        try:
            config = AgentBrowserConfig.from_env(
                _context_env(ctx),
                session=invocation.params.get("session"),
                allowed_domains=(),
                timeout_seconds=invocation.timeout_seconds,
            )
            client = self._client_factory(config)
            await client.click_xy(x, y)
            return ToolResult(
                call_id=invocation.id,
                success=True,
                data={
                    "clicked_x": x,
                    "clicked_y": y,
                    "browser_backend": "vercel-labs/agent-browser",
                    "session": config.session,
                },
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )
        except (AgentBrowserError, ValueError, TypeError) as exc:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=f"Browser click failed: {type(exc).__name__}: {exc}",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )
