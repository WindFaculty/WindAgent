"""
WindAgent Core Domain Package (V2 Architecture).
Pure Python domain models, contracts, error hierarchy, configuration, security primitives, and event model.
"""

from windagent_core.domain.types import (
    UUIDEntityId, OpaqueId, TaskId, TaskRunId, RunId, SessionId, WorkflowId, WorkflowRunId,
    StepId, StepRunId, ToolCallId, ModelCallId, EventId, ArtifactId, PermissionRequestId,
    ProviderId, EndpointId, CanonicalModelId, ProviderModelId, RuntimeRunId, RuntimeSessionId,
    WorkerId, RouteLockId, RouteAttemptId, ExternalRequestId, classify_identifier,
    ToolInvocationId, DecisionId
)
from windagent_core.domain.lifecycle import (
    TaskState, WorkflowState, StepState, SessionState, StateTransitionResult,
    TaskLifecycle, WorkflowLifecycle, StepLifecycle, SessionLifecycle, utc_now
)
from windagent_core.domain.models import (
    Session, SessionStatus, Task, TaskRequest, TaskRun, WorkflowDefinition, WorkflowRun, WorkflowStep, WorkflowStatus, StepStatus, ModelRequest, ModelResponse, ArtifactRef, PermissionRequest, VerificationResult,
)
from windagent_core.errors.exceptions import (
    WindAgentError, DomainError, ValidationError, IdentityValidationError, ConflictError,
    InvalidStateTransitionError, TerminalStateMutationError, ConcurrentStateConflictError,
    NotFoundError, PermissionDeniedError, ApprovalRequiredError, ExecutionError, RuntimeLostError,
    ProviderError, RateLimitError, QuotaExhaustedError, AuthenticationError, TimeoutError,
    ToolError, ToolExecutionError, SerializationError, IntegrityError, ConfigurationError, RetryableError, NonRetryableError
)
from windagent_core.config.settings import (
    ApplicationConfig, DatabaseConfig, ExecutionConfig, ProviderRoutingConfig,
    SecurityConfig, ObservabilityConfig, FeatureGateConfig,
    CoreSettings, DatabaseSettings, ProviderSettings, ExecutionSettings, SecuritySettings, ObservabilitySettings
)
from windagent_core.security.types import (
    Principal, Role, Permission, ResourceScope, RiskLevel,
    ApprovalRequirement, PermissionEvaluationRequest, PermissionDecision,
    SecretRef, SecretName, SecretValue, RedactedValue, SecurityAuditContext
)
from windagent_core.contracts.providers import (
    ProviderRequest, ProviderResponse, ProviderUsage, ProviderToolCall, ProviderStreamChunk
)
from windagent_core.contracts.tools import ToolInvocation, ToolResult
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.events.registry import EventRegistry, BaseEventPayload
from windagent_core.events.processor import (
    redact_event_payload, EventDeduplicator, ReplayFilter
)

from windagent_core.contracts import (
    Clock, IdGenerator, TaskRepository, TaskRunRepository, SessionRepository,
    WorkflowRepository, WorkflowRunRepository, EventStore, OutboxWriter, EventPublisher,
    ArtifactRepository, UnitOfWork, ExecutionRuntimePort, ModelGatewayPort, SecretStore,
    PermissionEvaluator, AuditSink
)

__version__ = "0.3.0"

__all__ = [
    # Types
    "UUIDEntityId", "OpaqueId", "TaskId", "TaskRunId", "RunId", "SessionId", "WorkflowId", "WorkflowRunId",
    "StepId", "StepRunId", "ToolCallId", "ModelCallId", "EventId", "ArtifactId", "PermissionRequestId",
    "ProviderId", "EndpointId", "CanonicalModelId", "ProviderModelId", "RuntimeRunId", "RuntimeSessionId",
    "WorkerId", "RouteLockId", "RouteAttemptId", "ExternalRequestId", "classify_identifier",
    # Models
    "Session", "SessionStatus", "Task", "TaskRequest", "TaskRun",
    "WorkflowDefinition", "WorkflowRun", "WorkflowStep", "WorkflowStatus", "StepStatus",
    "ToolInvocation", "ToolResult", "ModelRequest", "ModelResponse",
    "ArtifactRef", "PermissionRequest", "VerificationResult",
    # Errors
    "WindAgentError", "DomainError", "ValidationError", "IdentityValidationError", "ConflictError",
    "NotFoundError", "PermissionDeniedError", "RetryableError", "NonRetryableError",
    "ProviderError", "ToolError", "IntegrityError",
    # Settings
    "CoreSettings", "DatabaseSettings", "ProviderSettings",
    "ExecutionSettings", "SecuritySettings", "ObservabilitySettings",
    # Security
    "Principal", "Permission", "ResourceScope", "RiskLevel",
    "ApprovalRequirement", "SecretRef", "RedactedValue",
    # Events
    "EventEnvelope", "EventCatalog",
    "redact_event_payload", "EventDeduplicator", "ReplayFilter",
    # Contracts
    "Clock", "IdGenerator", "TaskRepository", "TaskRunRepository", "SessionRepository",
    "WorkflowRepository", "WorkflowRunRepository", "EventStore", "OutboxWriter", "EventPublisher",
    "ArtifactRepository", "UnitOfWork", "ExecutionRuntimePort", "ModelGatewayPort", "SecretStore",
    "PermissionEvaluator", "AuditSink",
]
