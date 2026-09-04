"""Tool executor — the only place that knows policy + runtime dispatch."""

from __future__ import annotations

from windagent.platform.security.contracts import PolicyDecision, PolicyEffect

from ..domain.errors import (
    AutomationPolicyApprovalRequiredError,
    AutomationPolicyDeniedError,
    AutomationRuntimeError,
)
from ..domain.invocation import ToolExecutionContext, ToolInvocation
from ..domain.result import ToolResult
from .policy import evaluate_policy
from .registry import RuntimeRegistry, ToolRegistry


class ToolExecutor:
    """Coordinates registry lookup → policy evaluation → runtime dispatch.

    The executor is deliberately stateless; every dependency is injected.
    It never touches SQL — the caller records runs via ``AutomationService``.
    """

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        runtime_registry: RuntimeRegistry,
        policy_engine: object | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._runtime_registry = runtime_registry
        self._policy_engine = policy_engine

    async def execute(
        self,
        invocation: ToolInvocation,
        ctx: ToolExecutionContext,
    ) -> tuple[ToolResult, PolicyDecision]:
        """Execute one invocation and return ``(result, policy_decision)``.

        Raises ``AutomationPolicyDeniedError`` or
        ``AutomationPolicyApprovalRequiredError`` when policy denies, so
        callers can distinguish policy failures from runtime failures.
        """
        definition = self._tool_registry.require(invocation.tool_name)
        if not definition.enabled:
            decision = PolicyDecision(effect=PolicyEffect.DENY, reason=f"tool [{definition.name}] is disabled", policy_id="tool-disabled")
            raise AutomationPolicyDeniedError(decision.reason or "tool disabled", context={"tool_name": definition.name, "policy_id": decision.policy_id or ""})

        decision = await evaluate_policy(self._policy_engine, definition, invocation, ctx) if self._policy_engine is not None else await evaluate_policy(None, definition, invocation, ctx)

        if decision.effect == PolicyEffect.DENY:
            raise AutomationPolicyDeniedError(decision.reason or "policy denied", context={"tool_name": definition.name, "policy_id": decision.policy_id or ""})
        if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
            raise AutomationPolicyApprovalRequiredError(
                decision.reason or "policy requires approval",
                context={"tool_name": definition.name, "policy_id": decision.policy_id or ""},
            )

        # Dispatch to runtime
        adapter = self._runtime_registry.get(definition.runtime_type.value)
        if adapter is None:
            # Fallback to in_process when specific runtime missing (e.g., remote not configured)
            adapter = self._runtime_registry.get("in_process")
        if adapter is None:
            raise AutomationRuntimeError(f"no runtime adapter for [{definition.runtime_type.value}]", context={"runtime_type": definition.runtime_type.value})

        try:
            result: ToolResult = await adapter.execute(invocation, ctx)  # type: ignore[attr-defined]
        except Exception as ex:
            raise AutomationRuntimeError(str(ex), context={"tool_name": definition.name}) from ex

        # Record audit in registry (best-effort)
        try:
            self._tool_registry.record_audit(definition.name, invocation.call_id, result.success, result.execution_time_ms)
        except Exception:
            pass
        return result, decision

    async def try_execute(
        self,
        invocation: ToolInvocation,
        ctx: ToolExecutionContext,
    ) -> tuple[ToolResult, PolicyDecision | None]:
        """Variant that never raises on policy denial — returns a synthetic ToolResult."""
        try:
            return await self.execute(invocation, ctx)
        except (AutomationPolicyDeniedError, AutomationPolicyApprovalRequiredError) as ex:
            status = "denied" if isinstance(ex, AutomationPolicyDeniedError) else "approval_required"
            decision = PolicyDecision(
                effect=PolicyEffect.DENY if status == "denied" else PolicyEffect.REQUIRE_APPROVAL,
                reason=str(ex),
                policy_id=str(ex.context.get("policy_id", "")) if ex.context else None,
            )
            result = ToolResult(call_id=invocation.call_id, success=False, error=str(ex), execution_time_ms=0.0)
            return result, decision
