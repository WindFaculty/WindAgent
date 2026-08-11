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
WORKER_ATTESTATION_SCHEMA_VERSION = "studio.worker-attestation/v1"
REQUIRED_STORY_TASK_HANDLERS = frozenset(
    {
        "studio.story.idea.generate",
        "studio.story.idea.evaluate",
        "studio.story.bible.generate",
        "studio.story.beats.generate",
        "studio.story.outline.generate",
        "studio.story.screenplay.generate",
        "studio.story.review",
        "studio.story.revise",
        "studio.story.lock",
    }
)


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


class WorkerRuntimeAttestation(BaseModel):
    """Redaction-safe statement of the runtime composed by one live worker."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = WORKER_ATTESTATION_SCHEMA_VERSION
    generated_at: datetime = Field(default_factory=utc_now)
    worker_id: str = Field(min_length=1)
    source_sha: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    certification_mode: bool = False
    runtime_adapter: str = ""
    completion_reconciler: str = ""
    completion_recovery: str = ""
    handler_names: List[str] = Field(default_factory=list)
    handler_digest: str = ""
    model_port_type: str = ""
    canonical_model: str = ""
    provider_route_ready: bool = False
    durable_route_lock: bool = False
    endpoint_binding_identities: List[Dict[str, str]] = Field(default_factory=list)
    fake_runtime: bool = False
    capability_profile: RuntimeCapabilityProfile

    @property
    def is_story_eligible(self) -> bool:
        """True only for a fully composed, real Story execution authority."""

        return (
            self.runtime_adapter == "StudioRuntimeAdapter"
            and self.completion_reconciler == "StudioCompletionReconciler"
            and self.completion_recovery == "StudioCompletionRecovery"
            and REQUIRED_STORY_TASK_HANDLERS <= set(self.handler_names)
            and bool(self.handler_digest)
            and self.model_port_type == "RouteLockedModelPort"
            and bool(self.canonical_model)
            and self.provider_route_ready
            and self.durable_route_lock
            and bool(self.endpoint_binding_identities)
            and not self.fake_runtime
            and self.capability_profile.is_fail_closed_ok
        )


__all__ = [
    "CAPABILITY_SCHEMA_VERSION",
    "WORKER_ATTESTATION_SCHEMA_VERSION",
    "REQUIRED_STORY_TASK_HANDLERS",
    "utc_now",
    "CapabilityStatus",
    "CapabilityKind",
    "RuntimeCapability",
    "RuntimeCapabilityProfile",
    "WorkerRuntimeAttestation",
]
