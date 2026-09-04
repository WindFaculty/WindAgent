"""Checkpoint aggregate (Phase 13).

Immutable, append-only snapshot for recovery.  Every checkpoint carries a
monotonic ``seq`` scoped to its run (+ task) and a content-addressed hash of
the snapshot payload so replay is deterministic and tamper-evident.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import AgentRuntimeValidationError


def _utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_hash(payload: Any) -> str:
    dumped = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


class CheckpointRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_id: str | None = None
    workflow_id: str | None = None
    step_id: str | None = None
    seq: int = Field(ge=0)
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    snapshot_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("snapshot_hash")
    @classmethod
    def _hash_hex(cls, v: str) -> str:
        if len(v) != 64:
            raise AgentRuntimeValidationError("Checkpoint snapshot_hash must be 64-char SHA-256 hex.")
        try:
            int(v, 16)
        except ValueError as exc:
            raise AgentRuntimeValidationError("Checkpoint snapshot_hash must be hex.") from exc
        return v.lower()

    @classmethod
    def create(
        cls,
        *,
        checkpoint_id: str,
        run_id: str,
        seq: int,
        state_snapshot: dict[str, Any],
        task_id: str | None = None,
        workflow_id: str | None = None,
        step_id: str | None = None,
    ) -> CheckpointRecord:
        if not checkpoint_id.strip():
            raise AgentRuntimeValidationError("checkpoint_id cannot be blank.")
        if not run_id.strip():
            raise AgentRuntimeValidationError("run_id cannot be blank.")
        if seq < 0:
            raise AgentRuntimeValidationError("Checkpoint seq must be >= 0.")
        h = canonical_hash(state_snapshot)
        return cls(
            checkpoint_id=checkpoint_id.strip(),
            run_id=run_id.strip(),
            task_id=task_id,
            workflow_id=workflow_id,
            step_id=step_id,
            seq=seq,
            state_snapshot=state_snapshot,
            snapshot_hash=h,
            created_at=_utc_now(),
        )


__all__ = ["CheckpointRecord", "canonical_hash"]
