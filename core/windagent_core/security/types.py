"""
Security Primitives for WindAgent Architecture V2.
Encapsulates principals, permissions, resource scopes, risk levels, and secret protection types.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalRequirement(str, Enum):
    AUTOMATIC = "automatic"
    USER_PROMPT = "user_prompt"
    EXPLICIT_CONFIRMATION = "explicit_confirmation"
    DENIED = "denied"


@dataclass(frozen=True)
class Permission:
    action: str
    target: str
    risk_level: RiskLevel = RiskLevel.LOW

    def __str__(self) -> str:
        return f"{self.action}:{self.target}"


@dataclass(frozen=True)
class ResourceScope:
    name: str
    path_patterns: List[str] = field(default_factory=list)
    read_only: bool = False


@dataclass
class Principal:
    id: str
    roles: List[str] = field(default_factory=list)
    permissions: List[Permission] = field(default_factory=list)

    def has_permission(self, action: str, target: str) -> bool:
        for perm in self.permissions:
            if isinstance(perm, str):
                if perm in (action, "*"):
                    return True
            elif getattr(perm, "action", None) in (action, "*") and getattr(perm, "target", None) in (target, "*"):
                return True
        return False


class RedactedValue:
    """Wrapper class that hides sensitive raw data from repr/str outputs."""
    def __init__(self, raw_value: str) -> None:
        self._raw_value = raw_value

    def get_secret_value(self) -> str:
        return self._raw_value

    def __str__(self) -> str:
        return "***REDACTED***"

    def __repr__(self) -> str:
        return "RedactedValue(***REDACTED***)"

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> Any:
        from pydantic_core import core_schema

        def validate(val: Any) -> RedactedValue:
            if isinstance(val, RedactedValue):
                return val
            if isinstance(val, str):
                return RedactedValue(val)
            raise ValueError(f"Invalid RedactedValue: {val}")

        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: str(instance)
            ),
        )

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, RedactedValue):
            return self._raw_value == other._raw_value
        if isinstance(other, str):
            return self._raw_value == other
        return False


@dataclass
class SecretRef:
    name: str
    value: RedactedValue

    @classmethod
    def create(cls, name: str, raw_secret: str) -> SecretRef:
        return cls(name=name, value=RedactedValue(raw_secret))

    def get_secret(self) -> str:
        return self.value.get_secret_value()

    def __repr__(self) -> str:
        return f"SecretRef(name={self.name!r}, value=***REDACTED***)"


# Alias types for security
Role = str
SecretName = str
SecretValue = RedactedValue


from windagent_core.domain.types import DecisionId  # noqa: E402  (kept here to avoid import-cycle at module load)


@dataclass(frozen=True)
class PermissionEvaluationRequest:
    principal: Principal
    action: str
    target: str
    risk_level: RiskLevel = RiskLevel.LOW
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PermissionDecision:
    decision_id: DecisionId = field(default_factory=DecisionId.generate)
    outcome: str = "DENY"  # ALLOW, REQUIRE_APPROVAL, DENY
    risk_level: RiskLevel = RiskLevel.LOW
    reason_code: str = "DEFAULT_DENY"
    human_reason: str = "Unknown or unhandled action defaults to DENY."
    policy_version: str = "v1"
    matched_rule: str | None = None
    audit_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        return self.outcome == "ALLOW"


@dataclass(frozen=True)
class SecurityAuditContext:
    audit_id: str
    principal_id: str
    action: str
    resource: str
    decision_outcome: str
    timestamp_utc: str
    decision_id: Optional[DecisionId] = None
    metadata: dict[str, Any] = field(default_factory=dict)


