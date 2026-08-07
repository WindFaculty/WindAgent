"""
WindAgent Core Domain Package (V2 Architecture).
Pure Python domain models, contracts, error hierarchy, configuration, security primitives, and event model.
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_core.domain.types import (
    UUIDEntityId, OpaqueId, TaskId, TaskRunId, RunId, SessionId, WorkflowId, WorkflowRunId,
    StepId, StepRunId, ToolCallId, ModelCallId, EventId, ArtifactId, PermissionRequestId,
    ProviderId, EndpointId, CanonicalModelId, ProviderModelId, RuntimeRunId, RuntimeSessionId,
    WorkerId, RouteLockId, RouteAttemptId, ExternalRequestId, classify_identifier,
    ToolInvocationId, DecisionId, AggregateId
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
from windagent_core.contracts.health import (
    HealthStatus, HealthProfile, HealthCheckResult, ReadinessStatus,
    HealthCheckPort, DatabaseHealthPort, SchemaHealthPort, OutboxHealthPort,
    WorkerHealthPort, QueueHealthPort, RegistryHealthPort, EventHealthPort,
    FilesystemHealthPort, ConfigurationHealthPort,
)
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.events.registry import EventRegistry, BaseEventPayload
from windagent_core.events.processor import (
    redact_event_payload, EventDeduplicator, ReplayFilter
)
from windagent_core.events.video_production import (
    VideoProductionEventCatalog,
    VideoProductionEventEnvelope,
    VideoProductionEventTransitions,
    EventIdempotencyGuard,
)
from windagent_core.domain.video_production import (
    VideoProject,
    ProductionRevision,
    RevisionService,
    CreativeBrief,
    StoryConcept,
    Screenplay,
    DialogueLine,
    Scene,
    CharacterBible,
    LocationBible,
    PropBible,
    StyleBible,
    Shot,
    ShotDependency,
    ShotDependencyGraph,
    CinematicPlan,
    CameraDecision,
    RetryPolicy,
    ShotSpecification,
    ShotScheduling,
    ShotGraphIssue,
    ShotDependencyGraphValidator,
    compute_graph_hash,
    DirectorialIssue,
    SceneObjective,
    ScriptRevisionProposal,
    compute_plan_hash,
    ReferenceAsset,
    AssetAcquisitionRecord,
    FinalDeliverable,
    ContinuityState,
    ContinuityFieldState,
    ContinuityChange,
    ContinuityAssertion,
    ContinuityDiff,
    ContinuityLedgerEntry,
    ContinuityIssue,
    HumanContinuityOverride,
    ContinuityLedger,
    ContinuityLedgerValidator,
    compute_ledger_hash,
    GenerationRequest,
    GenerationCandidate,
    GenerationRecord,
    ReferenceBinding,
    ReferenceBindingIssue,
    ReferenceBindingPlan,
    ReferenceBindingValidator,
    compute_reference_binding_hash,
    PromptBlock,
    CompiledPrompt,
    PromptCompilerIssue,
    PromptSecurityFinding,
    compute_prompt_hash,
    compute_request_hash,
    ReviewResult,
    ApprovalDecision,
    ApprovalState,
    VideoProductionPackage,
    PackageProvenance,
    ValidationIssue,
    VideoProductionPackageValidator,
    VIDEO_PRODUCTION_PACKAGE_VERSION,
    CharacterVoiceProfile,
    DialogueTrack,
    WordTimestamp,
    SoundEffectCue,
    MusicCue,
    TtsAudioAsset,
    AudioMixPlan,
    compute_mix_hash,
    AudioIntentType,
    AudioCueKind,
    VoiceRightsState,
    AudioAlignmentStatus,
    AudioInvalidationScope,
)

from windagent_core.contracts import (
    Clock, IdGenerator, TaskRepository, TaskRunRepository, SessionRepository,
    WorkflowRepository, WorkflowRunRepository, EventStore, OutboxWriter, EventPublisher,
    ArtifactRepository, UnitOfWork, ExecutionRuntimePort, ModelGatewayPort, SecretStore,
    PermissionEvaluator, AuditSink, WorkRepository,
)

__version__ = PRODUCT_VERSION
__all__ = [
    # Types
    "UUIDEntityId", "OpaqueId", "TaskId", "TaskRunId", "RunId", "SessionId", "WorkflowId", "WorkflowRunId",
    "StepId", "StepRunId", "ToolCallId", "ModelCallId", "EventId", "ArtifactId", "PermissionRequestId",
    "ProviderId", "EndpointId", "CanonicalModelId", "ProviderModelId", "RuntimeRunId", "RuntimeSessionId",
    "WorkerId", "RouteLockId", "RouteAttemptId", "ExternalRequestId", "classify_identifier",
    "ToolInvocationId", "DecisionId", "AggregateId",
    "Session", "SessionStatus", "Task", "TaskRequest", "TaskRun",
    "WorkflowDefinition", "WorkflowRun", "WorkflowStep", "WorkflowStatus", "StepStatus",
    "ToolInvocation", "ToolResult", "ModelRequest", "ModelResponse",
    "ArtifactRef", "PermissionRequest", "VerificationResult",
    # Errors
    "WindAgentError", "DomainError", "ValidationError", "IdentityValidationError", "ConflictError",
    "InvalidStateTransitionError", "TerminalStateMutationError", "ConcurrentStateConflictError",
    "NotFoundError", "PermissionDeniedError", "ApprovalRequiredError", "ExecutionError", "RuntimeLostError",
    "ProviderError", "RateLimitError", "QuotaExhaustedError", "AuthenticationError", "TimeoutError",
    "ToolError", "ToolExecutionError", "SerializationError", "IntegrityError", "ConfigurationError",
    "RetryableError", "NonRetryableError",
    # Settings
    "ApplicationConfig", "DatabaseConfig", "ExecutionConfig", "ProviderRoutingConfig",
    "SecurityConfig", "ObservabilityConfig", "FeatureGateConfig",
    "CoreSettings", "DatabaseSettings", "ProviderSettings",
    "ExecutionSettings", "SecuritySettings", "ObservabilitySettings",
    # Security
    "Principal", "Role", "Permission", "ResourceScope", "RiskLevel",
    "ApprovalRequirement", "PermissionEvaluationRequest", "PermissionDecision",
    "SecretRef", "SecretName", "SecretValue", "RedactedValue", "SecurityAuditContext",
    # Events
    "EventEnvelope", "EventCatalog", "EventRegistry", "BaseEventPayload",
    "redact_event_payload", "EventDeduplicator", "ReplayFilter",
    "VideoProductionEventCatalog", "VideoProductionEventEnvelope",
    "VideoProductionEventTransitions", "EventIdempotencyGuard",
    # Video Production Domain (Phase 3)
    "VideoProject", "ProductionRevision", "RevisionService",
    "CreativeBrief", "StoryConcept", "Screenplay", "DialogueLine", "Scene",
    "CharacterBible", "LocationBible", "PropBible", "StyleBible",
    "Shot", "ShotDependency", "ShotDependencyGraph", "CinematicPlan",
    "CameraDecision", "RetryPolicy",
    "ShotSpecification", "ShotScheduling", "ShotGraphIssue",
    "ShotDependencyGraphValidator", "compute_graph_hash",
    "DirectorialIssue", "SceneObjective", "ScriptRevisionProposal", "compute_plan_hash",
    "ReferenceAsset", "AssetAcquisitionRecord", "FinalDeliverable",
    "ContinuityState", "ContinuityFieldState", "ContinuityChange",
    "ContinuityAssertion", "ContinuityDiff", "ContinuityLedgerEntry",
    "ContinuityIssue", "HumanContinuityOverride", "ContinuityLedger",
    "ContinuityLedgerValidator", "compute_ledger_hash",
    "GenerationRequest", "GenerationCandidate",
    "GenerationRecord", "ReviewResult", "ApprovalDecision", "ApprovalState",
    "ReferenceBinding", "ReferenceBindingIssue", "ReferenceBindingPlan",
    "ReferenceBindingValidator", "compute_reference_binding_hash",
    "PromptBlock", "CompiledPrompt",
    "PromptCompilerIssue", "PromptSecurityFinding",
    "compute_prompt_hash", "compute_request_hash",
    "VideoProductionPackage", "PackageProvenance", "ValidationIssue",
    "VideoProductionPackageValidator", "VIDEO_PRODUCTION_PACKAGE_VERSION",
    "CharacterVoiceProfile", "DialogueTrack", "WordTimestamp",
    "SoundEffectCue", "MusicCue", "TtsAudioAsset", "AudioMixPlan",
    "compute_mix_hash", "AudioIntentType", "AudioCueKind",
    "VoiceRightsState", "AudioAlignmentStatus", "AudioInvalidationScope",
    # Health Contracts
    "HealthStatus", "HealthProfile", "HealthCheckResult", "ReadinessStatus",
    "HealthCheckPort", "DatabaseHealthPort", "SchemaHealthPort", "OutboxHealthPort",
    "WorkerHealthPort", "QueueHealthPort", "RegistryHealthPort", "EventHealthPort",
    "FilesystemHealthPort", "ConfigurationHealthPort",
    # Other Contracts
    "Clock", "IdGenerator", "TaskRepository", "TaskRunRepository", "SessionRepository",
    "WorkflowRepository", "WorkflowRunRepository", "EventStore", "OutboxWriter", "EventPublisher",
    "ArtifactRepository", "UnitOfWork", "ExecutionRuntimePort", "ModelGatewayPort", "SecretStore",
    "PermissionEvaluator", "AuditSink",
    # Domain Models
    "WorkflowRun", "WorkflowStep", "WorkflowDefinition", "Task", "TaskRun", "Session", "ModelRequest", "ModelResponse", "ArtifactRef",
    # Lifecycle
    "TaskState", "WorkflowState", "StepState", "SessionState", "StateTransitionResult",
    "TaskLifecycle", "WorkflowLifecycle", "StepLifecycle", "SessionLifecycle", "utc_now",
    # Worker Contracts
    "WorkerHealth", "WorkerHeartbeat", "WorkerHeartbeatRepository", "WorkerStatus", "WorkerStatusQueryPort",
    "WorkSubmission", "WorkSubmissionPort", "WorkRepository",
    # Contract Types
    "ProviderRequest", "ProviderResponse", "ProviderUsage", "ProviderToolCall", "ProviderStreamChunk",
    "CacheDirective", "CachePort", "CanonicalModelRegistryPort", "ConnectionTestResult", "DiscoveredModel",
    "EndpointRegistryPort", "EndpointStatePort", "FinishReason", "ModelDescriptor", "ProtocolDetectionResult",
    "ProviderCapabilities", "ProviderHealth", "QuotaState", "QuotaStatePort", "RateLimitState", "RouteAttemptPort",
    "RouteLockPort", "UsageLedgerPort",
    "ToolDefinition", "ToolExecutionContext", "ToolExecutorPort", "ToolInvocation", "ToolRegistryPort", "ToolResult", "ToolRiskLevel",
    "FinalizeTaskExecutionRequest", "FinalizeTaskExecutionResult", "StaleResultRejectedError", "TaskFinalizationPort",
]