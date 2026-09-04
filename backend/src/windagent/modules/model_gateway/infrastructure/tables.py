"""Durable tables for the model gateway (registered into the shared metadata).

Table names carry the ``model_gateway_`` prefix to keep the single Alembic
chain namespace-clean.  The route-lock table enforces one ACTIVE lock per
scope through a partial unique index — the cross-process CAS backstop
preserved from the old ``route_locks_v3``.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Table,
    Text,
)

from windagent.platform.persistence.metadata import metadata

providers_table = Table(
    "model_gateway_providers",
    metadata,
    Column("id", String(100), primary_key=True),
    Column("name", String(200), nullable=False, unique=True),
    Column("display_name", String(200), nullable=False),
    Column("vendor_type", String(50), nullable=False, default="cloud"),
    Column("base_url", Text, nullable=False),
    Column("protocol_mode", String(50), nullable=False, default="openai"),
    Column("supports_model_discovery", Boolean, nullable=False, default=True),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

endpoints_table = Table(
    "model_gateway_endpoints",
    metadata,
    Column("id", String(120), primary_key=True),
    Column("provider_id", String(100), nullable=False, index=True),
    Column("base_url", Text, nullable=False),
    Column("protocol_mode", String(50), nullable=False, default="openai"),
    Column("priority", Integer, nullable=False, default=50),
    Column("weight", Integer, nullable=False, default=100),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("test_status", String(20), nullable=False, default="untested"),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

credentials_table = Table(
    "model_gateway_credentials",
    metadata,
    # Write-only credential contract: only a SecretStore reference lives here.
    Column("id", String(100), primary_key=True),
    Column("provider_id", String(100), nullable=False, index=True),
    Column("secret_name", String(200), nullable=False, unique=True),
    Column("secret_version", Integer, nullable=False, default=1),
    Column("label", String(200), nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)

canonical_models_table = Table(
    "model_gateway_models",
    metadata,
    Column("canonical_name", String(300), primary_key=True),
    Column("vendor", String(100), nullable=False),
    Column("family", String(200), nullable=False),
    Column("revision", String(100), nullable=True),
    Column("quantization", String(50), nullable=True),
    Column("parameter_size", String(50), nullable=True),
    Column("equivalence_fingerprint", String(400), nullable=False, default=""),
    Column("context_window", Integer, nullable=True),
    Column("capabilities_json", Text, nullable=False, default="[]"),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

bindings_table = Table(
    "model_gateway_bindings",
    metadata,
    Column("id", String(120), primary_key=True),
    Column("endpoint_id", String(120), nullable=False, index=True),
    Column("canonical_model_id", String(300), nullable=False, index=True),
    Column("provider_model_id", String(300), nullable=False),
    Column("equivalence_level", String(60), nullable=False, default="exact_revision"),
    Column("equivalence_fingerprint", String(400), nullable=False, default=""),
    Column("pricing_class", String(20), nullable=False, default="UNKNOWN"),
    Column("priority", Integer, nullable=False, default=50),
    Column("availability", String(30), nullable=False, default="active"),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("last_discovered_at", DateTime(timezone=True), nullable=True),
    Index(
        "uq_model_gateway_bindings_pair",
        "endpoint_id",
        "canonical_model_id",
        unique=True,
    ),
)

routing_rules_table = Table(
    "model_gateway_rules",
    metadata,
    Column("rule_id", String(200), primary_key=True),
    Column("rule_version", Integer, nullable=False, default=1),
    Column("canonical_model_id", String(300), nullable=False),
    Column("fallback_model_id", String(300), nullable=True),
    Column("description", Text, nullable=False, default=""),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("priority", Integer, nullable=False, default=50),
    Column("task_labels_json", Text, nullable=False, default="[]"),
    Column("agent_types_json", Text, nullable=False, default="[]"),
    Column("workflow_types_json", Text, nullable=False, default="[]"),
    Column("required_capabilities_json", Text, nullable=False, default="[]"),
    Column("min_context_tokens", Integer, nullable=False, default=0),
    Column("requires_tools", Boolean, nullable=False, default=False),
    Column("requires_vision", Boolean, nullable=False, default=False),
    Column("cost_classes_json", Text, nullable=False, default="[]"),
    Column("requires_local", Boolean, nullable=False, default=False),
    Column("requires_private", Boolean, nullable=False, default=False),
    Column("user_preference_model", String(300), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

route_locks_table = Table(
    "model_gateway_route_locks",
    metadata,
    Column("lock_id", String(36), primary_key=True),
    Column("scope_type", String(30), nullable=False),
    Column("scope_id", String(200), nullable=False),
    Column("canonical_model_id", String(300), nullable=False),
    Column("rule_id", String(200), nullable=False),
    Column("rule_version", Integer, nullable=False, default=0),
    Column("snapshot_json", Text, nullable=False, default="{}"),
    Column("status", String(20), nullable=False, default="active"),
    Column("reselection_count", Integer, nullable=False, default=0),
    Column("is_fallback", Boolean, nullable=False, default=False),
    Column("source_lock_id", String(36), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("released_at", DateTime(timezone=True), nullable=True),
    # The partial unique index enforcing one ACTIVE lock per scope is the
    # cross-process CAS backstop; its authoritative DDL lives in migration
    # 0005 (dialect-specific WHERE clauses are declared there).
    Index(
        "ix_model_gateway_route_locks_scope",
        "scope_type",
        "scope_id",
    ),
)

endpoint_state_table = Table(
    "model_gateway_endpoint_state",
    metadata,
    Column("endpoint_id", String(120), primary_key=True),
    Column("consecutive_failures", Integer, nullable=False, default=0),
    Column("success_count", Integer, nullable=False, default=0),
    Column("failure_count", Integer, nullable=False, default=0),
    Column("cooldown_until", DateTime(timezone=True), nullable=True),
    Column("circuit_open_until", DateTime(timezone=True), nullable=True),
    Column("last_latency_ms", Float, nullable=False, default=0.0),
    Column("last_success_at", DateTime(timezone=True), nullable=True),
    Column("last_failure_at", DateTime(timezone=True), nullable=True),
    Column("last_error_class", String(100), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

quota_state_table = Table(
    "model_gateway_quota_state",
    metadata,
    Column("provider_name", String(200), primary_key=True),
    Column("has_quota", Boolean, nullable=False, default=True),
    Column("remaining_requests_today", Integer, nullable=True),
    Column("remaining_tokens_today", Integer, nullable=True),
    Column("reset_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

attempts_table = Table(
    "model_gateway_attempts",
    metadata,
    Column("id", String(200), primary_key=True),
    Column("route_lock_id", String(36), nullable=False, index=True),
    Column("endpoint_id", String(120), nullable=False),
    Column("binding_id", String(120), nullable=False),
    Column("attempt_index", Integer, nullable=False, default=0),
    Column("status", String(20), nullable=False),
    Column("error_class", String(100), nullable=True),
    Column("http_status", Integer, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("prompt_tokens", Integer, nullable=False, default=0),
    Column("completion_tokens", Integer, nullable=False, default=0),
    Column("latency_ms", Float, nullable=False, default=0.0),
)

secrets_table = Table(
    "model_gateway_secrets",
    metadata,
    # AES-GCM ciphertext envelopes only; the plaintext never touches storage.
    Column("secret_name", String(200), primary_key=True),
    Column("ciphertext", Text, nullable=False),
    Column("key_version", Integer, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), nullable=True),
)

receipts_table = Table(
    "model_gateway_receipts",
    metadata,
    Column("id", String(100), primary_key=True),
    Column("task_id", String(200), nullable=False),
    Column("role", String(100), nullable=True),
    Column("route_lock_id", String(36), nullable=False),
    Column("rule_id", String(200), nullable=False),
    Column("rule_version", Integer, nullable=False, default=0),
    Column("provider_id", String(100), nullable=False, default=""),
    Column("canonical_model_id", String(300), nullable=False),
    Column("provider_model_id", String(300), nullable=False, default=""),
    Column("endpoint_id", String(120), nullable=False, default=""),
    Column("fallback_used", Boolean, nullable=False, default=False),
    Column("fallback_reason", String(300), nullable=True),
    Column("status", String(20), nullable=False, default="success"),
    Column("error_code", String(100), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Index("ix_model_gateway_receipts_task", "task_id"),
)
