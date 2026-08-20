"""Typed execution context for the Production Worker pipeline (Architecture V3 Phase 9).

``TaskExecutionContext`` is the single normalized carrier for one claimed task
through every pipeline stage.  It is created by the claim stage from either a
durable queue object claim (``ClaimedTask``) or a legacy dict claim, and it
carries the exact lease identity (lease id + generation + fencing token) so
later stages never have to re-derive lease identity from cleared Worker fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from windagent_core.domain.types import TaskId


@dataclass
class TaskExecutionContext:
    """Normalized per-task state flowing through the worker pipeline stages.

    Fields:
    - canonical and raw task id;
    - worker id;
    - fencing token;
    - exact lease id and lease generation;
    - attempt / attempt id;
    - tool name, prompt, parameters;
    - runtime handle and result slots;
    - claimed/start/execution-finished/finalized timestamps;
    - redaction-safe per-task metric state.
    """

    task_id: str
    raw_task_id: str
    worker_id: str
    fencing_token: str
    lease_id: str
    lease_generation: int
    attempt: int = 1
    attempt_id: str = "att_1"
    tool_name: str = "read_file"
    prompt: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    handle: Optional[Any] = None
    result: Optional[Any] = None
    claimed_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    execution_finished_at: Optional[datetime] = None
    finalized_at: Optional[datetime] = None
    metric: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_claim(cls, claimed: Any, worker_id: str) -> "TaskExecutionContext":
        """Normalize an object claim or a legacy dict claim exactly as today.

        Object claims (``ClaimedTask``) expose attributes; legacy dict claims
        fall back to deterministic task-ID-derived values for lease identity
        (generation 1) for compatibility.  Lease identity is captured here and
        never re-derived later from cleared Worker fields.
        """
        if hasattr(claimed, "task_id"):
            raw_tid = str(claimed.task_id)
            fencing_token = claimed.fencing_token
            lease_id = claimed.lease_id
            lease_generation = claimed.lease_generation
            tool_name = claimed.tool_name
            prompt = claimed.prompt
            parameters = claimed.parameters
            claimed_at = getattr(claimed, "acquired_at", None)
        else:
            raw_tid = str(claimed["task_id"])
            fencing_token = claimed.get("fencing_token", f"fence_{raw_tid}_gen_1")
            # Legacy dict claims may omit lease identity; fall back to a
            # deterministic task-ID-derived value (generation 1) for
            # compatibility. Never read an in-memory field that was already
            # cleared to None.
            lease_id = claimed.get("lease_id", f"lease_{raw_tid}")
            lease_generation = claimed.get("lease_generation", 1)
            tool_name = claimed.get("tool_name", "read_file")
            prompt = claimed.get("prompt", "")
            parameters = claimed.get("parameters", {})
            claimed_at = claimed.get("acquired_at", None)

        try:
            tid = str(TaskId(raw_tid))
        except Exception:
            tid = raw_tid

        # ``attempt`` is typed as an integer; coerce legacy string/numeric
        # claim payloads so the metric/attempt contract stays integer-typed
        # while remaining compatible with existing claims.
        raw_attempt = parameters.get("attempt", 1)
        try:
            attempt = int(raw_attempt)
        except (TypeError, ValueError):
            attempt = 1

        return cls(
            task_id=tid,
            raw_task_id=raw_tid,
            worker_id=worker_id,
            fencing_token=fencing_token,
            lease_id=lease_id,
            lease_generation=lease_generation,
            attempt=attempt,
            attempt_id="att_1",
            tool_name=tool_name,
            prompt=prompt,
            parameters=parameters,
            claimed_at=claimed_at,
        )


__all__ = ["TaskExecutionContext"]