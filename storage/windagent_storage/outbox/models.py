"""Outbox persistence models for WindAgent Storage Layer (Phase 3)."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OutboxRecord(BaseModel):
    """Canonical outbox record model for durable event publication."""
    id: str
    event_id: str
    aggregate_id: Optional[str] = None
    aggregate_type: Optional[str] = None
    event_type: str
    payload_json: str
    schema_version: int = 1
    sequence_number: int = 0
    created_at: datetime = Field(default_factory=default_utc_now)
    available_at: datetime = Field(default_factory=default_utc_now)
    published_at: Optional[datetime] = None
    attempt_count: int = 0
    last_error: Optional[str] = None
    status: str = "pending"  # pending, published, failed, dead_letter
    deduplication_key: Optional[str] = None

    model_config = ConfigDict(frozen=False)
