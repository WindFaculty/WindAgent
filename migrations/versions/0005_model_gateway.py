"""Model gateway tables (Phase 11).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_gateway_providers",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("vendor_type", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("protocol_mode", sa.String(length=50), nullable=False),
        sa.Column("supports_model_discovery", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_gateway_providers")),
        sa.UniqueConstraint("name", name=op.f("uq_model_gateway_providers_name")),
    )
    op.create_table(
        "model_gateway_endpoints",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("provider_id", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("protocol_mode", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("test_status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_gateway_endpoints")),
    )
    op.create_index(
        op.f("ix_model_gateway_endpoints_provider_id"),
        "model_gateway_endpoints",
        ["provider_id"],
        unique=False,
    )
    op.create_table(
        "model_gateway_credentials",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("provider_id", sa.String(length=100), nullable=False),
        sa.Column("secret_name", sa.String(length=200), nullable=False),
        sa.Column("secret_version", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_gateway_credentials")),
        sa.UniqueConstraint(
            "secret_name", name=op.f("uq_model_gateway_credentials_secret_name")
        ),
    )
    op.create_index(
        op.f("ix_model_gateway_credentials_provider_id"),
        "model_gateway_credentials",
        ["provider_id"],
        unique=False,
    )
    op.create_table(
        "model_gateway_models",
        sa.Column("canonical_name", sa.String(length=300), nullable=False),
        sa.Column("vendor", sa.String(length=100), nullable=False),
        sa.Column("family", sa.String(length=200), nullable=False),
        sa.Column("revision", sa.String(length=100), nullable=True),
        sa.Column("quantization", sa.String(length=50), nullable=True),
        sa.Column("parameter_size", sa.String(length=50), nullable=True),
        sa.Column("equivalence_fingerprint", sa.String(length=400), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "canonical_name", name=op.f("pk_model_gateway_models")
        ),
    )
    op.create_table(
        "model_gateway_bindings",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("endpoint_id", sa.String(length=120), nullable=False),
        sa.Column("canonical_model_id", sa.String(length=300), nullable=False),
        sa.Column("provider_model_id", sa.String(length=300), nullable=False),
        sa.Column("equivalence_level", sa.String(length=60), nullable=False),
        sa.Column("equivalence_fingerprint", sa.String(length=400), nullable=False),
        sa.Column("pricing_class", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("availability", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_gateway_bindings")),
    )
    op.create_index(
        op.f("ix_model_gateway_bindings_endpoint_id"),
        "model_gateway_bindings",
        ["endpoint_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_gateway_bindings_canonical_model_id"),
        "model_gateway_bindings",
        ["canonical_model_id"],
        unique=False,
    )
    op.create_index(
        "uq_model_gateway_bindings_pair",
        "model_gateway_bindings",
        ["endpoint_id", "canonical_model_id"],
        unique=True,
    )
    op.create_table(
        "model_gateway_rules",
        sa.Column("rule_id", sa.String(length=200), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("canonical_model_id", sa.String(length=300), nullable=False),
        sa.Column("fallback_model_id", sa.String(length=300), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("task_labels_json", sa.Text(), nullable=False),
        sa.Column("agent_types_json", sa.Text(), nullable=False),
        sa.Column("workflow_types_json", sa.Text(), nullable=False),
        sa.Column("required_capabilities_json", sa.Text(), nullable=False),
        sa.Column("min_context_tokens", sa.Integer(), nullable=False),
        sa.Column("requires_tools", sa.Boolean(), nullable=False),
        sa.Column("requires_vision", sa.Boolean(), nullable=False),
        sa.Column("cost_classes_json", sa.Text(), nullable=False),
        sa.Column("requires_local", sa.Boolean(), nullable=False),
        sa.Column("requires_private", sa.Boolean(), nullable=False),
        sa.Column("user_preference_model", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("rule_id", name=op.f("pk_model_gateway_rules")),
    )
    op.create_table(
        "model_gateway_route_locks",
        sa.Column("lock_id", sa.String(length=36), nullable=False),
        sa.Column("scope_type", sa.String(length=30), nullable=False),
        sa.Column("scope_id", sa.String(length=200), nullable=False),
        sa.Column("canonical_model_id", sa.String(length=300), nullable=False),
        sa.Column("rule_id", sa.String(length=200), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reselection_count", sa.Integer(), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False),
        sa.Column("source_lock_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("lock_id", name=op.f("pk_model_gateway_route_locks")),
    )
    op.create_index(
        "uq_model_gateway_route_locks_active",
        "model_gateway_route_locks",
        ["scope_type", "scope_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_model_gateway_route_locks_scope",
        "model_gateway_route_locks",
        ["scope_type", "scope_id"],
        unique=False,
    )
    op.create_table(
        "model_gateway_endpoint_state",
        sa.Column("endpoint_id", sa.String(length=120), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("circuit_open_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_latency_ms", sa.Float(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_class", sa.String(length=100), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "endpoint_id", name=op.f("pk_model_gateway_endpoint_state")
        ),
    )
    op.create_table(
        "model_gateway_quota_state",
        sa.Column("provider_name", sa.String(length=200), nullable=False),
        sa.Column("has_quota", sa.Boolean(), nullable=False),
        sa.Column("remaining_requests_today", sa.Integer(), nullable=True),
        sa.Column("remaining_tokens_today", sa.Integer(), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "provider_name", name=op.f("pk_model_gateway_quota_state")
        ),
    )
    op.create_table(
        "model_gateway_attempts",
        sa.Column("id", sa.String(length=200), nullable=False),
        sa.Column("route_lock_id", sa.String(length=36), nullable=False),
        sa.Column("endpoint_id", sa.String(length=120), nullable=False),
        sa.Column("binding_id", sa.String(length=120), nullable=False),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_class", sa.String(length=100), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_gateway_attempts")),
    )
    op.create_index(
        op.f("ix_model_gateway_attempts_route_lock_id"),
        "model_gateway_attempts",
        ["route_lock_id"],
        unique=False,
    )
    op.create_table(
        "model_gateway_secrets",
        sa.Column("secret_name", sa.String(length=200), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("secret_name", name=op.f("pk_model_gateway_secrets")),
    )
    op.create_table(
        "model_gateway_receipts",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("task_id", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column("route_lock_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=200), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(length=100), nullable=False),
        sa.Column("canonical_model_id", sa.String(length=300), nullable=False),
        sa.Column("provider_model_id", sa.String(length=300), nullable=False),
        sa.Column("endpoint_id", sa.String(length=120), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("fallback_reason", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_gateway_receipts")),
    )
    op.create_index(
        "ix_model_gateway_receipts_task",
        "model_gateway_receipts",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("model_gateway_secrets")
    op.drop_index("ix_model_gateway_receipts_task", table_name="model_gateway_receipts")
    op.drop_table("model_gateway_receipts")
    op.drop_index(
        op.f("ix_model_gateway_attempts_route_lock_id"), table_name="model_gateway_attempts"
    )
    op.drop_table("model_gateway_attempts")
    op.drop_table("model_gateway_quota_state")
    op.drop_table("model_gateway_endpoint_state")
    op.drop_index(
        "ix_model_gateway_route_locks_scope", table_name="model_gateway_route_locks"
    )
    op.drop_index(
        "uq_model_gateway_route_locks_active", table_name="model_gateway_route_locks"
    )
    op.drop_table("model_gateway_route_locks")
    op.drop_table("model_gateway_rules")
    op.drop_index(
        "uq_model_gateway_bindings_pair", table_name="model_gateway_bindings"
    )
    op.drop_index(
        op.f("ix_model_gateway_bindings_canonical_model_id"),
        table_name="model_gateway_bindings",
    )
    op.drop_index(
        op.f("ix_model_gateway_bindings_endpoint_id"), table_name="model_gateway_bindings"
    )
    op.drop_table("model_gateway_bindings")
    op.drop_table("model_gateway_models")
    op.drop_index(
        op.f("ix_model_gateway_credentials_provider_id"),
        table_name="model_gateway_credentials",
    )
    op.drop_table("model_gateway_credentials")
    op.drop_index(
        op.f("ix_model_gateway_endpoints_provider_id"), table_name="model_gateway_endpoints"
    )
    op.drop_table("model_gateway_endpoints")
    op.drop_table("model_gateway_providers")
