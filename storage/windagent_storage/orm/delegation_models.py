"""ORM for durable recursive subagent delegation (Phase 4)."""
from __future__ import annotations
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from windagent_storage.orm.models import BaseORM, default_utc_now
class AgentDelegationORM(BaseORM):
    __tablename__ = "agent_delegations"
    child_agent_run_id = Column(String(64), ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), primary_key=True)
    parent_agent_run_id = Column(String(64), nullable=False, index=True)
    root_agent_run_id = Column(String(64), nullable=False, index=True)
    delegation_depth = Column(Integer, nullable=False)
    delegation_reason = Column(String(255), nullable=False)
    failure_policy = Column(String(32), nullable=False, default="fail_parent")
    allocated_budget_json = Column(Text, nullable=False, default="{}")
    child_result_summary_json = Column(Text, nullable=True)
    child_artifact_refs_json = Column(Text, nullable=False, default="[]")
    bounded_context_json = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
