"""
Durable checkpoint model for the Durable Production Workflow (plan 05 §8.3).

A checkpoint records, atomically with the run state and outgoing outbox
events (via the engine's unit-of-work):

- current step id + version;
- attempt number;
- input revision/hash and output artifact hashes;
- worker lease (owner, expires_at) for stale-write protection;
- pending external operation (provider, request hash, external id) so a crash
  between submit and result ingestion always lands in reconciliation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class WorkerLease:
    worker_id: str
    expires_at: float  # unix epoch seconds
    token: str = field(default_factory=lambda: uuid.uuid4().hex)

    def is_expired(self, now: Optional[float] = None) -> bool:
        """True when the lease has passed its expiry (clock-injectable)."""
        return (now if now is not None else time.time()) > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "expires_at": self.expires_at,
            "token": self.token,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["WorkerLease"]:
        if not data:
            return None
        return cls(
            worker_id=data["worker_id"],
            expires_at=data["expires_at"],
            token=data.get("token", ""),
        )


@dataclass
class PendingExternalOperation:
    """An operation submitted to an external provider that is not yet resolved."""

    step_id: str
    provider: str
    request_hash: str
    external_id: str = ""  # generation/job id at the provider
    submitted_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "provider": self.provider,
            "request_hash": self.request_hash,
            "external_id": self.external_id,
            "submitted_at": self.submitted_at,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["PendingExternalOperation"]:
        if not data:
            return None
        return cls(
            step_id=data["step_id"],
            provider=data["provider"],
            request_hash=data["request_hash"],
            external_id=data.get("external_id", ""),
            submitted_at=data.get("submitted_at", 0.0),
        )


@dataclass
class ProductionCheckpoint:
    """Checkpoint payload persisted atomically with the run (plan 05 §8.3)."""

    run_id: str
    current_step: str
    step_version: int = 1
    attempt: int = 1
    input_revision_hash: str = ""
    input_hashes: Dict[str, str] = field(default_factory=dict)
    output_hashes: Dict[str, str] = field(default_factory=dict)
    lease: Optional[WorkerLease] = None
    pending_external_operation: Optional[PendingExternalOperation] = None
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "current_step": self.current_step,
            "step_version": self.step_version,
            "attempt": self.attempt,
            "input_revision_hash": self.input_revision_hash,
            "input_hashes": dict(self.input_hashes),
            "output_hashes": dict(self.output_hashes),
            "lease": self.lease.to_dict() if self.lease else None,
            "pending_external_operation": (
                self.pending_external_operation.to_dict()
                if self.pending_external_operation
                else None
            ),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProductionCheckpoint":
        return cls(
            run_id=data["run_id"],
            current_step=data["current_step"],
            step_version=data.get("step_version", 1),
            attempt=data.get("attempt", 1),
            input_revision_hash=data.get("input_revision_hash", ""),
            input_hashes=data.get("input_hashes", {}),
            output_hashes=data.get("output_hashes", {}),
            lease=WorkerLease.from_dict(data.get("lease")),
            pending_external_operation=PendingExternalOperation.from_dict(
                data.get("pending_external_operation")
            ),
            updated_at=data.get("updated_at", 0.0),
        )


__all__ = [
    "WorkerLease",
    "PendingExternalOperation",
    "ProductionCheckpoint",
]
