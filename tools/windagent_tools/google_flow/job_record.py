"""
Phase 14 — Durable generation job record + reconciliation (plan 04 §18.2).

A `FlowJobRecord` is persisted BEFORE the submit click (plan 04 §18.2:
"record action/job before or atomically with submit intent"). Crash recovery
and repeated commands reconcile against the registry and NEVER blind-resubmit:

    lookup request_hash + provider + project mapping
    ├── COMPLETED                → reuse candidate set
    ├── active (SUBMITTING/GENERATING/RESULT_READY/DOWNLOADING) → inspect/resume
    ├── UNKNOWN / terminal       → reconcile, never blind resubmit
    ├── failed retryable + budget → new attempt (attempt+1, parent link)
    └── missing                  → create PREPARED record

Statuses follow plan 04 §22 (durable job model).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence


class FlowJobStatus(str, Enum):
    PREPARED = "PREPARED"
    SUBMITTING = "SUBMITTING"
    GENERATING = "GENERATING"
    RESULT_READY = "RESULT_READY"
    DOWNLOADING = "DOWNLOADING"
    COMPLETED = "COMPLETED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    UNKNOWN_REQUIRES_RECONCILIATION = "UNKNOWN_REQUIRES_RECONCILIATION"
    HUMAN_ACTION_REQUIRED = "HUMAN_ACTION_REQUIRED"
    CANCELLED = "CANCELLED"


_ACTIVE_STATUSES = frozenset(
    {
        FlowJobStatus.SUBMITTING,
        FlowJobStatus.GENERATING,
        FlowJobStatus.RESULT_READY,
        FlowJobStatus.DOWNLOADING,
    }
)


class FlowReconcileAction(str, Enum):
    REUSE_COMPLETED = "REUSE_COMPLETED"
    RESUME_ACTIVE = "RESUME_ACTIVE"
    NEW_ATTEMPT = "NEW_ATTEMPT"
    CREATE_PREPARED = "CREATE_PREPARED"
    RECONCILE_UNKNOWN = "RECONCILE_UNKNOWN"  # never blind resubmit


@dataclass(frozen=True)
class FlowJobRecord:
    """Durable job record (plan 04 §22 shape, Phase 14 subset)."""

    generation_id: str
    project_id: str
    revision_id: str
    shot_id: str = ""
    provider: str = "google_flow_browser"
    request_hash: str = ""
    submitted_at: float = 0.0
    browser_session_id: str = ""
    flow_project_id: str = ""
    status: FlowJobStatus = FlowJobStatus.PREPARED
    attempt: int = 1
    parent_generation_id: str = ""  # causal link (re-generation, §18.4)
    candidate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            object.__setattr__(self, "status", FlowJobStatus(self.status))
        if isinstance(self.candidate_ids, list):
            object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "shot_id": self.shot_id,
            "provider": self.provider,
            "request_hash": self.request_hash,
            "submitted_at": self.submitted_at,
            "browser_session_id": self.browser_session_id,
            "flow_project_id": self.flow_project_id,
            "status": self.status.value,
            "attempt": self.attempt,
            "parent_generation_id": self.parent_generation_id,
            "candidate_ids": list(self.candidate_ids),
        }

    @property
    def active(self) -> bool:
        return self.status in _ACTIVE_STATUSES


@dataclass(frozen=True)
class FlowReconcileDecision:
    """Outcome of a job lookup (plan 04 §18.2 / §23.1 reconciliation)."""

    action: FlowReconcileAction
    record: Optional[FlowJobRecord] = None
    reason: str = ""


class FlowJobRegistry:
    """JSON-persisted job registry with fail-closed reconciliation."""

    def __init__(
        self,
        *,
        state_dir: str,
        clock: Optional[callable] = None,
        retry_budget: int = 3,
    ) -> None:
        self._state_dir = Path(state_dir).resolve()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock or time.time
        self._retry_budget = retry_budget
        self._path = self._state_dir / "flow_jobs.json"
        self._jobs: dict[str, dict] = self._load()

    @property
    def state_dir(self) -> Path:
        """Directory shared by durable Flow coordination records."""
        return self._state_dir

    # ------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._jobs, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def _store(self, record: FlowJobRecord) -> FlowJobRecord:
        self._jobs[record.generation_id] = record.to_dict()
        self._save()
        return record

    def get(self, generation_id: str) -> Optional[FlowJobRecord]:
        raw = self._jobs.get(generation_id)
        return FlowJobRecord(**raw) if raw else None

    def list_records(self) -> list[FlowJobRecord]:
        return [
            FlowJobRecord(**raw)
            for raw in sorted(
                self._jobs.values(), key=lambda r: r.get("submitted_at", 0.0)
            )
        ]

    # ------------------------------------------------------------------
    def reconcile(
        self,
        *,
        request_hash: str,
        project_id: str,
        provider: str,
    ) -> FlowReconcileDecision:
        """Look up the latest job for the idempotency key (request_hash +
        provider + project) and decide what to do (plan 04 §18.2/§23.1)."""
        candidates = [
            r for r in self.list_records()
            if r.request_hash == request_hash
            and r.project_id == project_id
            and r.provider == provider
        ]
        if not candidates:
            return FlowReconcileDecision(
                FlowReconcileAction.CREATE_PREPARED,
                reason="no prior job for idempotency key",
            )
        latest = candidates[-1]

        if latest.status == FlowJobStatus.COMPLETED:
            return FlowReconcileDecision(
                FlowReconcileAction.REUSE_COMPLETED,
                latest,
                "completed job reused (candidate set intact)",
            )
        if latest.active:
            return FlowReconcileDecision(
                FlowReconcileAction.RESUME_ACTIVE,
                latest,
                f"active job {latest.status.value} inspected/resumed",
            )
        if latest.status == FlowJobStatus.FAILED_RETRYABLE:
            if latest.attempt < self._retry_budget:
                return FlowReconcileDecision(
                    FlowReconcileAction.NEW_ATTEMPT,
                    latest,
                    f"retryable failure; attempt {latest.attempt + 1} allowed",
                )
            return FlowReconcileDecision(
                FlowReconcileAction.RECONCILE_UNKNOWN,
                latest,
                f"retry budget exhausted (attempt {latest.attempt})",
            )
        # UNKNOWN / terminal / human / cancelled → never blind resubmit
        return FlowReconcileDecision(
            FlowReconcileAction.RECONCILE_UNKNOWN,
            latest,
            f"non-retryable status {latest.status.value}",
        )

    # ------------------------------------------------------------------
    def create_prepared(
        self,
        *,
        generation_id: str,
        project_id: str,
        revision_id: str,
        shot_id: str = "",
        provider: str = "google_flow_browser",
        request_hash: str = "",
        browser_session_id: str = "",
        flow_project_id: str = "",
        parent_generation_id: str = "",
    ) -> FlowJobRecord:
        return self._store(
            FlowJobRecord(
                generation_id=generation_id,
                project_id=project_id,
                revision_id=revision_id,
                shot_id=shot_id,
                provider=provider,
                request_hash=request_hash,
                submitted_at=self._clock(),
                browser_session_id=browser_session_id,
                flow_project_id=flow_project_id,
                status=FlowJobStatus.PREPARED,
                attempt=1,
                parent_generation_id=parent_generation_id,
            )
        )

    def mark(self, generation_id: str, status: FlowJobStatus) -> FlowJobRecord:
        record = self.get(generation_id)
        if record is None:
            raise KeyError(f"unknown generation {generation_id}")
        updated = FlowJobRecord(
            **{**record.to_dict(), "status": status.value}
        )
        return self._store(updated)

    def next_attempt(
        self, generation_id: str, *, reason: str = ""
    ) -> FlowJobRecord:
        """New attempt with attempt+1 and a causal parent link (§18.4)."""
        record = self.get(generation_id)
        if record is None:
            raise KeyError(f"unknown generation {generation_id}")
        updated = FlowJobRecord(
            **{
                **record.to_dict(),
                "generation_id": f"{record.generation_id}a{record.attempt + 1}",
                "status": FlowJobStatus.PREPARED.value,
                "attempt": record.attempt + 1,
                "parent_generation_id": record.generation_id,
                "submitted_at": self._clock(),
            }
        )
        return self._store(updated)

    def record_candidates(
        self, generation_id: str, candidate_ids: Sequence[str]
    ) -> FlowJobRecord:
        record = self.get(generation_id)
        if record is None:
            raise KeyError(f"unknown generation {generation_id}")
        updated = FlowJobRecord(
            **{
                **record.to_dict(),
                "status": FlowJobStatus.COMPLETED.value,
                "candidate_ids": list(candidate_ids),
            }
        )
        return self._store(updated)


__all__ = [
    "FlowJobRecord",
    "FlowJobRegistry",
    "FlowJobStatus",
    "FlowReconcileAction",
    "FlowReconcileDecision",
]
