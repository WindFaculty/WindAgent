"""
Worker Node Registry for Orchestration V2 Dispatcher.
Registers worker instances, tracks runtime types, and monitors active execution loads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("windagent.orchestration.dispatcher.worker_registry")


@dataclass
class WorkerRegistration:
    worker_id: str
    runtime_type: str  # local | hermes | browser | worker
    health: str = "healthy"  # healthy | degraded | unhealthy
    active_leases: int = 0
    last_heartbeat_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, str] = field(default_factory=dict)


class WorkerRegistry:
    def __init__(self):
        self._workers: Dict[str, WorkerRegistration] = {}

    def register(self, worker_id: str, runtime_type: str = "local", metadata: Optional[Dict[str, str]] = None) -> WorkerRegistration:
        reg = WorkerRegistration(
            worker_id=worker_id,
            runtime_type=runtime_type,
            metadata=metadata or {},
        )
        self._workers[worker_id] = reg
        logger.info(f"Registered worker [{worker_id}] with runtime [{runtime_type}]")
        return reg

    def heartbeat(self, worker_id: str, active_leases: int = 0) -> bool:
        worker = self._workers.get(worker_id)
        if not worker:
            self.register(worker_id)
            worker = self._workers[worker_id]

        worker.active_leases = active_leases
        worker.last_heartbeat_at = datetime.now(timezone.utc)
        return True

    def get_healthy_workers(self, runtime_type: Optional[str] = None) -> List[WorkerRegistration]:
        res = [w for w in self._workers.values() if w.health == "healthy"]
        if runtime_type:
            res = [w for w in res if w.runtime_type == runtime_type]
        return res
