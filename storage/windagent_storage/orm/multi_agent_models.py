"""ORM for multi-agent canonical tables (Phase 1).

Defines minimal declarative tables for BaseORM metadata so that
Phase 2's ``agent_loop_states.agent_run_id -> agent_runs.agent_run_id`` FK
can be resolved during ``BaseORM.metadata.create_all`` (0001 baseline).

The tables are intentionally minimal (no FKs to other canonical tables)
to avoid requiring the full dependency chain in metadata; the real
FK-enforced DDL lives in migrations 0003/0004.  Migrations remain the
authoritative DDL for file DBs; this module only ensures metadata
contains the referenced table for FK resolution and for in-memory
``create_all`` fallback.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from windagent_storage.orm.models import BaseORM, default_utc_now


class ConversationORM(BaseORM):
    __tablename__ = "conversations"
    conversation_id = Column(String(36), primary_key=True)
    title = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="idle")
    metadata_json = Column(Text, nullable=True)
    last_event_sequence = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class ParentTaskORM(BaseORM):
    __tablename__ = "parent_tasks"
    parent_task_id = Column(String(36), primary_key=True)
    conversation_id = Column(String(36), ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False)
    objective = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="draft")
    active_plan_version_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class TaskPlanVersionORM(BaseORM):
    __tablename__ = "task_plan_versions"
    plan_version_id = Column(String(64), primary_key=True)
    parent_task_id = Column(String(36), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    dag_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class TaskNodeRunORM(BaseORM):
    __tablename__ = "task_node_runs"
    task_node_run_id = Column(String(64), primary_key=True)
    plan_version_id = Column(String(64), nullable=True)
    node_id = Column(String(64), nullable=False)
    parent_task_id = Column(String(36), nullable=True)
    agent_instance_id = Column(String(64), nullable=True)
    state = Column(String(32), nullable=False, default="received")
    version = Column(Integer, nullable=False, default=1)
    facts_json = Column(Text, nullable=False, default="{}")
    dependency_state_json = Column(Text, nullable=False, default="{}")
    retry_state_json = Column(Text, nullable=False, default="{}")
    routing_snapshot_json = Column(Text, nullable=False, default="{}")
    concurrency_group = Column(String(128), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class AgentInstanceORM(BaseORM):
    __tablename__ = "agent_instances"
    agent_instance_id = Column(String(64), primary_key=True)
    conversation_id = Column(String(36), ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False)
    parent_task_id = Column(String(36), nullable=True)
    agent_type = Column(String(64), nullable=False)
    permission_profile_json = Column(Text, nullable=True)
    canonical_model_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="created")
    assigned_node_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class AgentSessionORM(BaseORM):
    __tablename__ = "agent_sessions"
    agent_session_id = Column(String(64), primary_key=True)
    agent_instance_id = Column(String(64), ForeignKey("agent_instances.agent_instance_id", ondelete="CASCADE"), nullable=False)
    windagent_session_id = Column(String(64), nullable=False, unique=True)
    runtime_locator = Column(String(255), nullable=True)
    hermes_run_id = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="idle")
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class AgentRunORM(BaseORM):
    """Minimal run table to satisfy FK from agent_loop_states.

    Real DDL with full FKs lives in 0004; this stub only ensures the
    referenced table exists in metadata for FK resolution.
    """

    __tablename__ = "agent_runs"
    agent_run_id = Column(String(64), primary_key=True)
    agent_instance_id = Column(String(64), nullable=False)
    agent_session_id = Column(String(64), nullable=False)
    parent_task_id = Column(String(36), nullable=False)
    plan_version_id = Column(String(64), nullable=False)
    task_node_run_id = Column(String(64), nullable=False)
    runtime_handle_id = Column(String(128), nullable=True)
    runtime_run_id = Column(String(128), nullable=True)
    runtime_locator = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="dispatching")
    routing_snapshot_json = Column(Text, nullable=False, default="{}")
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class AgentTurnORM(BaseORM):
    __tablename__ = "agent_turns"
    turn_id = Column(String(64), primary_key=True)
    agent_run_id = Column(String(64), nullable=False)
    agent_session_id = Column(String(64), nullable=False)
    route_lock_id = Column(String(64), nullable=False)
    canonical_model_id = Column(String(128), nullable=False)
    routing_snapshot_json = Column(Text, nullable=False, default="{}")
    response_summary_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="running")
    error_class = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
