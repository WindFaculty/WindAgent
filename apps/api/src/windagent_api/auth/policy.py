"""Route-level authorization through the Policy Engine.

``require_policy(action, resource_type)`` builds a FastAPI dependency that
evaluates the composition-root policy engine and enforces the outcome:

- ``ALLOW``            → the route runs; the decision is returned to it.
- ``DENY``             → 403 ``forbidden``.
- ``REQUIRE_APPROVAL`` → 403 ``require_approval`` (no approval workflow
  exists until the agent-runtime approvals phase, so approval-gated
  operations are never executed as a side effect of an HTTP request).

Every evaluated decision is written to the audit sink.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final, cast

from fastapi import Request
from windagent.kernel.time import utc_now
from windagent.platform.observability import current_operation_context
from windagent.platform.security import (
    AuditEvent,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
)

from ..errors import ApiError
from .principal import Principal, get_principal

POLICY_UNCONFIGURED_POLICY_ID: Final[str] = "policy-unconfigured"


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


def require_policy(
    action: str, resource_type: str
) -> Callable[[Request], Awaitable[PolicyDecision]]:
    """Build the authorization dependency for one (action, resource) pair."""
    normalized_action = _required_text(action, "action")
    normalized_resource_type = _required_text(resource_type, "resource_type")

    async def dependency(request: Request) -> PolicyDecision:
        principal = get_principal(request)
        engine = getattr(request.app.state, "policy_engine", None)
        if engine is None:
            # Explicitly unsecured development mode: authorization is open,
            # and the composition root is responsible for never shipping
            # that configuration to production.
            return PolicyDecision(
                effect=PolicyEffect.ALLOW,
                reason="no policy engine is configured",
                policy_id=POLICY_UNCONFIGURED_POLICY_ID,
            )

        decision = await cast(PolicyEngine, engine).decide(
            PolicyRequest(
                action=normalized_action,
                resource_type=normalized_resource_type,
                actor_id=principal.actor_id,
                context={"principal_source": principal.source},
            )
        )
        await _audit(request, principal, decision, normalized_action, normalized_resource_type)

        if decision.effect is PolicyEffect.DENY:
            raise ApiError(
                403,
                code="forbidden",
                message=decision.reason or "denied by policy",
                context={"policy_id": decision.policy_id},
            )
        if decision.effect is PolicyEffect.REQUIRE_APPROVAL:
            raise ApiError(
                403,
                code="require_approval",
                message=decision.reason or "operation requires approval",
                context={"policy_id": decision.policy_id},
            )
        return decision

    return dependency


async def _audit(
    request: Request,
    principal: Principal,
    decision: PolicyDecision,
    action: str,
    resource_type: str,
) -> None:
    sink = getattr(request.app.state, "audit_sink", None)
    if sink is None:
        return
    operation_context = current_operation_context()
    await sink.record(
        AuditEvent(
            action=action,
            resource_type=resource_type,
            outcome=decision.effect.value,
            actor_id=principal.actor_id,
            correlation_id=(
                operation_context.correlation_id
                if operation_context is not None
                else None
            ),
            causation_id=(
                operation_context.causation_id
                if operation_context is not None
                else None
            ),
            trace_id=(
                operation_context.trace_id if operation_context is not None else None
            ),
            reason=decision.reason,
            details=(
                {"policy_id": decision.policy_id} if decision.policy_id else {}
            ),
            occurred_at=utc_now(),
        )
    )
