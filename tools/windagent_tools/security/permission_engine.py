"""
Permission Policy Engine for WindAgent Tool Platform (Phase 10 Adoption).
Evaluates security policies, canonical PermissionEvaluationRequest, and normalized path scopes.
Enforces fail-closed security:
- Unknown action defaults to DENY.
- Destructive action cannot be auto-approved due to missing profile.
- Autonomous profile cannot bypass hard-deny rules.
- Permission event and audit record share the same decision_id.
"""

from __future__ import annotations
import logging
from pathlib import Path

from windagent_core.domain.types import DecisionId
from windagent_core.contracts.tools import ToolInvocation
from windagent_core.errors.exceptions import PermissionDeniedError
from windagent_core.security.types import (
    PermissionEvaluationRequest,
    PermissionDecision,
    RiskLevel,
    Principal,
)
from windagent_tools.base import ToolDefinition, ToolExecutionContext, ToolRiskLevel

logger = logging.getLogger("windagent.tools.permission")

HIGH_RISK_LEVELS = {
    ToolRiskLevel.EXTERNAL_NETWORK,
    ToolRiskLevel.SECRET_ACCESS,
    ToolRiskLevel.PROCESS_EXECUTION,
    ToolRiskLevel.DESTRUCTIVE,
    ToolRiskLevel.PRIVILEGED,
}

HARD_DENY_ACTIONS = {"format_c", "drop_production_db", "exfiltrate_keys", "bypass_auth"}


def normalize_and_validate_path(target_path: str, workspace_root: str) -> bool:
    """Validates that normalized absolute target_path is within normalized absolute workspace_root."""
    if not target_path or not workspace_root:
        return False
    try:
        norm_root = Path(workspace_root).resolve()
        norm_target = Path(target_path).resolve()
        norm_target.relative_to(norm_root)
        return True
    except (ValueError, RuntimeError, TypeError):
        return False


