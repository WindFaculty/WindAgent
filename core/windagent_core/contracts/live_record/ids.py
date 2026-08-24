"""Canonical Live Record identity contract (live_record.contract/v0.1).

Opaque identifiers for the Live Record lineage:
- ``LiveExecutionPlanId`` — frozen execution plan derived from an Episode revision.
- ``RecordingTakeId`` — one recording run of a frozen plan.
- ``DirectorSessionId`` — one Gemini Live director session bound to a plan.
"""

from __future__ import annotations

from windagent_core.domain.types import OpaqueId

__all__ = [
    "LiveExecutionPlanId",
    "RecordingTakeId",
    "DirectorSessionId",
]


class LiveExecutionPlanId(OpaqueId):
    """Identifier for an immutable LiveExecutionPlan aggregate."""


class RecordingTakeId(OpaqueId):
    """Identifier for a RecordingTake of a frozen execution plan."""


class DirectorSessionId(OpaqueId):
    """Identifier for a Gemini Live director session."""
