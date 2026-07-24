"""Phase 2 — Agent Workspace schema.

Six tables per ban_ke_hoach.md §2.2:
  - canonical_models        — unique logical model identity
  - provider_model_bindings — one canonical model → many provider bindings
  - route_locks             — per-scope immutable route decision
  - route_attempts          — individual provider call records
  - parent_tasks            — top-level conversation orchestration task
  - task_plans              — versioned plans
  - task_nodes              — plan node
  - task_edges              — plan edge
  - task_artifacts          — node output/artifact references

Plus legacy tables (AgentORM, AgentSessionORM, PermissionRequestORM)
and orchestration runtime tables (AgentInstanceORM, AgentRunORM,
WorktreeORM, PartialArtifactORM).

UUIDs are stored as String(36) since SQLite has no native UUID type.
JSON payloads are stored as TEXT (SQLite has a JSON affinity but we
keep it as text for simplicity).

"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates

from utils.encryption import encrypt


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- chat_sessions ----------


class ChatSessionORM(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default="New Session")
    status: Mapped[str] = mapped_column(String(32), default="idle")
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Phase recovery columns
    agent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    last_event_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow, nullable=False)

    messages: Mapped[list["MessageORM"]] = relationship(back_populates="session")


# ---------- messages ----------


class MessageORM(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id"), nullable=False
    )
    sender: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    session: Mapped[ChatSessionORM] = relationship(back_populates="messages")


Index("ix_messages_session_id_created_at", MessageORM.session_id, MessageORM.created_at)


# ---------- workflows ----------


class WorkflowORM(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    steps: Mapped[list["WorkflowStepORM"]] = relationship(back_populates="workflow")


# ---------- workflow_steps ----------


class WorkflowStepORM(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflows.id"), nullable=False)
    step_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    params_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    workflow: Mapped[WorkflowORM] = relationship(back_populates="steps")

    __table_args__ = (
        Index("ix_workflow_steps_workflow_id_order", "workflow_id", "order_index"),
    )


# ---------- tool_calls ----------


class ToolCallORM(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


Index("ix_tool_calls_session_id_created_at", ToolCallORM.session_id, ToolCallORM.created_at)


# ---------- execution_events ----------


class ExecutionEventORM(Base):
    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    event_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


Index("ix_execution_events_session_id_created_at", ExecutionEventORM.session_id, ExecutionEventORM.event_seq)


# ---------- model_providers ----------


class ModelProviderORM(Base):
    __tablename__ = "model_providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_name: Mapped[str] = mapped_column(String(128), nullable=False)
    api_source: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    management_base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    api_key_env: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    api_key: Mapped[Optional[Text]] = mapped_column(Text, nullable=True)
    management_api_key_env: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_type: Mapped[str] = mapped_column(String(32), default="cloud")  # "cloud" | "local"
    quota_mode: Mapped[str] = mapped_column(String(32), default="RPM_RPD")  # "ONE_TIME_CREDIT" | "TOKEN_BUDGET" | "RPM_RPD" | "LOCAL_RESOURCE"
    supports_openai_compatible: Mapped[bool] = mapped_column(default=True)
    supports_model_discovery: Mapped[bool] = mapped_column(default=True)
    models_endpoint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    chat_endpoint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    priority: Mapped[int] = mapped_column(default=50)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow, nullable=False)

    @validates("api_key")
    def _encrypt_api_key(self, key: str, value: Optional[str]) -> Optional[str]:
        """Encrypt API key before storing."""
        if value is None:
            return None
        if isinstance(value, str) and value.startswith("enc:v1:"):
            return value
        return encrypt(value)


# ---------- model_catalog ----------


class ModelCatalogORM(Base):
    __tablename__ = "model_catalog"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # "API" | "Local"
    billing_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    context_window: Mapped[Optional[int]] = mapped_column(nullable=True)
    max_output_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    default_roles_json: Mapped[str] = mapped_column(Text, default="[]")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deployment: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    quantization: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    discovered: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String(32), default="seed")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow, nullable=False)


class ModelRuntimeStatusORM(Base):
    __tablename__ = "model_runtime_status"

    model_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="Offline")
    health: Mapped[str] = mapped_column(String(32), default="Unknown")
    latency_p50_ms: Mapped[Optional[float]] = mapped_column(nullable=True)
    latency_p90_ms: Mapped[Optional[float]] = mapped_column(nullable=True)
    tokens_per_sec: Mapped[Optional[float]] = mapped_column(nullable=True)
    success_rate: Mapped[Optional[float]] = mapped_column(nullable=True)
    uptime_seconds: Mapped[int] = mapped_column(default=0)
    last_probe_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ProviderQuotaSnapshotORM(Base):
    __tablename__ = "provider_quota_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quota_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    rpm_limit: Mapped[Optional[int]] = mapped_column(nullable=True)
    rpd_limit: Mapped[Optional[int]] = mapped_column(nullable=True)
    tpm_limit: Mapped[Optional[int]] = mapped_column(nullable=True)
    daily_token_limit: Mapped[Optional[int]] = mapped_column(nullable=True)
    monthly_token_limit: Mapped[Optional[int]] = mapped_column(nullable=True)
    remaining_requests_today: Mapped[Optional[int]] = mapped_column(nullable=True)
    remaining_tokens_today: Mapped[Optional[int]] = mapped_column(nullable=True)
    remaining_tokens_month: Mapped[Optional[int]] = mapped_column(nullable=True)
    remaining_credit: Mapped[Optional[float]] = mapped_column(nullable=True)
    credit_currency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reset_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    source: Mapped[str] = mapped_column(String(64), default="manual")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


class ModelRoutingRuleORM(Base):
    __tablename__ = "model_routing_rules"

    role: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_model_id: Mapped[Optional[str]] = mapped_column(String(128), ForeignKey("model_catalog.id"), nullable=True)
    fallback_model_id: Mapped[Optional[str]] = mapped_column(String(128), ForeignKey("model_catalog.id"), nullable=True)
    final_fallback_model_id: Mapped[Optional[str]] = mapped_column(String(128), ForeignKey("model_catalog.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="Active", nullable=False)
    priority: Mapped[int] = mapped_column(default=1, nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    policy_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow, nullable=False)


class RouterExecutionLogORM(Base):
    __tablename__ = "router_execution_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(64), ForeignKey("model_routing_rules.role"), nullable=False)
    selected_model_id: Mapped[str] = mapped_column(String(128), ForeignKey("model_catalog.id"), nullable=False)
    selection_tier: Mapped[str] = mapped_column(String(32), nullable=False)  # primary, fallback, final_fallback, auto, emergency
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # success, failed
    latency_ms: Mapped[int] = mapped_column(nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


Index("ix_router_logs_role_created", RouterExecutionLogORM.role, RouterExecutionLogORM.created_at)
Index("ix_router_logs_model_created", RouterExecutionLogORM.selected_model_id, RouterExecutionLogORM.created_at)


class ModelActivityORM(Base):
    __tablename__ = "model_activity"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    level: Mapped[str] = mapped_column(String(16), default="info")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


class ModelBenchmarkRunORM(Base):
    __tablename__ = "model_benchmark_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    benchmark: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    run_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


# ---------- Phase 2: Canonical Model Registry (ban_ke_hoach §5.1) ----------


class CanonicalModelORM(Base):
    __tablename__ = "canonical_models"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False)
    family: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    context_window: Mapped[Optional[int]] = mapped_column(nullable=True)
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    tool_call_protocol: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    bindings: Mapped[list["ProviderModelBindingORM"]] = relationship(
        back_populates="canonical_model", cascade="all, delete-orphan"
    )


class ProviderModelBindingORM(Base):
    __tablename__ = "provider_model_bindings"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    canonical_model_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("canonical_models.id"), nullable=False
    )
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    equivalence_level: Mapped[str] = mapped_column(
        String(32), default="exact_revision", nullable=False
    )
    health: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_429_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    canonical_model: Mapped[CanonicalModelORM] = relationship(
        back_populates="bindings"
    )


# ---------- Route Locks & Attempts (ban_ke_hoach §5.2) ----------


class RouteLockORM(Base):
    __tablename__ = "route_locks"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_model_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("canonical_models.id"), nullable=False
    )
    policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    routing_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    released_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    attempts: Mapped[list["RouteAttemptORM"]] = relationship(
        back_populates="route_lock", cascade="all, delete-orphan"
    )


class RouteAttemptORM(Base):
    __tablename__ = "route_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_lock_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("route_locks.id"), nullable=False
    )
    agent_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    turn_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    attempt_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_binding_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_class: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    first_token_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_artifact_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    route_lock: Mapped[RouteLockORM] = relationship(back_populates="attempts")


# ---------- Parent Tasks & Task Plans (ban_ke_hoach §4.1) ----------


class ParentTaskORM(Base):
    __tablename__ = "parent_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    progress: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    plans: Mapped[list["TaskPlanORM"]] = relationship(
        back_populates="parent_task", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs: Any) -> None:
        if "prompt" in kwargs and "title" not in kwargs:
            kwargs["title"] = kwargs.pop("prompt")
        elif "prompt" in kwargs:
            kwargs.pop("prompt")
        if "session_id" in kwargs and "conversation_id" not in kwargs:
            kwargs["conversation_id"] = kwargs.pop("session_id")
        elif "session_id" in kwargs:
            kwargs.pop("session_id")
        super().__init__(**kwargs)


class TaskPlanORM(Base):
    __tablename__ = "task_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parent_tasks.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    parent_task: Mapped[ParentTaskORM] = relationship(back_populates="plans")
    nodes: Mapped[list["TaskNodeORM"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    edges: Mapped[list["TaskEdgeORM"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class TaskNodeORM(Base):
    __tablename__ = "task_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_plans.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="blocked", nullable=False)
    agent_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    concurrency_group: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_contract_json: Mapped[str] = mapped_column(Text, default="{}")
    output_contract_json: Mapped[str] = mapped_column(Text, default="{}")
    assigned_agent_instance_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timeout_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    plan: Mapped[TaskPlanORM] = relationship(back_populates="nodes")


class TaskEdgeORM(Base):
    __tablename__ = "task_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_plans.id"), nullable=False
    )
    from_task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_nodes.id"), nullable=False
    )
    to_task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_nodes.id"), nullable=False
    )
    edge_type: Mapped[str] = mapped_column(String(32), default="requires", nullable=False)

    plan: Mapped[TaskPlanORM] = relationship(back_populates="edges")


class TaskArtifactORM(Base):
    __tablename__ = "task_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_nodes.id"), nullable=False
    )
    agent_instance_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    path_or_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


# ---------- Legacy Agent Registry (from Phase 1) ----------


class AgentORM(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    runtime_type: Mapped[str] = mapped_column(String(32), default="hermes", nullable=False)
    hermes_profile: Mapped[Optional[str]] = mapped_column(String(128), default="default", nullable=True)
    router_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="offline", nullable=False)
    workspace_root: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    toolsets_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    skills_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    memory_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    max_concurrent_sessions: Mapped[int] = mapped_column(default=5, nullable=False)
    auto_start: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow, nullable=False)


class AgentSessionORM(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    windagent_session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.id"), nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hermes_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hermes_run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
    workspace_root: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    router_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_event_sequence: Mapped[int] = mapped_column(default=0, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PermissionRequestORM(Base):
    __tablename__ = "permission_requests"

    windagent_request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hermes_approval_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments_redacted: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


# ---------- Orchestration Runtime Tables ----------


class AgentRunORM(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_instance_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agent_instances.id"), nullable=False
    )
    hermes_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hermes_run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PartialArtifactORM(Base):
    __tablename__ = "partial_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    agent_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    turn_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_binding_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_class: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), default="audit_only", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


class WorktreeORM(Base):
    __tablename__ = "worktrees"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    repo_root: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    quarantined_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


# ---------- Multi-session Agent Instances (ban_ke_hoach §7.2) ----------


class AgentInstanceORM(Base):
    __tablename__ = "agent_instances"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
    permission_profile: Mapped[str] = mapped_column(String(32), default="Standard", nullable=False)
    workspace_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    route_lock_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    selected_provider_binding_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


async def seed_canonical_models(db: "Database") -> int:
    """Backfill canonical_models + bindings from existing model_catalog rows.

    Idempotent: skip canonical models that already exist.
    Returns count of new canonical models created.
    """
    from sqlalchemy import select, func

    async with db.session() as session:
        existing = await session.execute(select(func.count(CanonicalModelORM.id)))
        if existing.scalar() > 0:
            return 0  # already seeded, skip

        result = await session.execute(
            select(ModelCatalogORM).where(ModelCatalogORM.enabled.is_(True))
        )
        catalog_rows = result.scalars().all()

        created = 0
        seen_names: set[str] = set()
        for row in catalog_rows:
            fam = row.model_id.split("-")[0] if "-" in row.model_id else row.model_id
            if row.model_id in seen_names:
                continue
            seen_names.add(row.model_id)

            canonical = CanonicalModelORM(
                id=row.model_id,
                vendor=row.provider_id,
                family=fam,
                canonical_name=row.model_id,
                context_window=row.context_window,
                enabled=True,
            )
            session.add(canonical)

            binding = ProviderModelBindingORM(
                id=row.id,
                canonical_model_id=row.model_id,
                provider_id=row.provider_id,
                provider_model_id=row.model_id,
                priority=int(row.id.count(":")),
                enabled=True,
                equivalence_level="exact_revision",
            )
            session.add(binding)
            created += 1

        await session.commit()
        return created
