"""Public domain surface of the Automation bounded context."""

from .definition import HIGH_RISK_LEVELS, RuntimeType, ToolDefinition, ToolRiskLevel
from .errors import (
    AutomationConflictError,
    AutomationError,
    AutomationNotFoundError,
    AutomationPolicyApprovalRequiredError,
    AutomationPolicyDeniedError,
    AutomationRuntimeError,
    AutomationStaleVersionError,
    AutomationValidationError,
)
from .invocation import ToolExecutionContext, ToolInvocation
from .policy_mapping import (
    HARD_DENY_ACTIONS,
    POLICY_GATED_CAPABILITIES,
    is_policy_gated,
    risk_to_policy_level,
)
from .result import ToolResult
from .sandbox import is_within_workspace, resolve_safe_path

__all__ = [
    "AutomationConflictError",
    "AutomationError",
    "AutomationNotFoundError",
    "AutomationPolicyApprovalRequiredError",
    "AutomationPolicyDeniedError",
    "AutomationRuntimeError",
    "AutomationStaleVersionError",
    "AutomationValidationError",
    "HARD_DENY_ACTIONS",
    "HIGH_RISK_LEVELS",
    "POLICY_GATED_CAPABILITIES",
    "RuntimeType",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolInvocation",
    "ToolResult",
    "ToolRiskLevel",
    "is_policy_gated",
    "is_within_workspace",
    "resolve_safe_path",
    "risk_to_policy_level",
]
