"""Minimal agent_runs stub for FK resolution (Phase 2)."""
from __future__ import annotations
from sqlalchemy import Column, DateTime, Integer, String, Text
from windagent_storage.orm.models import BaseORM, default_utc_now
class AgentRunStubORM(BaseORM):
    __tablename__ = "agent_runs"
    __table_args__ = {"extend_existing": True}
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
