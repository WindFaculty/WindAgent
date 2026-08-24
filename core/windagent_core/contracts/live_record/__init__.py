"""Canonical Live Record contracts (live_record.contract/v0.1).

Identity, error, and port contracts for the Live Record subsystem:
Episode -> LiveExecutionPlan -> RecordingTake lineage (ban_ke_hoach_v1.md
Phase 1). The plan is immutable after FROZEN; staleness is derived by
comparing ``episode_revision_id`` against the episode's current revision.
"""

from windagent_core.contracts.live_record.errors import (
    HTTP_STATUS_BY_CODE,
    LiveRecordCapabilityUnavailableError,
    LiveRecordError,
    LiveRecordErrorCode,
    LiveRecordInvalidTransitionError,
    LiveRecordNotFrozenError,
    LiveRecordNotFoundError,
    LiveRecordPlanFrozenError,
    LiveRecordPlanStaleError,
    LiveRecordValidationError,
)
from windagent_core.contracts.live_record.ids import (
    DirectorSessionId,
    LiveExecutionPlanId,
    RecordingTakeId,
)

# NOTE: repository ports are intentionally NOT re-exported here. Importing them
# in this package __init__ creates a circular import with
# ``windagent_core.domain.live_record`` (ports -> plan -> lifecycle -> this
# package's errors). Import via ``windagent_core.contracts.live_record.ports``.

__all__ = [
    "HTTP_STATUS_BY_CODE",
    "LiveRecordCapabilityUnavailableError",
    "LiveRecordError",
    "LiveRecordErrorCode",
    "LiveRecordInvalidTransitionError",
    "LiveRecordNotFrozenError",
    "LiveRecordNotFoundError",
    "LiveRecordPlanFrozenError",
    "LiveRecordPlanStaleError",
    "LiveRecordValidationError",
    "DirectorSessionId",
    "LiveExecutionPlanId",
    "RecordingTakeId",
]
