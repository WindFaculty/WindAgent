"""Heartbeat hardening for Phase 5 — two-role semantics (Phase 5 §10).

WindAgent already runs an independent ProductionWorker with heartbeat
renewal + fencing-aware execution (orchestration/worker continuation
principle). This module makes that contract testable as a domain rule
at the orchestration seam:

  heartbeat == observability + control-plane liveness

Observability: heartbeat carries worker_id, run_id, active_leases,
  and attestation metadata (never content).
Control-plane liveness: heartbeat owns the durable fencing lease. A
  renewal that returns False (fencing token mismatch / takeover) must
  fence-reject the stale worker via cancellation.

No new daemon is introduced; this is a thin hardening surface that
delegates to the existing Worker/lease APIs and is exercised by
Phase 5 tests without requiring a live worker process.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class HeartbeatRecord:
    worker_id: str
    runtime_run_id: str
    active_leases: int
    recorded_at: datetime = field(default_factory=_utc_now)
    fencing_token: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HeartbeatResult:
    recorded: HeartbeatRecord
    lease_renewed: Optional[bool] = None
    fencing_rejected: bool = False
    cancelled: bool = False


class HeartbeatHardening:
    """Deterministic heartbeat facade preserving the two-role semantics.

    Operates over injected collaborators so it remains scheduler/host-owned
    and test-friendly (no background asyncio loops required for unit tests).
    Production Worker still runs its own ``_heartbeat_loop``; this class is
    the inspection + single-tick semantics layer for Phase 5 verification.
    """

    def __init__(
        self,
        *,
        worker_id: str,
        runtime_run_id: str | None = None,
        heartbeat_repo: Any | None = None,
        lease_manager: Any | None = None,
        task_queue: Any | None = None,
        current_task_provider: Callable[[], tuple[Optional[str], Optional[str]]] | None = None,
        cancellation_hook: Callable[[], Any] | None = None,
    ) -> None:
        self.worker_id = str(worker_id)
        self.runtime_run_id = str(runtime_run_id or f"run_{uuid.uuid4().hex[:8]}")
        self.heartbeat_repo = heartbeat_repo
        self.lease_manager = lease_manager
        self.task_queue = task_queue
        self._current_task_provider = current_task_provider or (lambda: (None, None))
        self._cancellation_hook = cancellation_hook
        self._history: List[HeartbeatRecord] = []
        self._cancelled_count = 0

    def set_current_task(self, provider: Callable[[], tuple[Optional[str], Optional[str]]]) -> None:
        self._current_task_provider = provider

    @property
    def history(self) -> List[HeartbeatRecord]:
        return list(self._history)

    @property
    def cancelled_count(self) -> int:
        return self._cancelled_count

    async def heartbeat_tick(self, *, active_leases: int | None = None) -> HeartbeatResult:
        task_id, fencing_token = self._current_task_provider()
        # active_leases defaults to 1 when holding a task, 0 otherwise — matches ProductionWorker
        if active_leases is None:
            active_leases = 1 if task_id else 0
        rec = HeartbeatRecord(
            worker_id=self.worker_id,
            runtime_run_id=self.runtime_run_id,
            active_leases=int(active_leases),
            recorded_at=_utc_now(),
            fencing_token=fencing_token,
            metadata={"runtime_run_id": self.runtime_run_id},
        )
        # observability — best effort SQL record
        if self.heartbeat_repo is not None and hasattr(self.heartbeat_repo, "record_heartbeat"):
            try:
                # adapt to core's WorkerHeartbeat shape: worker_id, runtime_type, health, active_leases, last_heartbeat_at, metadata
                from windagent_core.contracts.workers import WorkerHeartbeat, WorkerHealth

                hb = WorkerHeartbeat(
                    worker_id=self.worker_id,
                    runtime_type="production_worker",
                    health=WorkerHealth.HEALTHY,
                    active_leases=int(active_leases),
                    last_heartbeat_at=rec.recorded_at,
                    metadata=dict(rec.metadata),
                )
                await self.heartbeat_repo.record_heartbeat(hb)
            except Exception:
                pass

        renewed: Optional[bool] = None
        fencing_rejected = False
        cancelled = False

        if task_id and fencing_token:
            if self.task_queue is not None and hasattr(self.task_queue, "renew"):
                try:
                    res = self.task_queue.renew(str(task_id), str(self.worker_id), str(fencing_token))
                    renewed = await res if hasattr(res, "__await__") else res  # type: ignore
                except Exception:
                    renewed = False
            elif self.lease_manager is not None and hasattr(self.lease_manager, "renew_lease"):
                try:
                    res = self.lease_manager.renew_lease(
                        str(task_id), str(self.worker_id), fencing_token=str(fencing_token)
                    )
                    renewed = await res if hasattr(res, "__await__") else res  # type: ignore
                except Exception:
                    renewed = False

            if renewed is False:
                fencing_rejected = True
                # control-plane liveness: fencing mismatch -> cancel execution
                if self._cancellation_hook is not None:
                    try:
                        res = self._cancellation_hook()
                        if hasattr(res, "__await__"):
                            await res  # type: ignore
                    except Exception:
                        pass
                self._cancelled_count += 1
                cancelled = True

        self._history.append(rec)
        return HeartbeatResult(recorded=rec, lease_renewed=renewed, fencing_rejected=fencing_rejected, cancelled=cancelled)

    def determinism_snapshot(self) -> Dict[str, Any]:
        """Redaction-safe snapshot for deterministic-restart assertions."""
        return {
            "worker_id": self.worker_id,
            "runtime_run_id": self.runtime_run_id,
            "ticks": len(self._history),
            "cancelled_count": self._cancelled_count,
            "last_tick_at": self._history[-1].recorded_at.isoformat() if self._history else None,
        }
