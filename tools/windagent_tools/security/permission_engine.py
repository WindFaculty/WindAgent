"""
Permission Policy Engine for WindAgent Tool Platform.
Evaluates security policies, principal permissions, and user approvals before executing tools.
Enforces fail-closed security.
"""

from __future__ import annotations
import logging

from windagent_core.domain.models import ToolInvocation
from windagent_core.errors.exceptions import PermissionDeniedError
from windagent_tools.base import ToolDefinition, ToolExecutionContext, ToolRiskLevel

logger = logging.getLogger("windagent.tools.permission")

HIGH_RISK_LEVELS = {
    ToolRiskLevel.EXTERNAL_NETWORK,
    ToolRiskLevel.SECRET_ACCESS,
    ToolRiskLevel.PROCESS_EXECUTION,
    ToolRiskLevel.DESTRUCTIVE,
    ToolRiskLevel.PRIVILEGED,
}


class PermissionEngine:
    def __init__(self, enforce_strict: bool = True):
        self.enforce_strict = enforce_strict

    async def evaluate_and_enforce(
        self,
        definition: ToolDefinition,
        invocation: ToolInvocation,
        ctx: ToolExecutionContext
    ) -> None:
        """Evaluates security rules and raises PermissionDeniedError if unauthorized."""
        tool_name = definition.name

        # 1. High-risk tool approval requirement
        if definition.risk_level in HIGH_RISK_LEVELS and not ctx.user_approved:
            logger.warning(f"Tool [{tool_name}] requires user approval (risk: {definition.risk_level.value})")
            raise PermissionDeniedError(
                message=f"Execution of high-risk tool [{tool_name}] requires explicit user approval.",
                code="WINDAGENT_ERR_PERMISSION_DENIED",
                details={"tool_name": tool_name, "risk_level": definition.risk_level.value},
            )

        # 2. Principal permission checks
        if ctx.principal:
            for req_perm in definition.required_permissions:
                if not ctx.principal.has_permission(req_perm, tool_name):
                    logger.warning(f"Principal [{ctx.principal.id}] lacks permission [{req_perm}] for [{tool_name}]")
                    raise PermissionDeniedError(
                        message=f"Principal [{ctx.principal.id}] lacks required permission [{req_perm}] to execute [{tool_name}].",
                        code="WINDAGENT_ERR_PERMISSION_DENIED",
                        details={"tool_name": tool_name, "required_permission": req_perm},
                    )

        logger.debug(f"Permission Engine approved tool call [{tool_name}]")
