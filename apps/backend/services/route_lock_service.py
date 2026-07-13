"""Phase 3 — Route lock and same-model provider failover (ban_ke_hoach §5.3-5.4).

Invariant: once a route lock pins a canonical_model_id, the router NEVER
switches to a different canonical model. Provider may change only among
bindings of that same canonical model.

The router is deliberately dumb:
  1. Resolve canonical model once (or reuse active lock).
  2. Pick best enabled/healthy binding of that canonical model.
  3. Record a route_attempt.
  4. On allowed failure, switch binding, never model.

Cross-model fallback is forbidden by default.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import select

from db.database import Database
from db.models import (
    CanonicalModelORM,
    ProviderModelBindingORM,
    RouteAttemptORM,
    RouteLockORM,
)

log = logging.getLogger(__name__)


class ErrorClass(str, Enum):
    """Error taxonomy driving the §5.4 failure policy."""

    RATE_LIMIT = "rate_limit"          # HTTP 429
    AUTH = "auth"                       # 401/403
    SERVER = "server"                   # 500/502/503
    TIMEOUT_BEFORE_TOKEN = "timeout_before_token"
    STREAM_INTERRUPTED = "stream_interrupted"
    CONTEXT_OVERFLOW = "context_overflow"
    INVALID_TOOL_JSON = "invalid_tool_json"
    MODEL_UNAVAILABLE = "model_unavailable"
    UNKNOWN = "unknown"


def classify_error(exc: BaseException, *, got_first_token: bool = False) -> ErrorClass:
    """Map an exception (and stream state) to an ErrorClass."""
    msg = str(exc).lower()
    if isinstance(exc, ModelResponseError):
        if exc.status_code == 429:
            return ErrorClass.RATE_LIMIT
        if exc.status_code in (401, 403):
            return ErrorClass.AUTH
        if exc.status_code in (500, 502, 503):
            return ErrorClass.SERVER
        if exc.status_code == 429:
            return ErrorClass.RATE_LIMIT
    if isinstance(exc, ModelOfflineError):
        # Distinguish pre-token timeout from mid-stream disconnect by caller.
        return ErrorClass.TIMEOUT_BEFORE_TOKEN if not got_first_token else ErrorClass.STREAM_INTERRUPTED
    if "429" in msg or "rate" in msg or "quota" in msg:
        return ErrorClass.RATE_LIMIT
    if "401" in msg or "403" in msg or "auth" in msg:
        return ErrorClass.AUTH
    if "timeout" in msg:
        return ErrorClass.TIMEOUT_BEFORE_TOKEN if not got_first_token else ErrorClass.STREAM_INTERRUPTED
    if "context" in msg and ("overflow" in msg or "too long" in msg or "exceed" in msg):
        return ErrorClass.CONTEXT_OVERFLOW
    if "tool" in msg and "json" in msg:
        return ErrorClass.INVALID_TOOL_JSON
    if "not found" in msg or "unavailable" in msg or "degraded" in msg:
        return ErrorClass.MODEL_UNAVAILABLE
    return ErrorClass.UNKNOWN


class ModelOfflineError(Exception):
    """Provider unreachable."""


class ModelResponseError(Exception):
    """Provider online but unusable output."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ResolvedBinding:
    canonical_model_id: str
    binding_id: str
    provider_id: str
    provider_model_id: str
    endpoint: Optional[str] = None


@dataclass
class RouteDecision:
    lock_id: str
    canonical_model_id: str
    binding: ResolvedBinding
    attempt_index: int
    attempts: list = field(default_factory=list)


