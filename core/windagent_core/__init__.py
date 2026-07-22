"""
WindAgent Core Domain Package (V2 Architecture).
Pure Python domain models, contracts, error hierarchy, configuration, and security primitives.
"""

from windagent_core.domain.types import (
    BaseEntityId, TaskId, RunId, SessionId, WorkflowId, StepId,
    ToolCallId, ModelCallId, EventId, ArtifactId
)
from windagent_core.domain.models import (
    Session, SessionStatus, Task, TaskRequest, TaskRun,
    WorkflowDefinition, WorkflowRun, WorkflowStep, WorkflowStatus, StepStatus,
    ToolInvocation, ToolResult, ModelRequest, ModelResponse,
    ArtifactRef, PermissionRequest, VerificationResult
)
from windagent_core.errors.exceptions import (
    WindAgentError, DomainError, ValidationError, ConflictError,
    NotFoundError, PermissionDeniedError, RetryableError, NonRetryableError,
    ProviderError, ToolError, IntegrityError
)
from windagent_core.config.settings import (
    CoreSettings, DatabaseSettings, ProviderSettings,
    ExecutionSettings, SecuritySettings, ObservabilitySettings
)
from windagent_core.security.types import (
    Principal, Permission, ResourceScope, RiskLevel,
    ApprovalRequirement, SecretRef, RedactedValue
)

__version__ = "0.3.0"

__all__ = [
    # Types
    "BaseEntityId", "TaskId", "RunId", "SessionId", "WorkflowId", "StepId",
    "ToolCallId", "ModelCallId", "EventId", "ArtifactId",
    # Models
    "Session", "SessionStatus", "Task", "TaskRequest", "TaskRun",
    "WorkflowDefinition", "WorkflowRun", "WorkflowStep", "WorkflowStatus", "StepStatus",
    "ToolInvocation", "ToolResult", "ModelRequest", "ModelResponse",
    "ArtifactRef", "PermissionRequest", "VerificationResult",
    # Errors
    "WindAgentError", "DomainError", "ValidationError", "ConflictError",
    "NotFoundError", "PermissionDeniedError", "RetryableError", "NonRetryableError",
    "ProviderError", "ToolError", "IntegrityError",
    # Settings
    "CoreSettings", "DatabaseSettings", "ProviderSettings",
    "ExecutionSettings", "SecuritySettings", "ObservabilitySettings",
    # Security
    "Principal", "Permission", "ResourceScope", "RiskLevel",
    "ApprovalRequirement", "SecretRef", "RedactedValue",
]
