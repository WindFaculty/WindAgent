"""
Typed runtime capability contract (studio.contract/v0.1).

A ``RuntimeCapabilityProfile`` reports what a deployed environment can actually
do — durable DB, real model route, worker, Blender, and future story engines —
with source, reason, and timestamp for every entry. The certification profile
fails closed when a fake runtime/mock fallback/bypass is reported active.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

CAPABILITY_SCHEMA_VERSION = "studio.capability/v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CapabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class CapabilityKind(str, Enum):
    DURABLE_DB = "durable_db"
    DB = "durable_db"
    WORKER = "worker"
    MODEL_ROUTE = "model_route"
    MODEL = "model_route"
    BLENDER = "blender"
    STORY_ENGINE = "story_engine"
    QUEUE = "queue"
    OUTBOX = "outbox"
    UNREAL = "unreal"


class RuntimeCapability(BaseModel):
    """A single typed capability observation."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    source: str = Field(default="?", min_length=1)
    reason: str = ""
    discovered_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RuntimeCapabilityProfile(BaseModel):
    """Snapshot of detected runtime capabilities with provenance."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = CAPABILITY_SCHEMA_VERSION
    report_timestamp: datetime = Field(default_factory=utc_now)
    capabilities: List[RuntimeCapability] = Field(default_factory=list)
    fail_closed_flags: List[str] = Field(default_factory=list)
    certification_mode: bool = False

    def by_name(self, name: str) -> RuntimeCapability | None:
        for cap in self.capabilities:
            if cap.name == name:
                return cap
        return None

    @property
    def is_fail_closed_ok(self) -> bool:
        """True when no active fake/mock/bypass capability is flagged."""
        return not self.fail_closed_flags

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "CAPABILITY_SCHEMA_VERSION",
    "utc_now",
    "CapabilityStatus",
    "CapabilityKind",
    "RuntimeCapability",
    "RuntimeCapabilityProfile",
]
