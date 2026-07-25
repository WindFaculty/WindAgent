"""Publisher heartbeat model for WindAgent Observability Layer (Phase 6)."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PublisherHeartbeat:
    """Runtime heartbeat snapshot for the outbox publisher loop."""

    state: str = "stopped"  # stopped, starting, running, draining, stopped
    last_poll_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    pending_count: int = 0
    failed_count: int = 0
    dead_letter_count: int = 0
    publishing_count: int = 0

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "pending_count": self.pending_count,
            "failed_count": self.failed_count,
            "dead_letter_count": self.dead_letter_count,
            "publishing_count": self.publishing_count,
        }

    def is_healthy(self, max_stale_seconds: float = 30.0) -> bool:
        if self.state not in ("running", "draining"):
            return False
        if self.last_poll_at is None:
            return False
        age = (_utc_now() - self.last_poll_at).total_seconds()
        return age <= max_stale_seconds
