"""Policy helper for tool execution (Phase 12).

Converts a ``ToolDefinition`` + ``ToolInvocation`` + ``ToolExecutionContext``
into a platform ``PolicyRequest`` and evaluates it via a platform
``PolicyEngine``.

Decision mapping preserves the old permission_engine semantics:

- ``HARD_DENY_ACTIONS`` always deny (even with approval).
- Path-scope violations deny when a file param escapes ``workspace_root``.
- Destructive / high-risk without ``user_approved`` yields
  ``REQUIRE_APPROVAL`` (the frozen destructive guard).

The execution layer calls :meth:`evaluate` before dispatching to any runtime.
"""

from __future__ import annotations

from windagent.kernel.ids import ActorId
from windagent.platform.security.contracts import PolicyDecision, PolicyEffect, PolicyRequest

from ..domain.definition import HIGH_RISK_LEVELS, ToolDefinition
from ..domain.invocation import ToolExecutionContext, ToolInvocation
from ..domain.policy_mapping import HARD_DENY_ACTIONS, is_policy_gated, risk_to_policy_level
from ..domain.sandbox import is_within_workspace


def _maybe_actor_id(value: str | None) -> ActorId | None:
    if value is None:
        return None
    try:
        return ActorId(value)
    except Exception:
        return None


def build_policy_request(
    definition: ToolDefinition,
    invocation: ToolInvocation,
    ctx: ToolExecutionContext,
) -> PolicyRequest:
    """Build a platform ``PolicyRequest`` from automation domain objects."""
    # Extract potential file path for sandbox gating
    target_path = (
        str(invocation.params.get("file_path") or invocation.params.get("path") or "")
        or definition.name
    )

    # Use capability as resource_type where available; fallback to definition's
    # side-effect grouping so rules can target `filesystem`, `process`, etc.
    resource_type = definition.capability or definition.side_effect_class or "automation_tool"
    actor = _maybe_actor_id(ctx.actor_id)
    context_dict: dict[str, object] = {
        "tool_name": definition.name,
        "risk_level": definition.risk_level.value,
        "policy_risk": risk_to_policy_level(definition.risk_level),
        "runtime_type": definition.runtime_type.value,
        "capability": definition.capability,
        "side_effect_class": definition.side_effect_class,
        "target_path": target_path,
        "workspace_root": ctx.workspace_root,
        "user_approved": ctx.user_approved,
        "required_permissions": list(definition.required_permissions),
        "is_destructive": definition.is_destructive,
        "is_policy_gated": is_policy_gated(
            definition.name, capability=definition.capability, side_effect_class=definition.side_effect_class
        ),
    }
    # Carry correlation metadata
    if ctx.correlation_id:
        context_dict["correlation_id"] = ctx.correlation_id
    if ctx.trace_id:
        context_dict["trace_id"] = ctx.trace_id
    return PolicyRequest(
        action=definition.name,
        resource_type=resource_type,
        actor_id=actor,
        resource_id=None,
        context=context_dict,
    )


async def evaluate_policy(
    engine: object,
    definition: ToolDefinition,
    invocation: ToolInvocation,
    ctx: ToolExecutionContext,
) -> PolicyDecision:
    """Evaluate the policy engine and return its decision (fail-closed).

    Also applies the frozen hard-deny and path-scope checks before invoking
    the engine, so the engine never sees an already-denied request.
    """
    # Hard-deny fast path (no engine call needed for parity)
    lower_name = definition.name.lower()
    if lower_name in HARD_DENY_ACTIONS:
        return PolicyDecision(
            effect=PolicyEffect.DENY,
            reason=f"action [{definition.name}] matches hard-deny policy",
            policy_id="hard-deny",
        )
    # Path-scope for filesystem tools
    gated = is_policy_gated(
        definition.name, capability=definition.capability, side_effect_class=definition.side_effect_class
    )
    if gated and definition.sandbox_requirement == "path_sandbox":
        target = str(invocation.params.get("file_path") or invocation.params.get("path") or "")
        if target and not is_within_workspace(target, ctx.workspace_root):
            # Try to handle relative paths: if target is not absolute we already normalized inside is_within_workspace
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                reason=f"path [{target}] escapes workspace [{ctx.workspace_root}]",
                policy_id="path-scope",
            )
        if not target and definition.name in {"write_file", "read_file"}:
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                reason="file_path is required for filesystem tools",
                policy_id="validation",
            )

    # Destructive guard without approval — yield REQUIRE_APPROVAL before engine
    if gated and definition.is_destructive and not ctx.user_approved:
        return PolicyDecision(
            effect=PolicyEffect.REQUIRE_APPROVAL,
            reason=f"destructive tool [{definition.name}] requires user approval",
            policy_id="destructive-guard",
        )

    # Delegate to platform engine (rule-based, deny-by-default)
    request = build_policy_request(definition, invocation, ctx)
    # ``engine`` is typed as object to avoid importing the protocol and to keep
    # the domain agnostic; we only require ``decide``.
    decide = getattr(engine, "decide", None)
    if decide is None or not callable(decide):
        # No engine configured — mirror HTTP layer's permissive dev fallback
        # (plan section 13).  High-risk without approval already returned
        # REQUIRE_APPROVAL above; with approval we allow-through so the
        # foundation remains E2E-testable without explicit rules.
        if definition.risk_level in HIGH_RISK_LEVELS and gated:
            if ctx.user_approved:
                return PolicyDecision(
                    effect=PolicyEffect.ALLOW,
                    reason="no engine — high-risk approved pass-through",
                    policy_id="allow-no-engine-approved",
                )
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                reason="policy engine is not configured and high-risk tool requires explicit rules",
                policy_id="policy-unconfigured",
            )
        return PolicyDecision(effect=PolicyEffect.ALLOW, reason="no engine — low-risk pass-through", policy_id="allow-no-engine")

    result = await decide(request)
    if not isinstance(result, PolicyDecision):
        raise TypeError("policy engine must return a PolicyDecision")
    return result


__all__ = ["build_policy_request", "evaluate_policy"]
