"""SQLAlchemy ORM models for the WindAgent backend.

Six tables per ban_ke_hoach.md §2.2:

  chat_sessions   - one row per chat session
  messages        - user/assistant/system messages per session
  workflows       - workflow owned by a session (1:1 in MVP)
  workflow_steps  - ordered steps inside a workflow
  tool_calls      - audit trail of every tool invocation (Phase 3 fills this)
  execution_events- every event envelope ever published (for replay + audit)

UUIDs are stored as String(36) since SQLite has no native UUID type.
JSON payloads are stored as TEXT (SQLite has a JSON affinity but we
keep it as text for simplicity).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- chat_sessions ----------

class ChatSessionORM(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")

    messages: Mapped[list["MessageORM"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    workflows: Mapped[list["WorkflowORM"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


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
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    session: Mapped[ChatSessionORM] = relationship(back_populates="workflows")
    steps: Mapped[list["WorkflowStepORM"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStepORM.order_index",
    )


# ---------- workflow_steps ----------

class WorkflowStepORM(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    workflow: Mapped[WorkflowORM] = relationship(back_populates="steps")


Index("ix_workflow_steps_workflow_id_order", WorkflowStepORM.workflow_id, WorkflowStepORM.order_index)


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
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


Index("ix_tool_calls_session_id_created_at", ToolCallORM.session_id, ToolCallORM.created_at)


# ---------- execution_events ----------

class ExecutionEventORM(Base):
    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


Index("ix_execution_events_session_id_created_at", ExecutionEventORM.session_id, ExecutionEventORM.created_at)


# ---------- Model Registry & Management ----------

class ModelProviderORM(Base):
    __tablename__ = "model_providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_name: Mapped[str] = mapped_column(String(128), nullable=False)
    api_source: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    management_base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    api_key_env: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    management_api_key_env: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_type: Mapped[str] = mapped_column(String(32), default="cloud") # "cloud" | "local"
    quota_mode: Mapped[str] = mapped_column(String(32), default="RPM_RPD") # "ONE_TIME_CREDIT" | "TOKEN_BUDGET" | "RPM_RPD" | "LOCAL_RESOURCE"
    supports_openai_compatible: Mapped[bool] = mapped_column(default=True)
    supports_model_discovery: Mapped[bool] = mapped_column(default=True)
    models_endpoint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    chat_endpoint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    priority: Mapped[int] = mapped_column(default=50)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow, nullable=False)


class ModelCatalogORM(Base):
    __tablename__ = "model_catalog"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False) # "API" | "Local"
    billing_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    context_window: Mapped[Optional[int]] = mapped_column(nullable=True)
    max_output_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]") # List of capabilities
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    default_roles_json: Mapped[str] = mapped_column(Text, default="[]")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deployment: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    quantization: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    discovered: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String(32), default="seed") # "seed" | "discovered"
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow, nullable=False)


class ModelRuntimeStatusORM(Base):
    __tablename__ = "model_runtime_status"

    model_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="Offline") # "Running" | "Ready" | "Loading" | "Idle" | "Offline"
    health: Mapped[str] = mapped_column(String(32), default="Unknown") # "Healthy" | "Unhealthy" | "Unknown"
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

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    latency_p50_ms: Mapped[float] = mapped_column(nullable=False)
    latency_p90_ms: Mapped[float] = mapped_column(nullable=False)
    tokens_per_sec: Mapped[float] = mapped_column(nullable=False)
    success_rate: Mapped[float] = mapped_column(nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    test_name: Mapped[str] = mapped_column(String(128), default="smoke")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)


__all__ = [
    "Base",
    "ChatSessionORM",
    "MessageORM",
    "WorkflowORM",
    "WorkflowStepORM",
    "ToolCallORM",
    "ExecutionEventORM",
    "ModelProviderORM",
    "ModelCatalogORM",
    "ModelRuntimeStatusORM",
    "ProviderQuotaSnapshotORM",
    "ModelRoutingRuleORM",
    "RouterExecutionLogORM",
    "ModelActivityORM",
    "ModelBenchmarkRunORM",
]


