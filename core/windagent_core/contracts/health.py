"""
Health Check Contracts for WindAgent V2 (Phase 10).
Defines ports and models for real readiness, liveness, and diagnostics.
"""

from __future__ import annotations
from enum import Enum
from typing import Protocol, runtime_checkable, Any, Dict, Optional
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
                }
                for name, check in self.checks.items()
            }
        }


@runtime_checkable
class HealthCheckPort(Protocol):
    """Port for performing health checks."""
    
    async def check_liveness(self) -> bool:
        """Check if the process is alive (event loop running)."""
        ...
    
    async def check_readiness(self, profile: HealthProfile = HealthProfile.DEVELOPMENT) -> ReadinessStatus:
        """Check if all required components are ready."""
        ...


@runtime_checkable
class DatabaseHealthPort(Protocol):
    """Port for checking database health."""
    
    async def check_connection(self) -> HealthCheckResult:
        """Check database connection."""
        ...


@runtime_checkable
class SchemaHealthPort(Protocol):
    """Port for checking schema migration version."""
    
    async def check_current_revision(self) -> HealthCheckResult:
        """Check current schema revision matches expected."""
        ...


@runtime_checkable
class OutboxHealthPort(Protocol):
    """Port for checking outbox publisher health."""
    
    async def check_publisher_heartbeat(self) -> HealthCheckResult:
        """Check outbox publisher heartbeat."""
        ...


@runtime_checkable
class WorkerHealthPort(Protocol):
    """Port for checking worker process health."""
    
    async def check_worker_heartbeat(self) -> HealthCheckResult:
        """Check worker process heartbeat."""
        ...


@runtime_checkable
class QueueHealthPort(Protocol):
    """Port for checking queue access."""
    
    async def check_queue_access(self) -> HealthCheckResult:
        """Check queue access."""
        ...


@runtime_checkable
class RegistryHealthPort(Protocol):
    """Port for checking registry health."""
    
    async def check_provider_registry(self) -> HealthCheckResult:
        """Check provider registry is loaded."""
        ...
    
    async def check_tool_registry(self) -> HealthCheckResult:
        """Check tool registry is loaded."""
        ...
    
    async def check_plugin_registry(self) -> HealthCheckResult:
        """Check plugin registry is loaded."""
        ...
    
    async def check_skill_registry(self) -> HealthCheckResult:
        """Check skill registry is loaded."""
        ...
    
    async def check_workflow_registry(self) -> HealthCheckResult:
        """Check workflow registry is loaded."""
        ...


@runtime_checkable
class EventHealthPort(Protocol):
    """Port for checking event system health."""
    
    async def check_event_dispatcher(self) -> HealthCheckResult:
        """Check event dispatcher is active."""
        ...


@runtime_checkable
class FilesystemHealthPort(Protocol):
    """Port for checking required filesystem paths."""
    
    async def check_required_paths(self) -> HealthCheckResult:
        """Check all required filesystem paths exist."""
        ...


@runtime_checkable
class ConfigurationHealthPort(Protocol):
    """Port for checking configuration validity."""
    
    async def check_configuration(self) -> HealthCheckResult:
        """Check configuration is valid."""
        ...
