"""Durable checkpoints for hardened long-running agents (Phase 5).

Covers all mandated boundaries from ban_ke_hoach_v1 §10:

  turn_boundary
  tool_boundary
  child_admission
  child_completion
  compaction
  external_wait
  terminal_state

plus manual/auto convenience kinds. A checkpoint is an opaque
JSON-serializable snapshot stored atomically with the owning
AgentLoop state's version. Host-authority fields are forbidden
exactly as in stateful_runtime (never persisted).

Domain is pure — zero storage/provider/orchestration imports.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


HOST_FORBIDDEN_KEYS = frozenset({
    "provider_credentials",
    "credentials",
    "credential",
    "api_key",
    "apikey",
    "secret",
    "secrets",
    "provider_call",
    "provider_routing",
    "provider_token",
    "schedule",
    "scheduling",
    "memory_write",
    "memory_writes",
    "learning_promotion",
    "promotion",
    "host_authority",
    "authority",
    "session_lifecycle_authority",
    "privileged",
    "password",
    "auth_token",
})


def _contains_forbidden(obj: Any, depth: int = 0) -> Optional[str]:
    if depth > 10:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in HOST_FORBIDDEN_KEYS:
                return str(k)
            inner = _contains_forbidden(v, depth + 1)
            if inner:
                return inner
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            inner = _contains_forbidden(item, depth + 1)
            if inner:
                return inner
    return None


def assert_no_host_authority(payload: Optional[Dict[str, Any]], context: str = "payload") -> None:
    if not payload:
        return
    off = _contains_forbidden(payload)
    if off:
        raise ValueError(
            f"Host authority field '{off}' is not allowed in {context}; "
            "checkpoints must remain substrate-only and never capture credentials/routing/schedule/memory/promotion."
        )


def sanitize_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-copy stripping any forbidden keys (defense-in-depth)."""
    cleaned = copy.deepcopy(snapshot)

    def _strip(d: Any) -> Any:
        if isinstance(d, dict):
            out: Dict[str, Any] = {}
            for kk, vv in d.items():
                if str(kk).lower() in HOST_FORBIDDEN_KEYS:
                    continue
                out[kk] = _strip(vv)
            return out
        if isinstance(d, list):
            return [_strip(x) for x in d]
        return d

    return _strip(cleaned)


def ensure_json_serializable(obj: Any, context: str = "checkpoint snapshot") -> None:
    try:
        json.dumps(obj)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be JSON-serializable (opaque): {exc}") from exc


class CheckpointKind(str, Enum):
    TURN_BOUNDARY = "turn_boundary"
    TOOL_BOUNDARY = "tool_boundary"
    CHILD_ADMISSION = "child_admission"
    CHILD_COMPLETION = "child_completion"
    COMPACTION = "compaction"
    EXTERNAL_WAIT = "external_wait"
    TERMINAL_STATE = "terminal_state"
    MANUAL = "manual"
    AUTO = "auto"


ALL_CHECKPOINT_KINDS: List[str] = [k.value for k in CheckpointKind]


class DurableCheckpoint(BaseModel):
    checkpoint_id: str = Field(min_length=1)
    agent_run_id: str = Field(min_length=1)
    session_id: Optional[str] = Field(default=None)
    kind: CheckpointKind = Field(default=CheckpointKind.MANUAL)
    step_run_id: Optional[str] = Field(default=None)
    tool_name: Optional[str] = Field(default=None)
    fencing_token: str = Field(default="")
    snapshot: Dict[str, Any] = Field(default_factory=dict)
    sequence: int = Field(default=0, ge=0)
    loop_version_at_checkpoint: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(frozen=True, extra="forbid")

    def validate_snapshot(self) -> None:
        assert_no_host_authority(self.snapshot, "snapshot")
        ensure_json_serializable(self.snapshot, "checkpoint snapshot")


__all__ = [
    "CheckpointKind",
    "ALL_CHECKPOINT_KINDS",
    "DurableCheckpoint",
    "HOST_FORBIDDEN_KEYS",
    "assert_no_host_authority",
    "sanitize_snapshot",
    "ensure_json_serializable",
]
