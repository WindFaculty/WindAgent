"""Live Record persistence ORM models (live_record.contract/v0.1).

Tables owned exclusively by the additive migration ``0019_live_record_domain``.
Importing this module registers the tables on ``BaseORM.metadata`` (used by
tests and the ``create_all`` dev path); the Alembic chain deliberately does NOT
import it so the migration stays the only producer of the schema on real
databases.

Lineage: Episode -> LiveExecutionPlan -> RecordingTake -> RecordingSegment,
with append-only RecordingEvent timeline rows and DirectorSession rows.
Scenes/cues/actions are stored as JSON columns on the plan row — they are
value objects of the immutable plan aggregate, not independent entities
(mirrors the TS domain contract where they are readonly arrays).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint

from windagent_storage.orm.models import BaseORM


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LiveExecutionPlanORM(BaseORM):
    __tablename__ = "live_execution_plans"

    plan_id = Column(String(64), primary_key=True)
    episode_id = Column(String(64), nullable=False, index=True)
    episode_revision_id = Column(String(64), nullable=False)
    preparation_revision = Column(Integer, nullable=False, default=1)
    plan_hash = Column(String(64), nullable=False, default="")
    status = Column(String(32), nullable=False, default="DRAFT")
    director_role = Column(String(32), nullable=False, default="LIVE_DIRECTOR")
    recording_profile_json = Column(Text, nullable=False, default="{}")
    scenes_json = Column(Text, nullable=False, default="[]")
    actions_json = Column(Text, nullable=False, default="[]")
    # Exact prepared payloads keyed by action_id (PreparedCodeBundle). Never
    # exposed through tool args — Principle C.
    payload_bundles_json = Column(Text, nullable=False, default="{}")
    source_workspace_hash = Column(String(64), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    frozen_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    optimistic_version = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("ix_live_plans_episode_status", "episode_id", "status"),
        UniqueConstraint(
            "episode_id", "preparation_revision",
            name="uq_live_plan_episode_revision_number",
        ),
    )


class LiveRecordTakeORM(BaseORM):
    __tablename__ = "live_record_takes"

    take_id = Column(String(64), primary_key=True)
    execution_plan_id = Column(String(64), nullable=False, index=True)
    execution_plan_hash = Column(String(64), nullable=False)
    episode_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="IDLE")
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    optimistic_version = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=False, default="{}")


class LiveRecordSegmentORM(BaseORM):
    __tablename__ = "live_record_segments"

    segment_id = Column(String(64), primary_key=True)
    take_id = Column(String(64), nullable=False, index=True)
    segment_index = Column(Integer, nullable=False, default=0)
    # Tokenized delivery reference — raw FS paths never reach the UI layer.
    file_token = Column(String(255), nullable=False, default="")
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Float, nullable=True)
    is_playable = Column(Boolean, nullable=False, default=False)
    manifest_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("take_id", "segment_index", name="uq_live_segment_take_index"),
    )


class LiveRecordEventORM(BaseORM):
    """Append-only recording timeline rows (``timeline.jsonl`` durable mirror).

    Composite PK ``(take_id, seq)`` with strictly increasing ``seq`` per take;
    ``t`` is seconds since take start so TTS alignment stays monotonic.
    """

    __tablename__ = "live_record_events"

    take_id = Column(String(64), primary_key=True)
    seq = Column(Integer, primary_key=True)
    event_type = Column(String(48), nullable=False)
    t = Column(Float, nullable=False, default=0.0)
    scene_id = Column(String(64), nullable=True)
    cue_id = Column(String(64), nullable=True)
    action_id = Column(String(64), nullable=True)
    segment_id = Column(String(64), nullable=True)
    execution_id = Column(String(64), nullable=True)
    marker_type = Column(String(64), nullable=True)
    detail = Column(Text, nullable=False, default="")
    payload_json = Column(Text, nullable=False, default="{}")
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_live_events_take_t", "take_id", "t"),
    )


class DirectorSessionORM(BaseORM):
    """One Gemini Live director session bound to a frozen plan."""

    __tablename__ = "director_sessions"

    session_id = Column(String(64), primary_key=True)
    execution_plan_id = Column(String(64), nullable=False, index=True)
    execution_plan_hash = Column(String(64), nullable=False)
    provider_id = Column(String(64), nullable=True)
    model_id = Column(String(128), nullable=True)
    connection_state = Column(String(32), nullable=False, default="DISCONNECTED")
    started_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    metadata_json = Column(Text, nullable=False, default="{}")


__all__ = [
    "LiveExecutionPlanORM",
    "LiveRecordTakeORM",
    "LiveRecordSegmentORM",
    "LiveRecordEventORM",
    "DirectorSessionORM",
]
