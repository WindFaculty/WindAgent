"""
Security Primitives for WindAgent Architecture V2.
Encapsulates principals, permissions, resource scopes, risk levels, and secret protection types.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List


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
            if perm.action in (action, "*") and perm.target in (target, "*"):
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