class RouteLockService:
    """Owns route locks, binding selection, and same-model failover."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ---------- lock lifecycle ----------

    async def acquire_lock(
        self,
        *,
        scope_type: str,
        scope_id: str,
        canonical_model_id: str,
        policy_version: Optional[int] = None,
        routing_snapshot: Optional[dict] = None,
    ) -> RouteLockORM:
        """Create (or reuse active) route lock pinning a canonical model."""
        async with self.db.session() as s:
            stmt = select(RouteLockORM).where(
                RouteLockORM.scope_type == scope_type,
                RouteLockORM.scope_id == scope_id,
                RouteLockORM.status == "active",
            )
            existing = (await s.execute(stmt)).scalar_one_or_none()
            if existing:
                # Invariant enforced: must not change canonical model.
                if existing.canonical_model_id != canonical_model_id:
                    raise ValueError(
                        f"route lock {existing.id} already pins "
                        f"{existing.canonical_model_id}; cannot switch to "
                        f"{canonical_model_id}"
                    )
                return existing

            lock = RouteLockORM(
                id=f"rlock_{uuid.uuid4().hex}",
                scope_type=scope_type,
                scope_id=scope_id,
                canonical_model_id=canonical_model_id,
                policy_version=policy_version,
                routing_snapshot_json=__import__("json").dumps(routing_snapshot or {}),
                status="active",
            )
            s.add(lock)
            return lock

    async def get_active_lock(
        self, *, scope_type: str, scope_id: str
    ) -> Optional[RouteLockORM]:
        async with self.db.session() as s:
            stmt = select(RouteLockORM).where(
                RouteLockORM.scope_type == scope_type,
                RouteLockORM.scope_id == scope_id,
                RouteLockORM.status == "active",
            )
            return (await s.execute(stmt)).scalar_one_or_none()

    async def release_lock(self, lock_id: str) -> None:
        async with self.db.session() as s:
            lock = await s.get(RouteLockORM, lock_id)
            if lock:
                lock.status = "released"
                lock.released_at = datetime.now(timezone.utc)

    # ---------- binding selection (same-model only) ----------

    async def select_binding(
        self,
        canonical_model_id: str,
        *,
        exclude: Optional[set[str]] = None,
    ) -> Optional[ResolvedBinding]:
        """Pick best enabled/healthy binding for the canonical model.

        Binds to one canonical model only. Never returns a binding for a
        different model. Cooled-down bindings are skipped.
        """
        exclude = exclude or set()
        async with self.db.session() as s:
            stmt = (
                select(ProviderModelBindingORM)
                .join(
                    CanonicalModelORM,
                    ProviderModelBindingORM.canonical_model_id == CanonicalModelORM.id,
                )
                .where(
                    CanonicalModelORM.id == canonical_model_id,
                    ProviderModelBindingORM.enabled == True,  # noqa: E712
                )
                .order_by(ProviderModelBindingORM.priority.desc())
            )
            rows = (await s.execute(stmt)).scalars().all()

        now = datetime.now(timezone.utc)
        for b in rows:
            if b.id in exclude:
                continue
            # Skip cooled-down bindings.
            if b.cooldown_until and b.cooldown_until > now:
                continue
            if b.health == "disabled":
                continue
            return ResolvedBinding(
                canonical_model_id=canonical_model_id,
                binding_id=b.id,
                provider_id=b.provider_id,
                provider_model_id=b.provider_model_id,
                endpoint=b.endpoint,
            )
        return None

    # ---------- attempt recording ----------

    async def open_attempt(
        self,
        *,
        lock_id: str,
        binding_id: Optional[str],
        agent_session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        attempt_index: int = 0,
    ) -> RouteAttemptORM:
        async with self.db.session() as s:
            attempt = RouteAttemptORM(
                route_lock_id=lock_id,
                provider_binding_id=binding_id,
                agent_session_id=agent_session_id,
                turn_id=turn_id,
                attempt_index=attempt_index,
                status="inflight",
            )
            s.add(attempt)
            return attempt

    async def close_attempt(
        self,
        attempt_id: int,
        *,
        status: str,
        error_class: Optional[str] = None,
        http_status: Optional[int] = None,
        first_token_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        partial_artifact_id: Optional[str] = None,
    ) -> None:
        async with self.db.session() as s:
            attempt = await s.get(RouteAttemptORM, attempt_id)
            if not attempt:
                return
            attempt.status = status
            if error_class is not None:
                attempt.error_class = error_class
            if http_status is not None:
                attempt.http_status = http_status
            if first_token_at is not None:
                attempt.first_token_at = first_token_at
            attempt.finished_at = finished_at or datetime.now(timezone.utc)
            attempt.prompt_tokens = prompt_tokens
            attempt.completion_tokens = completion_tokens
            attempt.partial_artifact_id = partial_artifact_id

    async def mark_binding_cooldown(self, binding_id: str, cooldown_seconds: int = 30) -> None:
        """Cool down a binding after 429/quota exhaustion."""
        # ponytail: naive fixed cooldown; replace with exponential backoff if needed.
        from datetime import timedelta

        async with self.db.session() as s:
            b = await s.get(ProviderModelBindingORM, binding_id)
            if b:
                b.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
                if b.health != "disabled":
                    b.health = "degraded"

    async def disable_binding(self, binding_id: str) -> None:
        """Disable a binding permanently (401/403 bad credential)."""
        async with self.db.session() as s:
            b = await s.get(ProviderModelBindingORM, binding_id)
            if b:
                b.enabled = False
                b.health = "disabled"


def should_switch_provider(error_class: ErrorClass) -> bool:
    """§5.4 policy: which errors allow same-model provider switch."""
    return error_class in {
        ErrorClass.RATE_LIMIT,
        ErrorClass.AUTH,
        ErrorClass.SERVER,
        ErrorClass.TIMEOUT_BEFORE_TOKEN,
        ErrorClass.STREAM_INTERRUPTED,
        ErrorClass.MODEL_UNAVAILABLE,
    }


def retry_same_provider(error_class: ErrorClass) -> bool:
    """§5.4: 500/502/503 retry once on same provider before switching."""
    return error_class == ErrorClass.SERVER


def is_exhausted(error_class: ErrorClass) -> bool:
    """When all same-model bindings are dead and we must stop."""
    return error_class in {
        ErrorClass.CONTEXT_OVERFLOW,
        ErrorClass.INVALID_TOOL_JSON,
    }