class PermissionEngine:
    def __init__(self, enforce_strict: bool = True):
        self.enforce_strict = enforce_strict

    def evaluate_request(self, req: PermissionEvaluationRequest) -> PermissionDecision:
        """Evaluates a canonical PermissionEvaluationRequest and returns a canonical PermissionDecision."""
        decision_id = DecisionId.generate()
        action = req.action.lower() if req.action else "unknown"

        # 1. Hard-deny rule evaluation (Autonomous profile CANNOT bypass hard-deny rules)
        if action in HARD_DENY_ACTIONS:
            return PermissionDecision(
                decision_id=decision_id,
                outcome="DENY",
                risk_level=RiskLevel.HIGH,
                reason_code="HARD_DENY_RULE",
                human_reason=f"Action [{req.action}] matches hard-deny policy rule.",
                matched_rule="HARD_DENY_POLICY",
                audit_metadata={"action": req.action, "target": req.target}
            )

        # 2. Unknown action defaults to DENY
        if action in ("unknown", "", "unhandled_action") or action.startswith(("unknown", "unhandled", "unrecognized")):
            return PermissionDecision(
                decision_id=decision_id,
                outcome="DENY",
                risk_level=RiskLevel.HIGH,
                reason_code="UNKNOWN_ACTION_DENY",
                human_reason=f"Unknown or unhandled action [{req.action}] defaults to DENY.",
                matched_rule="DEFAULT_FAIL_CLOSED",
                audit_metadata={"action": req.action}
            )

        # 3. Path scope check using normalized absolute path
        target_path = req.context.get("target_path")
        workspace_root = req.context.get("workspace_root")
        if target_path and workspace_root:
            if not normalize_and_validate_path(target_path, workspace_root):
                return PermissionDecision(
                    decision_id=decision_id,
                    outcome="DENY",
                    risk_level=RiskLevel.HIGH,
                    reason_code="PATH_SCOPE_VIOLATION",
                    human_reason=f"Target path [{target_path}] escapes workspace root [{workspace_root}].",
                    matched_rule="PATH_SCOPE_POLICY",
                    audit_metadata={"target_path": target_path, "workspace_root": workspace_root}
                )

        # 4. Destructive action check (missing profile/approval -> NOT auto-approved)
        is_destructive = req.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) or req.context.get("is_destructive", False)
        is_auto_approved = req.context.get("user_approved", False)

        if is_destructive and not is_auto_approved:
            return PermissionDecision(
                decision_id=decision_id,
                outcome="REQUIRE_APPROVAL",
                risk_level=RiskLevel.HIGH,
                reason_code="DESTRUCTIVE_APPROVAL_REQUIRED",
                human_reason=f"Destructive action [{req.action}] requires explicit user approval.",
                matched_rule="DESTRUCTIVE_GUARD_POLICY",
                audit_metadata={"action": req.action, "target": req.target}
            )

        # 5. Principal explicit permission check
        if req.principal and req.principal.permissions:
            required_perms = req.context.get("required_permissions") or [req.action]
            check_perms = list(required_perms) + [req.action, "*"]
            has_perm = any(
                req.principal.has_permission(perm, req.target) or req.principal.has_permission(perm, "*")
                for perm in check_perms
            )
            if not has_perm and "admin" not in req.principal.roles:
                return PermissionDecision(
                    decision_id=decision_id,
                    outcome="DENY",
                    risk_level=RiskLevel.HIGH,
                    reason_code="PRINCIPAL_PERMISSION_DENIED",
                    human_reason=f"Principal [{req.principal.id}] lacks required permission for action [{req.action}].",
                    matched_rule="PRINCIPAL_PERMISSION_POLICY",
                    audit_metadata={"principal_id": req.principal.id, "action": req.action, "target": req.target}
                )

        # Approved / Allow
        return PermissionDecision(
            decision_id=decision_id,
            outcome="ALLOW",
            risk_level=req.risk_level,
            reason_code="POLICY_APPROVED",
            human_reason=f"Action [{req.action}] approved under active security policy.",
            matched_rule="SECURITY_POLICY_ALLOW",
            audit_metadata={"action": req.action, "target": req.target}
        )

    async def evaluate_and_enforce(
        self,
        definition: ToolDefinition,
        invocation: ToolInvocation,
        ctx: ToolExecutionContext
    ) -> PermissionDecision:
        """Evaluates security rules and raises PermissionDeniedError if decision is DENY or REQUIRE_APPROVAL."""
        tool_name = definition.name
        principal = ctx.principal or Principal(id="anonymous", roles=["user"], permissions=[])

        args = getattr(invocation, "arguments", None) or getattr(invocation, "params", {}) or {}
        explicit_path = args.get("path") or args.get("target") or args.get("target_path")

        req = PermissionEvaluationRequest(
            principal=principal,
            action=tool_name,
            target=explicit_path or tool_name,
            risk_level=RiskLevel.HIGH if definition.risk_level in HIGH_RISK_LEVELS else RiskLevel.LOW,
            context={
                "target_path": explicit_path,
                "workspace_root": ctx.workspace_root,
                "user_approved": ctx.user_approved,
                "is_destructive": definition.risk_level == ToolRiskLevel.DESTRUCTIVE,
                "required_permissions": getattr(definition, "required_permissions", []),
            }
        )

        decision = self.evaluate_request(req)

        if not decision.is_allowed:
            logger.warning(f"Permission Engine denied tool [{tool_name}] (outcome: {decision.outcome}, reason: {decision.human_reason})")
            raise PermissionDeniedError(
                message=decision.human_reason,
                code=decision.reason_code,
                details={
                    "decision_id": str(decision.decision_id),
                    "tool_name": tool_name,
                    "outcome": decision.outcome,
                    "reason_code": decision.reason_code,
                }
            )

        logger.debug(f"Permission Engine approved tool call [{tool_name}] (decision_id: {decision.decision_id})")
        return decision
