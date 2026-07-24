"""
WindAgent Core Security Package.
Exports principal, role, permission, decision, and secret reference types.
"""

from windagent_core.security.types import (
    Principal,
    Role,
    Permission,
    ResourceScope,
    RiskLevel,
    ApprovalRequirement,
    PermissionEvaluationRequest,
    PermissionDecision,
    SecretRef,
    SecretName,
    SecretValue,
    RedactedValue,
    SecurityAuditContext,
)

__all__ = [
    "Principal",
    "Role",
    "Permission",
    "ResourceScope",
    "RiskLevel",
    "ApprovalRequirement",
    "PermissionEvaluationRequest",
    "PermissionDecision",
    "SecretRef",
    "SecretName",
    "SecretValue",
    "RedactedValue",
    "SecurityAuditContext",
]
