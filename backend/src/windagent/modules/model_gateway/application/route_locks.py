"""Route lock service: the single durable authority for model selection.

REWRITE of the frozen ``routing/route_lock_service.py``.  Preserved
semantics: fast-path read of the scope's active lock, fail-closed rule
resolution (no random model ever), race-safe lock creation (the durable
single-active-lock constraint arbitrates), explicit reselection, and
model-level fallback as a SEPARATE pinned lock so the primary decision is
never mutated.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from windagent.kernel.time import Clock, SystemClock

from ..domain.errors import (
    CanonicalModelDisabledError,
    ModelGatewayValidationError,
    NoMatchingRuleError,
    RouteLockNotFoundError,
)
from ..domain.route_lock import VALID_SCOPE_TYPES, LockStatus, RouteLockRecord, RoutingSnapshot
from ..domain.rules import RoutingRuleSet, RuleMatchContext, RuleMatcher
from . import events as route_events
from .models import RuleRow
from .ports import TransactionScope


class RouteLockService:
    """Resolves, creates, releases, and replaces route locks."""

    def __init__(
        self,
        *,
        scope_factory: Callable[[], TransactionScope],
        clock: Clock | None = None,
        matcher: RuleMatcher | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._clock: Clock = clock or SystemClock()
        self._matcher = matcher or RuleMatcher()

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #

    async def current_ruleset(self) -> RoutingRuleSet:
        """Load the enabled durable rules into a domain ruleset."""
        rows: tuple[RuleRow, ...] = ()
        async with self._scope_factory() as scope:
            rows = await scope.store().list_rules()
        return RoutingRuleSet(rules=tuple(row.to_domain_rule() for row in rows))

    async def resolve_or_create_lock(self, context: RuleMatchContext) -> RouteLockRecord:
        """Return the scope's active lock, or resolve and pin a new one."""
        scope_type, scope_id = _validated_scope(context)
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_active_route_lock(scope_type, scope_id)
            if existing is not None:
                await scope.record_event(route_events.route_reused(existing))
                await scope.commit()
                return existing

            ruleset = await self.current_ruleset()
            rule = self._matcher.find_first_match(ruleset, context)
            if rule is None:
                raise NoMatchingRuleError(
                    "no enabled routing rule matches the request context",
                    context={
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "agent_type": context.agent_type,
                        "workflow_type": context.workflow_type,
                    },
                )
            model = await store.get_model(rule.canonical_model_id)
            if model is not None and not model.enabled:
                raise CanonicalModelDisabledError(
                    f"canonical model {rule.canonical_model_id!r} is disabled",
                    context={
                        "canonical_model_id": rule.canonical_model_id,
                        "rule_id": rule.rule_id,
                    },
                )

            now = self._clock.now().timestamp()
            lock = RouteLockRecord(
                lock_id=str(uuid4()),
                scope_type=scope_type,
                scope_id=scope_id,
                canonical_model_id=rule.canonical_model_id,
                routing_snapshot=RoutingSnapshot(
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    canonical_model_id=rule.canonical_model_id,
                    selected_at=now,
                    reason=rule.description or f"matched rule {rule.rule_id}",
                ),
                created_at=now,
            )
            created = await store.record_route_lock(lock)
            if not created:
                # A concurrent writer won the single-active-lock race; the
                # existing lock is authoritative (old fast-path semantics).
                winner = await store.get_active_route_lock(scope_type, scope_id)
                if winner is None:  # pragma: no cover - constraint guarantees one
                    raise NoMatchingRuleError(
                        "route lock creation raced and no active lock remains",
                        context={"scope_type": scope_type, "scope_id": scope_id},
                    )
                await scope.commit()
                return winner

            await scope.record_event(route_events.route_locked(lock))
            await scope.commit()
        return lock

    async def create_fallback_lock(
        self,
        *,
        scope_type: str,
        scope_id: str,
        canonical_model_id: str,
        reason: str,
        source_lock_id: str,
    ) -> RouteLockRecord:
        """Pin a separate fallback lock (P0.3.5); the primary stays active."""
        if scope_type not in VALID_SCOPE_TYPES:
            raise ModelGatewayValidationError(
                f"invalid lock scope type: {scope_type!r}",
                context={"scope_type": scope_type},
            )
        now = self._clock.now().timestamp()
        lock = RouteLockRecord(
            lock_id=str(uuid4()),
            scope_type=scope_type,
            scope_id=scope_id,
            canonical_model_id=canonical_model_id,
            routing_snapshot=RoutingSnapshot(
                rule_id="fallback",
                rule_version=0,
                canonical_model_id=canonical_model_id,
                selected_at=now,
                reason=reason,
            ),
            created_at=now,
            is_fallback=True,
            source_lock_id=source_lock_id,
        )
        async with self._scope_factory() as scope:
            store = scope.store()
            await store.record_route_lock(lock)
            await scope.record_event(
                route_events.route_fallback_created(lock, source_lock_id=source_lock_id)
            )
            await scope.commit()
        return lock

    async def release_lock(self, lock_id: str) -> RouteLockRecord:
        """Release an active lock; releasing twice is an error."""
        async with self._scope_factory() as scope:
            store = scope.store()
            lock = await store.get_route_lock(lock_id)
            if lock is None or lock.status != LockStatus.ACTIVE.value:
                raise RouteLockNotFoundError(
                    f"route lock {lock_id!r} not found or already released",
                    context={"lock_id": lock_id},
                )
            released = await store.release_route_lock(lock_id, when=self._clock.now())
            if not released:  # pragma: no cover - guarded by the read above
                raise RouteLockNotFoundError(
                    f"route lock {lock_id!r} not found or already released",
                    context={"lock_id": lock_id},
                )
            released_lock = RouteLockRecord(
                lock_id=lock.lock_id,
                scope_type=lock.scope_type,
                scope_id=lock.scope_id,
                canonical_model_id=lock.canonical_model_id,
                routing_snapshot=lock.routing_snapshot,
                status=LockStatus.RELEASED.value,
                created_at=lock.created_at,
                released_at=self._clock.now().timestamp(),
                reselection_count=lock.reselection_count,
                is_fallback=lock.is_fallback,
                source_lock_id=lock.source_lock_id,
            )
            await scope.record_event(route_events.route_released(released_lock))
            await scope.commit()
        return released_lock

    async def reselect_model(
        self,
        *,
        scope_type: str,
        scope_id: str,
        new_context: RuleMatchContext,
        reason: str = "explicit_reselection",
    ) -> RouteLockRecord:
        """Release the scope's active lock and pin a new decision."""
        active = await self.get_active_lock(scope_type, scope_id)
        if active is None:
            raise RouteLockNotFoundError(
                f"no active route lock for scope {scope_type}/{scope_id}",
                context={"scope_type": scope_type, "scope_id": scope_id},
            )
        await self.release_lock(active.lock_id)
        replacement = await self.resolve_or_create_lock(new_context)
        async with self._scope_factory() as scope:
            await scope.record_event(
                route_events.model_reselected(replacement, reason=reason)
            )
            await scope.commit()
        return replacement

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    async def get_lock(self, lock_id: str) -> RouteLockRecord | None:
        """Fetch one lock by id."""
        lock: RouteLockRecord | None = None
        async with self._scope_factory() as scope:
            lock = await scope.store().get_route_lock(lock_id)
        return lock

    async def get_active_lock(self, scope_type: str, scope_id: str) -> RouteLockRecord | None:
        """Fetch the scope's active lock, if any."""
        scope_type, scope_id = _validated_scope(
            RuleMatchContext(scope_type=scope_type, scope_id=scope_id)
        )
        lock: RouteLockRecord | None = None
        async with self._scope_factory() as scope:
            lock = await scope.store().get_active_route_lock(scope_type, scope_id)
        return lock


def _validated_scope(context: RuleMatchContext) -> tuple[str, str]:
    scope_type = (context.scope_type or "session").strip()
    scope_id = (context.scope_id or "").strip()
    if not scope_id:
        raise ModelGatewayValidationError(
            "scope_id cannot be empty", context={"scope_type": scope_type}
        )
    if scope_type not in VALID_SCOPE_TYPES:
        raise ModelGatewayValidationError(
            f"invalid lock scope type: {scope_type!r}",
            context={"scope_type": scope_type},
        )
    return scope_type, scope_id
