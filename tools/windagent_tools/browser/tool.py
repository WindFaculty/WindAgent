"""Canonical browser tools backed by ``vercel-labs/agent-browser``."""

from __future__ import annotations

import hashlib
import time
from typing import Callable, Optional, Sequence

from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_core.security.types import PermissionEvaluationRequest, Principal, RiskLevel
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
    AgentBrowserPolicyError,
    BrowserAuditLogger,
    SOCIAL_PLATFORM_DOMAINS,
    is_retryable_browser_error,
    platform_for_url,
    resolve_workspace_artifact_path,
)
from windagent_tools.security.permission_engine import PermissionEngine

ClientFactory = Callable[[AgentBrowserConfig], AgentBrowserClient]


def _context_env(ctx: ToolExecutionContext) -> dict[str, str]:
    return {str(key): str(value) for key, value in ctx.env_vars.items()}


def _authenticated_browser_options(
    invocation: ToolInvocation,
    ctx: ToolExecutionContext,
) -> tuple[dict[str, str], bool, Optional[str]]:
    """Resolve an explicit, per-invocation Chrome-profile opt-in."""
    authenticated = bool(invocation.params.get("authenticated", False))
    profile_value = invocation.params.get("profile")
    if profile_value is not None and not isinstance(profile_value, str):
        raise AgentBrowserPolicyError("Browser profile must be a string.")
    profile = profile_value.strip() if isinstance(profile_value, str) else None
    if profile == "":
        raise AgentBrowserPolicyError("Browser profile cannot be empty.")
    env = _context_env(ctx)
    if authenticated:
        # The default is intentionally activated only by an explicit opt-in.
        profile = profile or env.get("AGENT_BROWSER_PROFILE") or "Default"
        env["WINDAGENT_BROWSER_AUTHENTICATED"] = "1"
        env["AGENT_BROWSER_PROFILE"] = profile
        # agent-browser does not combine native domain containment with a
        # profile. Preflight preserves WindAgent's URL checks before/after nav.
        env.setdefault("WINDAGENT_BROWSER_CONTAINMENT", "preflight")
    return env, authenticated, profile


