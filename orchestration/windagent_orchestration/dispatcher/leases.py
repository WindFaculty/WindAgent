"""
Durable Execution Lease Data Model & Manager for Orchestration V2 Dispatcher.
Enforces atomic lease acquisition, idempotency keys, fencing tokens, and TTL expiration.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from windagent_orchestration.metrics import metrics
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

logger = logging.getLogger("windagent.orchestration.dispatcher.leases")


@dataclass
class ExecutionLease:
    lease_id: str
    step_run_id: str
    run_id: str
    worker_id: str
    status: str  # active | expired | released
    expires_at: datetime
    idempotency_key: str
    lease_generation: int = 1
    fencing_token: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LeaseManager:
    def __init__(self, uow_factory: Optional[Any] = None):
        self.uow_factory = uow_factory
        self._in_memory_leases: Dict[str, ExecutionLease] = {}
        self._idempotency_index: Dict[str, ExecutionLease] = {}

    async def acquire_lease(
        self,
        step_run_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: float = 30.0,
        idempotency_key: Optional[str] = None,
    ) -> Optional[ExecutionLease]:
        t0 = time.perf_counter()
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)
        key = idempotency_key or f"{run_id}:{step_run_id}"

        # In-memory deduplication check
        existing = self._idempotency_index.get(key)
        if existing and existing.status == "active" and existing.expires_at > now:
            logger.warning(f"Duplicate lease claim prevented for idempotency key [{key}]")
            duration_ms = (time.perf_counter() - t0) * 1000.0
            metrics.record_dispatch_claim(duration_ms)
            metrics.duplicate_executions += 1
            return None

        lease_id = str(uuid.uuid4())
        lease_gen = 1
        fencing_token = f"fence_{step_run_id}_gen_1_{uuid.uuid4().hex[:6]}"

        if self.uow_factory:
            async with SqlUnitOfWork(self.uow_factory) as uow:
                acquired_dict = await uow.leases.acquire_lease(
                    lease_id=lease_id,
                    step_run_id=step_run_id,
                    run_id=run_id,
                    worker_id=worker_id,
                    ttl_seconds=ttl_seconds,
                    idempotency_key=key,
                )
                await uow.commit()
                if not acquired_dict:
                    metrics.duplicate_executions += 1
                    return None
                if isinstance(acquired_dict, dict):
                    lease_id = acquired_dict.get("lease_id", lease_id)
                    lease_gen = acquired_dict.get("lease_generation", 1)
                    fencing_token = acquired_dict.get("fencing_token", fencing_token)

        lease = ExecutionLease(
            lease_id=lease_id,
            step_run_id=step_run_id,
            run_id=run_id,
            worker_id=worker_id,
            status="active",
            expires_at=expires_at,
            idempotency_key=key,
            lease_generation=lease_gen,
            fencing_token=fencing_token,
            created_at=now,
        )

        self._in_memory_leases[lease_id] = lease
        self._idempotency_index[key] = lease

        duration_ms = (time.perf_counter() - t0) * 1000.0
        metrics.record_dispatch_claim(duration_ms)
        return lease

    async def release_lease(self, lease_id: str, worker_id: str) -> bool:
        lease = self._in_memory_leases.get(lease_id)
        if lease:
            lease.status = "released"

        if self.uow_factory:
            async with SqlUnitOfWork(self.uow_factory) as uow:
                released = await uow.leases.release_lease(lease_id, worker_id)
                await uow.commit()
                return released
        return True

    async def reclaim_expired_leases(self) -> List[str]:
        now = datetime.now(timezone.utc)
        reclaimed: List[str] = []
        for lid, lease in list(self._in_memory_leases.items()):
            if lease.status == "active" and lease.expires_at <= now:
                lease.status = "expired"
                reclaimed.append(lid)

        if self.uow_factory:
            async with SqlUnitOfWork(self.uow_factory) as uow:
                db_reclaimed = await uow.leases.reclaim_expired_leases()
                await uow.commit()
                reclaimed = list(set(reclaimed + db_reclaimed))

        return reclaimed
