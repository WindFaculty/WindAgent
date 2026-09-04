"""Recovery helpers (Phase 13).

Deterministic helpers to decide recovery action from a stale worker,
checkpoint, and retry classifier.  Pure domain — no DB access.
"""

from __future__ import annotations

from enum import StrEnum

from .checkpoints import CheckpointRecord
from .errors import AgentRuntimeStateError
from .lifecycle import AgentLoopState, TaskState


class RecoveryAction(StrEnum):
    RESUME = "RESUME"
    RETRY = "RETRY"
    FAIL = "FAIL"
    CANCEL = "CANCEL"
    RECOVER = "RECOVER"


def recover_run_state(
    current_state: AgentLoopState,
    *,
    has_checkpoint: bool,
    exhaustion_reason: str | None = None,
    attempt: int = 1,
    max_attempts: int = 3,
) -> RecoveryAction:
    """Decide recovery for a crashed run."""
    if exhaustion_reason is not None:
        return RecoveryAction.FAIL
    if current_state in (AgentLoopState.FAILED, AgentLoopState.CANCELLED, AgentLoopState.COMPLETED, AgentLoopState.ORPHANED):
        return RecoveryAction.FAIL
    if has_checkpoint:
        return RecoveryAction.RESUME
    if attempt < max_attempts:
        return RecoveryAction.RETRY
    return RecoveryAction.FAIL


def recover_task_state(
    current_state: TaskState,
    *,
    checkpoint: CheckpointRecord | None = None,
    error: str | None = None,
    attempt: int = 1,
    max_attempts: int = 3,
) -> RecoveryAction:
    """Task recovery mirrors TaskLifecycle RECOVERING path."""
    if current_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
        return RecoveryAction.FAIL
    if checkpoint is not None:
        return RecoveryAction.RECOVER
    # Delegates to retry classifier indirectly via attempt gate
    if attempt < max_attempts and error is not None and "timeout" in error.lower():
        return RecoveryAction.RETRY
    if current_state == TaskState.RETRY_WAIT and attempt < max_attempts:
        return RecoveryAction.RETRY
    if current_state == TaskState.RECOVERING:
        return RecoveryAction.RECOVER
    return RecoveryAction.FAIL


def validate_checkpoint_seq(checkpoints: list[CheckpointRecord]) -> None:
    """Ensure monotonic seq within same run_id+task_id scope."""
    if not checkpoints:
        return
    by_scope: dict[tuple[str, str | None], list[CheckpointRecord]] = {}
    for cp in checkpoints:
        key = (cp.run_id, cp.task_id)
        by_scope.setdefault(key, []).append(cp)
    for _key, seq_list in by_scope.items():
        sorted_seq = sorted(seq_list, key=lambda c: c.seq)
        for idx, cp in enumerate(sorted_seq):
            if cp.seq != idx:
                raise AgentRuntimeStateError(
                    f"Checkpoint seq gap: expected {idx}, got {cp.seq}.",
                    context={"run_id": cp.run_id, "task_id": cp.task_id or ""},
                )


__all__ = ["RecoveryAction", "recover_run_state", "recover_task_state", "validate_checkpoint_seq"]
