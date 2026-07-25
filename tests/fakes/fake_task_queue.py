"""Fake Task Queue for Unit Tests (Phase 3)."""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional

from windagent_core.contracts.workers.queue import ClaimedTask, DurableTaskQueuePort
from windagent_core.contracts.workers.leases import TaskLeasePort


class FakeDurableTaskQueue(DurableTaskQueuePort, TaskLeasePort):
    """In-memory task queue fake for unit tests."""

    def __init__(self) -> None:
        self.pending_tasks: List[Dict[str, Any]] = []
        self.active_claims: Dict[str, ClaimedTask] = {}
        self.released_tasks: List[str] = []

    def submit_fake_task(self, task_id: str, prompt: str, tool_name: str = "read_file", parameters: Optional[Dict[str, Any]] = None) -> str:
        self.pending_tasks.append({
            "task_id": task_id,
            "prompt": prompt,
            "tool_name": tool_name,
            "parameters": parameters or {},
        })
        return task_id

    async def claim_next(self, worker_id: str, lease_ttl_seconds: int = 30) -> Optional[ClaimedTask]:
        if not self.pending_tasks:
            return None

        task_data = self.pending_tasks.pop(0)
        raw_tid = task_data["task_id"]
        fencing_token = f"fence_{raw_tid}_gen_1_{uuid.uuid4().hex[:4]}"
        lease_id = f"lease_{raw_tid}_1"

        claimed = ClaimedTask(
            task_id=raw_tid,
            worker_id=worker_id,
            lease_id=lease_id,
            fencing_token=fencing_token,
            lease_generation=1,
            tool_name=task_data["tool_name"],
            prompt=task_data["prompt"],
            parameters=task_data["parameters"],
        )
        self.active_claims[raw_tid] = claimed
        return claimed

    async def renew(self, task_id: str, worker_id: str, fencing_token: str, extension_seconds: int = 30) -> bool:
        if task_id in self.active_claims and self.active_claims[task_id].fencing_token == fencing_token:
            return True
        return False

    async def release(self, task_id: str, worker_id: str, fencing_token: str) -> bool:
        if task_id in self.active_claims:
            del self.active_claims[task_id]
            self.released_tasks.append(task_id)
            return True
        return False

    async def fail(self, task_id: str, worker_id: str, fencing_token: str, error: str) -> bool:
        if task_id in self.active_claims:
            del self.active_claims[task_id]
            return True
        return False
