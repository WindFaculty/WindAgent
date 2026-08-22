"""
SQLAlchemy ORM Models for Provider Routing Subsystem V3.
Decoupled domain storage tables adhering to ban_ke_hoach.md §PHASE 2.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
)

from windagent_storage.orm.models import BaseORM, default_utc_now


class V3ResourceORM(BaseORM):
    """Namespaced durable V3 resource authority (Phase 4).

    Backs every canonical mutable V3 router aggregate that has no dedicated
    domain table. Each router uses a distinct ``namespace``; ``resource_id``
    is the aggregate's canonical ID; ``data_json`` holds the full resource
    payload; ``version`` provides optimistic concurrency; ``idempotency_key``
    provides durable idempotency for create operations.
    """

    __tablename__ = "v3_resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    namespace = Column(String(64), nullable=False, index=True)
    resource_id = Column(String(128), nullable=False)
    data_json = Column(Text, nullable=False, default="{}")
    version = Column(Integer, nullable=False, default=1)
    idempotency_key = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_v3_resources_namespace_id", "namespace", "resource_id", unique=True),
        Index(
            "ix_v3_resources_namespace_idem",
            "namespace",
            "idempotency_key",
            unique=True,
        ),
    )


class ProviderVendorORM(BaseORM):
    __tablename__ = "provider_vendors"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    vendor_type = Column(String(32), nullable=False, default="cloud")  # cloud | local | custom
    supports_model_discovery = Column(Boolean, nullable=False, default=True)
    supports_openai_compatible = Column(Boolean, nullable=False, default=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)


class ProviderCredentialORM(BaseORM):
    __tablename__ = "provider_credentials"

    id = Column(String(64), primary_key=True)
    vendor_id = Column(String(64), ForeignKey("provider_vendors.id"), nullable=False)
    label = Column(String(128), nullable=False)
    secret_ciphertext = Column(Text, nullable=True)  # Encrypted at rest (enc:v1:...)
    secret_version = Column(Integer, nullable=False, default=1)
    is_env_ref = Column(Boolean, nullable=False, default=False)
    env_var_name = Column(String(128), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)


class ProviderEndpointORM(BaseORM):
    __tablename__ = "provider_endpoints"

    id = Column(String(64), primary_key=True)
    vendor_id = Column(String(64), ForeignKey("provider_vendors.id"), nullable=False)
    credential_id = Column(String(64), ForeignKey("provider_credentials.id"), nullable=True)
    base_url = Column(String(255), nullable=False)
    protocol_mode = Column(String(32), nullable=False, default="openai")  # openai | anthropic | gemini | ollama
    configured_protocol = Column(String(64), nullable=True)
    detected_protocol = Column(String(64), nullable=True)
    protocol_confidence = Column(Float, nullable=False, default=1.0)
    region = Column(String(64), nullable=True, default="global")
    priority = Column(Integer, nullable=False, default=50)
    weight = Column(Integer, nullable=False, default=100)
    enabled = Column(Boolean, nullable=False, default=True)
    test_status = Column(String(32), nullable=False, default="untested")  # untested | pass | fail
    last_tested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)


class CanonicalModelV3ORM(BaseORM):
    __tablename__ = "canonical_models_v3"

    id = Column(String(128), primary_key=True)
    vendor = Column(String(64), nullable=False)
    family = Column(String(64), nullable=False)
    canonical_name = Column(String(128), nullable=False)
    revision = Column(String(64), nullable=True, default="latest")
    context_window = Column(Integer, nullable=True, default=128000)
    capabilities_json = Column(Text, nullable=False, default="[]")
    tool_call_protocol = Column(String(64), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)


class EndpointModelBindingORM(BaseORM):
    __tablename__ = "endpoint_model_bindings"

    id = Column(String(128), primary_key=True)
    endpoint_id = Column(String(64), ForeignKey("provider_endpoints.id"), nullable=False)
    canonical_model_id = Column(String(128), ForeignKey("canonical_models_v3.id"), nullable=False)
    provider_model_id = Column(String(128), nullable=False)
    model_revision = Column(String(64), nullable=True, default="latest")
    equivalence_level = Column(String(32), nullable=False, default="exact_revision")  # exact_revision | functional
    equivalence_fingerprint = Column(String(128), nullable=True)
    capabilities_json = Column(Text, nullable=False, default="[]")
    pricing_overrides_json = Column(Text, nullable=False, default="{}")
    enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=50)
    # P0.2 — discovery reconciliation + truthful pricing metadata
    availability = Column(String(16), nullable=False, default="active")  # active | unavailable | deprecated
    pricing_class = Column(String(16), nullable=False, default="UNKNOWN")  # FREE | PAID | UNKNOWN
    input_price = Column(Float, nullable=True)   # provider-advertised USD/token; NULL = not advertised
    output_price = Column(Float, nullable=True)  # provider-advertised USD/token; NULL = not advertised
    currency = Column(String(8), nullable=True)
    last_discovered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_endpoint_model_bindings_canonical", "canonical_model_id", "enabled"),
    )


class ModelRoutingRuleV3ORM(BaseORM):
    __tablename__ = "model_routing_rules_v3"

    role = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    primary_canonical_model_id = Column(String(128), ForeignKey("canonical_models_v3.id"), nullable=False)
    fallback_canonical_model_id = Column(String(128), ForeignKey("canonical_models_v3.id"), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=1)
    policy_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)


class RouteLockV3ORM(BaseORM):
    __tablename__ = "route_locks_v3"

    id = Column(String(128), primary_key=True)
    scope_type = Column(String(32), nullable=False)  # session | task | workflow
    scope_id = Column(String(128), nullable=False)
    canonical_model_id = Column(String(128), ForeignKey("canonical_models_v3.id"), nullable=False)
    policy_version = Column(Integer, nullable=True, default=1)
    version = Column(Integer, nullable=False, default=1)  # optimistic concurrency
    routing_snapshot_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="active")  # active | released
    reselection_reason = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)
    released_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_route_locks_v3_scope", "scope_type", "scope_id", "status"),
        Index(
            "uq_route_locks_v3_active_scope",
            "scope_type",
            "scope_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )


class ProviderRoutingAuditV3ORM(BaseORM):
    """Durable audit trail for provider routing decisions (merge/split/reselect/failover)."""

    __tablename__ = "provider_routing_audit_v3"

    id = Column(String(128), primary_key=True)
    action = Column(String(32), nullable=False)  # merge | split | reselect | failover
    scope_type = Column(String(32), nullable=True)
    scope_id = Column(String(128), nullable=True)
    lock_id = Column(String(128), ForeignKey("route_locks_v3.id"), nullable=True)
    canonical_model_id = Column(String(128), nullable=True)
    previous_canonical_model_id = Column(String(128), nullable=True)
    new_canonical_model_id = Column(String(128), nullable=True)
    endpoint_id = Column(String(64), nullable=True)
    reason = Column(String(255), nullable=True)
    actor = Column(String(128), nullable=False, default="system")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_provider_routing_audit_scope", "scope_type", "scope_id"),
        Index("ix_provider_routing_audit_lock", "lock_id"),
    )


class RouteAttemptV3ORM(BaseORM):
    __tablename__ = "route_attempts_v3"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_lock_id = Column(String(128), ForeignKey("route_locks_v3.id"), nullable=False)
    agent_session_id = Column(String(64), nullable=True)
    turn_id = Column(String(128), nullable=True)
    attempt_index = Column(Integer, nullable=False, default=0)
    provider_binding_id = Column(String(128), ForeignKey("endpoint_model_bindings.id"), nullable=True)
    status = Column(String(32), nullable=False, default="pending")  # pending | success | failed
    http_status = Column(Integer, nullable=True)
    error_class = Column(String(64), nullable=True)
    started_at = Column(DateTime, nullable=False, default=default_utc_now)
    first_token_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    partial_artifact_id = Column(String(128), nullable=True)


class EndpointRuntimeStateORM(BaseORM):
    __tablename__ = "endpoint_runtime_state"

    endpoint_id = Column(String(64), ForeignKey("provider_endpoints.id"), primary_key=True)
    circuit_state = Column(String(32), nullable=False, default="closed")  # closed | open | half_open
    consecutive_failures = Column(Integer, nullable=False, default=0)
    consecutive_successes = Column(Integer, nullable=False, default=0)
    cooldown_until = Column(DateTime, nullable=True)
    last_429_at = Column(DateTime, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)
    last_error_class = Column(String(64), nullable=True)
    latency_p50_ms = Column(Float, nullable=True, default=0.0)
    latency_p90_ms = Column(Float, nullable=True, default=0.0)
    success_rate = Column(Float, nullable=True, default=1.0)
    updated_at = Column(DateTime, nullable=False, default=default_utc_now)


class EndpointHealthSampleORM(BaseORM):
    __tablename__ = "endpoint_health_samples"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint_id = Column(String(64), ForeignKey("provider_endpoints.id"), nullable=False)
    healthy = Column(Boolean, nullable=False, default=True)
    latency_ms = Column(Float, nullable=False, default=0.0)
    status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    sampled_at = Column(DateTime, nullable=False, default=default_utc_now)


class EndpointRateLimitWindowORM(BaseORM):
    __tablename__ = "endpoint_rate_limit_windows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint_id = Column(String(64), ForeignKey("provider_endpoints.id"), nullable=False)
    window_type = Column(String(32), nullable=False)  # minute | day
    requests_count = Column(Integer, nullable=False, default=0)
    tokens_count = Column(Integer, nullable=False, default=0)
    window_start_at = Column(DateTime, nullable=False, default=default_utc_now)


class ProviderQuotaSnapshotV3ORM(BaseORM):
    __tablename__ = "provider_quota_snapshots_v3"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(String(64), ForeignKey("provider_vendors.id"), nullable=False)
    quota_mode = Column(String(32), nullable=False, default="RPM_RPD")
    remaining_requests_today = Column(Integer, nullable=True)
    remaining_tokens_today = Column(Integer, nullable=True)
    remaining_credit = Column(Float, nullable=True)
    credit_currency = Column(String(16), nullable=True)
    reset_at = Column(DateTime, nullable=True)
    raw_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=default_utc_now)


class ProviderUsageLedgerORM(BaseORM):
    __tablename__ = "provider_usage_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_model_id = Column(String(128), nullable=False)
    provider_model_id = Column(String(128), nullable=False)
    endpoint_id = Column(String(64), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Float, nullable=False, default=0.0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)


class ModelDiscoverySnapshotORM(BaseORM):
    __tablename__ = "model_discovery_snapshots"

    id = Column(String(64), primary_key=True)
    endpoint_id = Column(String(64), ForeignKey("provider_endpoints.id"), nullable=False)
    raw_response_json = Column(Text, nullable=False)
    discovered_models_json = Column(Text, nullable=False, default="[]")
    discovered_at = Column(DateTime, nullable=False, default=default_utc_now)


class ResponseCacheEntryORM(BaseORM):
    __tablename__ = "response_cache_entries"

    cache_key = Column(String(128), primary_key=True)
    canonical_model_id = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    response_json = Column(Text, nullable=False)
    ttl_seconds = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)


class ModelRouteReceiptV3ORM(BaseORM):
    """One durable receipt per LLM task routed through the model router (P0.3.6)."""

    __tablename__ = "model_route_receipts_v3"

    id = Column(String(128), primary_key=True)
    task_id = Column(String(128), nullable=False, index=True)
    role = Column(String(128), nullable=False, default="")
    rule_id = Column(String(128), nullable=False, default="")
    route_lock_id = Column(String(128), ForeignKey("route_locks_v3.id"), nullable=False)
    selected_provider = Column(String(128), nullable=True)
    selected_model_id = Column(String(128), nullable=False, default="")
    provider_model_id = Column(String(128), nullable=True)
    endpoint_id = Column(String(128), nullable=True)
    fallback_used = Column(Boolean, nullable=False, default=False)
    fallback_reason = Column(String(128), nullable=True)
    status = Column(String(16), nullable=False, default="success")  # success | failed
    error_code = Column(String(128), nullable=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_model_route_receipts_task", "task_id"),
        Index("ix_model_route_receipts_role_created", "role", "created_at"),
    )
