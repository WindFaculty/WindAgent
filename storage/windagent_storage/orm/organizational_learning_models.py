"""SQLAlchemy ORM models for Organizational Learning records (Phase 14 — ban_ke_hoach_v1 §20, §23, §24, §25)."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    String,
    Text,
)

from windagent_storage.orm.candidate_models import LearnedRuleORM
from windagent_storage.orm.models import BaseORM


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConflictResolutionORM(BaseORM):
    """SQLAlchemy model for conflict resolution audit records."""
    __tablename__ = "conflict_resolutions"

    resolution_id = Column(String(64), primary_key=True)
    domain = Column(String(64), nullable=False, index=True)
    context_query_json = Column(Text, nullable=False, default="{}")
    winning_rule_id = Column(String(64), nullable=False, index=True)
    competing_rule_ids_json = Column(Text, nullable=False, default="[]")
    resolution_rationale = Column(Text, nullable=False, default="")
    score_breakdown_json = Column(Text, nullable=False, default="{}")
    resolved_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_conflict_res_domain", "domain"),
        Index("ix_conflict_res_resolved_at", "resolved_at"),
    )


class MultiAgentAttributionORM(BaseORM):
    """SQLAlchemy model for multi-agent stage-separated performance attributions."""
    __tablename__ = "multi_agent_attributions"

    attribution_id = Column(String(64), primary_key=True)
    episode_id = Column(String(64), nullable=False, index=True)
    domain = Column(String(64), nullable=False, default="youtube_studio", index=True)
    metric_signals_json = Column(Text, nullable=False, default="{}")
    role_attributions_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_attributions_episode_id", "episode_id"),
        Index("ix_attributions_created_at", "created_at"),
    )


__all__ = [
    "LearnedRuleORM",
    "ConflictResolutionORM",
    "MultiAgentAttributionORM",
]