def _domains_for_request(
    url: str,
    platform: Optional[str],
    requested_domains: Optional[Sequence[str]],
) -> tuple[str, ...]:
    if requested_domains:
        return tuple(
            str(item).strip().lower() for item in requested_domains if str(item).strip()
        )
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
                        "authenticated": {
                            "type": "boolean",
                            "default": False,
                            "description": "Explicitly allow use of the selected Chrome profile",
                        },
                        "profile": {
                            "type": "string",
                            "description": "Chrome profile name or path; defaults to Default when authenticated",
                        },
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
                        "include_snapshot": {
                            "type": "boolean",
                            "default": False,
                            "description": "Return accessibility snapshot refs for semantic actions",
                        },
                        "include_session_health": {
                            "type": "boolean",
                            "default": False,
                            "description": "Return safe session diagnostics without cookie values",
                        },
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
                        "session": {"type": "string"},
                        "authenticated": {"type": "boolean"},
                        "profile": {"type": ["string", "null"]},
                        "screenshot_path": {"type": ["string", "null"]},
                        "snapshot": {"type": ["string", "null"]},
                        "session_health": {"type": ["object", "null"]},
                    },
                },
            )
        )
        self._client_factory = client_factory or (
            lambda config: AgentBrowserClient(config)
        )
        self._permission_engine = PermissionEngine()
        self._audit_logger = BrowserAuditLogger()

    async def execute(
        self, invocation: ToolInvocation, ctx: ToolExecutionContext
    ) -> ToolResult:
        started = time.perf_counter()
        url = invocation.params.get("url")
        if not isinstance(url, str) or not url.strip():
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Parameter 'url' is required.",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )

        # PermissionEngine check before any browser navigation
        principal = ctx.principal or Principal(id="anonymous", roles=["user"], permissions=[])
        perm_req = PermissionEvaluationRequest(
            principal=principal,
            action="open_url",
            target=url.strip(),
            risk_level=RiskLevel.HIGH,
            context={
                "workspace_root": ctx.workspace_root,
                "user_approved": ctx.user_approved,
                "is_destructive": False,
                "required_permissions": self.definition.required_permissions,
            },
        )
        perm_decision = self._permission_engine.evaluate_request(perm_req)
        if not perm_decision.is_allowed:
            self._audit_logger.log_event(
                "deny",
                str(invocation.params.get("session", "windagent")),
                {
                    "requested_url": url.strip(),
                    "principal_id": principal.id if hasattr(principal, "id") else "anonymous",
                    "reason_code": perm_decision.reason_code,
                    "human_reason": perm_decision.human_reason,
                },
            )
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=f"Permission denied: {perm_decision.human_reason}",
                data={"decision_id": str(perm_decision.decision_id), "reason_code": perm_decision.reason_code},
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
                self._audit_logger.log_event(
                    "error",
                    str(invocation.params.get("session", "windagent")),
                    {
                        "requested_url": url.strip(),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
                return ToolResult(
                    call_id=invocation.id,
                    success=False,
                    error=str(exc),
                    execution_time_ms=(time.perf_counter() - started) * 1000,
                )

        try:
            env, authenticated, profile = _authenticated_browser_options(
                invocation, ctx
            )
            config = AgentBrowserConfig.from_env(
                env,
                session=invocation.params.get("session"),
                authenticated=authenticated,
                profile=profile,
                allowed_domains=allowed_domains,
                timeout_seconds=invocation.timeout_seconds,
                max_output_chars=invocation.params.get("max_chars"),
                allow_private_network=bool(
                    invocation.params.get("allow_private_network", False)
                ),
            )
            client = self._client_factory(config)
            close_session = bool(invocation.params.get("close_session", True))
            needs_followup_read = bool(
                invocation.params.get("include_snapshot", False)
                or invocation.params.get("include_session_health", False)
            )
            try:
                capture = await client.open_and_read(
                    url.strip(),
                    wait_until=invocation.params.get("wait_until", "domcontentloaded"),
                    max_chars=invocation.params.get("max_chars"),
                    screenshot_path=str(resolved_screenshot)
                    if resolved_screenshot
                    else None,
                    close_session=close_session and not needs_followup_read,
                )

                # Post-navigation redirect validation against containment policy
                if capture.final_url and capture.final_url.strip() != capture.requested_url.strip():
                    validate_navigation_url(
                        capture.final_url,
                        allowed_domains=allowed_domains,
                        allow_private_network=config.allow_private_network,
                    )
                    self._audit_logger.log_event(
                        "redirect",
                        config.session,
                        {
                            "requested_url": capture.requested_url,
                            "final_url": capture.final_url,
                            "principal_id": principal.id if hasattr(principal, "id") else "anonymous",
                        },
                    )

                snapshot = (
                    await client.snapshot()
                    if bool(invocation.params.get("include_snapshot", False))
                    else None
                )
                session_health = (
                    await client.session_health()
                    if bool(invocation.params.get("include_session_health", False))
                    else None
                )
            finally:
                if close_session and needs_followup_read:
                    await client.close()

            if capture.screenshot_path:
                self._audit_logger.log_event(
                    "screenshot",
                    config.session,
                    {
                        "requested_url": capture.requested_url,
                        "screenshot_path": capture.screenshot_path,
                    },
                )

            digest = hashlib.sha256(capture.text.encode("utf-8")).hexdigest()
            self._audit_logger.log_event(
                "open_url",
                config.session,
                {
                    "requested_url": capture.requested_url,
                    "final_url": capture.final_url,
                    "principal_id": principal.id if hasattr(principal, "id") else "anonymous",
                    "authenticated": config.authenticated,
                    "profile": config.profile,
                },
            )
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
                    "authenticated": config.authenticated,
                    "profile": config.profile,
                    "screenshot_path": capture.screenshot_path,
                    "snapshot": snapshot,
                    "session_health": session_health,
                },
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )
        except (AgentBrowserError, ValueError, TypeError) as exc:
            self._audit_logger.log_event(
                "error",
                str(invocation.params.get("session", "windagent")),
                {
                    "requested_url": url.strip(),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            return ToolResult(
                call_id=invocation.id,
                success=False,
                data=(
                    {
                        "error_type": type(exc).__name__,
                        "retryable": is_retryable_browser_error(exc),
                    }
                    if isinstance(exc, AgentBrowserError)
                    else {"error_type": type(exc).__name__, "retryable": False}
                ),
                error=f"Browser navigation failed: {type(exc).__name__}: {exc}",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )


class ClickXYTool(BaseTool):
    """Canonical click tool with semantic targets; coordinates are legacy fallback."""

    def __init__(self, client_factory: Optional[ClientFactory] = None):
        super().__init__(
            ToolDefinition(
                name="click_xy",
                description=(
                    "Clicks a snapshot reference, semantic locator, or (as a legacy "
                    "fallback) screen coordinates in an existing agent-browser session."
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
                        "target": {
                            "type": "string",
                            "description": "@ref, CSS selector, or semantic-locator value",
                        },
                        "locator": {
                            "type": "string",
                            "enum": [
                                "ref",
                                "css",
                                "alt",
                                "label",
                                "placeholder",
                                "role",
                                "testid",
                                "text",
                                "title",
                            ],
                            "default": "ref",
                        },
                        "session": {"type": "string"},
                        "authenticated": {"type": "boolean", "default": False},
                        "profile": {"type": "string"},
                    },
                    "anyOf": [
                        {"required": ["x", "y"]},
                        {"required": ["target"]},
                    ],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "clicked_x": {"type": ["integer", "null"]},
                        "clicked_y": {"type": ["integer", "null"]},
                        "clicked_target": {"type": ["string", "null"]},
                        "browser_backend": {"type": "string"},
                        "session": {"type": "string"},
                    },
                },
            )
        )
        self._client_factory = client_factory or (
            lambda config: AgentBrowserClient(config)
        )
        self._permission_engine = PermissionEngine()
        self._audit_logger = BrowserAuditLogger()

    async def execute(
        self, invocation: ToolInvocation, ctx: ToolExecutionContext
    ) -> ToolResult:
        started = time.perf_counter()
        target = invocation.params.get("target")
        x = invocation.params.get("x")
        y = invocation.params.get("y")
        using_target = isinstance(target, str) and bool(target.strip())
        if not using_target and (not isinstance(x, int) or not isinstance(y, int)):
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error="Provide a semantic 'target' or integer parameters 'x' and 'y'.",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )

        # PermissionEngine check before any browser click action
        principal = ctx.principal or Principal(id="anonymous", roles=["user"], permissions=[])
        perm_req = PermissionEvaluationRequest(
            principal=principal,
            action="click_xy",
            target=target.strip() if using_target else f"coordinates ({x},{y})",
            risk_level=RiskLevel.MEDIUM,
            context={
                "workspace_root": ctx.workspace_root,
                "user_approved": ctx.user_approved,
                "is_destructive": False,
                "required_permissions": self.definition.required_permissions,
            },
        )
        perm_decision = self._permission_engine.evaluate_request(perm_req)
        if not perm_decision.is_allowed:
            self._audit_logger.log_event(
                "deny",
                str(invocation.params.get("session", "windagent")),
                {
                    "requested_target": target.strip() if using_target else f"coordinates ({x},{y})",
                    "principal_id": principal.id if hasattr(principal, "id") else "anonymous",
                    "reason_code": perm_decision.reason_code,
                    "human_reason": perm_decision.human_reason,
                },
            )
            return ToolResult(
                call_id=invocation.id,
                success=False,
                error=f"Permission denied: {perm_decision.human_reason}",
                data={
                    "decision_id": str(perm_decision.decision_id),
                    "reason_code": perm_decision.reason_code,
                },
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )

        try:
            env, authenticated, profile = _authenticated_browser_options(
                invocation, ctx
            )
            config = AgentBrowserConfig.from_env(
                env,
                session=invocation.params.get("session"),
                authenticated=authenticated,
                profile=profile,
                allowed_domains=(),
                timeout_seconds=invocation.timeout_seconds,
            )
            client = self._client_factory(config)
            if using_target:
                await client.click_target(
                    target.strip(),
                    locator=str(invocation.params.get("locator", "ref")),
                )
            else:
                await client.click_xy(x, y)
            self._audit_logger.log_event(
                "click_xy",
                config.session,
                {
                    "target": target.strip() if using_target else f"({x},{y})",
                    "principal_id": principal.id if hasattr(principal, "id") else "anonymous",
                },
            )
            return ToolResult(
                call_id=invocation.id,
                success=True,
                data={
                    "clicked_x": None if using_target else x,
                    "clicked_y": None if using_target else y,
                    "clicked_target": target.strip() if using_target else None,
                    "browser_backend": "vercel-labs/agent-browser",
                    "session": config.session,
                },
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )
        except (AgentBrowserError, ValueError, TypeError) as exc:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                data=(
                    {
                        "error_type": type(exc).__name__,
                        "retryable": is_retryable_browser_error(exc),
                    }
                    if isinstance(exc, AgentBrowserError)
                    else {"error_type": type(exc).__name__, "retryable": False}
                ),
                error=f"Browser click failed: {type(exc).__name__}: {exc}",
                execution_time_ms=(time.perf_counter() - started) * 1000,
            )