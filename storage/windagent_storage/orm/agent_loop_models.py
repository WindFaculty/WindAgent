"""ORM for durable agent loop state & budget snapshots (Phase 2).

Single canonical table ``agent_loop_states`` holds per-run loop state,
optimistic version, JSON budgets, scope, exhaustion reason, and timestamps.
Registered on BaseORM for create_all fallback; migrations own DDL for file DBs.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from windagent_storage.orm.models import BaseORM, default_utc_now


class AgentLoopStateORM(BaseORM):
    """Durable loop + budget row keyed by ``agent_run_id``."""

    __tablename__ = "agent_loop_states"

    agent_run_id = Column(
        String(64),
        ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    state = Column(String(32), nullable=False, default="CREATED")
    version = Column(Integer, nullable=False, default=1)
    budget_limits_json = Column(Text, nullable=False, default="{}")
    budget_usage_json = Column(Text, nullable=False, default="{}")
    budget_scope = Column(String(32), nullable=False, default="conversation")
    exhaustion_reason = Column(String(64), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
