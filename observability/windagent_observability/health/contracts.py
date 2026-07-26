"""
Health Check Contracts for WindAgent V2 (Phase 10).
Mirror of core contracts for observability module.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, Optional
from dataclasses import dataclass, field


class HealthStatus(Enum):
    """Canonical health status values."""
    UP = "UP"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    NOT_REQUIRED = "NOT_REQUIRED"


class HealthProfile(Enum):
    """Health check profile for different environments."""
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


@dataclass
class HealthCheckResult:
    """Result of a single health check component."""
    name: str
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    required: bool = True
    latency_ms: float = 0.0
    suggested_action: Optional[str] = None


@dataclass(frozen=True)
class HealthDependencyBundle:
    """Typed bundle of runtime dependencies for HealthChecker (Phase 10)."""
    database: Optional[Any] = None
    schema: Optional[Any] = None
    outbox: Optional[Any] = None
    queue: Optional[Any] = None
    worker: Optional[Any] = None
    providers: Optional[Any] = None
    tools: Optional[Any] = None
    plugins: Optional[Any] = None
    skills: Optional[Any] = None
    workflows: Optional[Any] = None
    events: Optional[Any] = None
    configuration: Optional[Any] = None
    filesystem: Optional[Any] = None


@dataclass
class ReadinessStatus:
    """Aggregated readiness status across all components."""
    overall_status: HealthStatus
    checks: Dict[str, HealthCheckResult] = field(default_factory=dict)
    profile: HealthProfile = HealthProfile.DEVELOPMENT
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.overall_status.value,
            "profile": self.profile.value,
            "checks": {
                name: {
                    "status": check.status.value,
                    "message": check.message,
                    "details": check.details,
                    "required": check.required,
                    "latency_ms": round(check.latency_ms, 2),
                    "suggested_action": check.suggested_action,
                }
                for name, check in self.checks.items()
            }
        }
