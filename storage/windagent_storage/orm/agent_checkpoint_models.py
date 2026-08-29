"""ORM for durable Agent Checkpoints (Phase 5)."""
from __future__ import annotations
from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from windagent_storage.orm.models import BaseORM, default_utc_now

class AgentCheckpointORM(BaseORM):
    __tablename__ = "agent_checkpoints"

    checkpoint_id = Column(String(64), primary_key=True)
    agent_run_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    kind = Column(String(32), nullable=False, index=True)
    step_run_id = Column(String(64), nullable=True)
    tool_name = Column(String(64), nullable=True)
    fencing_token = Column(String(128), nullable=False, default="")
    snapshot_json = Column(Text, nullable=False, default="{}")
    sequence = Column(Integer, nullable=False, default=0)
    loop_version_at_checkpoint = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_agent_checkpoints_run_seq", "agent_run_id", "sequence"),
        Index("ix_agent_checkpoints_run_kind", "agent_run_id", "kind"),
    )
