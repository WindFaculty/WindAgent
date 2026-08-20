"""
RouteLockService — Phase 1 durable route lock authority.

Responsibilities
----------------
1. Resolve or create a route lock for a (scope_type, scope_id) pair.
   - If an active lock exists in the repository → reuse it (RouteReused event).
   - If no lock exists → evaluate rules → atomically create lock (RouteLocked).
2. Explicit unlock (RouteReleased event).
3. Explicit model reselection: release old lock, create new lock
   (ModelReselectionRequested + ModelReselected events) + durable audit.
4. Failover: when an endpoint errors, the same canonical model is retained and
   only the endpoint/binding changes — the lock's canonical_model_id NEVER changes.

Cross-process authority
-----------------------
When a ``RouteLockRepositoryPort`` is injected, the repository is the single
source of truth. The atomic ``create_lock`` prevents duplicate active locks
across API + Worker + replicas (ban_ke_hoach.md §1.4 / §1.5).  Without an
injected repository the service falls back to an in-memory store (dev/test
only, NON-durable, single process).

Key invariants (validated in tests)
------------------------------------
* One active lock per scope_id (enforced by repository + create-or-reuse).
* 100+ turns on the same session all return the same canonical_model_id.
* Concurrent first requests → only one lock created (DB unique / in-memory lock).
* Process-restart simulation: read existing lock from repository.
* Rule update after lock creation → lock unchanged.
* No silent fallback to another model.
* Reselection always emits ModelReselectionRequested + ModelReselected + audit.
"""

from __future__ import annotations

import threading
import time
import logging
import warnings
from typing import Any, Callable, Dict, List, Optional

from windagent_providers.routing.events import (
    ModelReselected,
    ModelReselectionRequested,
    ModelSelected,
    RouteLocked,
    RouteReleased,
    RouteReused,
    RoutingEvent,
)
from windagent_providers.routing.route_lock import (
    LockStatus,
    RouteLockRecord,
)
from windagent_providers.routing.rule_matcher import RuleMatchContext, RuleMatcher
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
from windagent_providers.routing.ports import (
    RouteLockRepositoryPort,
    RoutingAuditRepositoryPort,
)

logger = logging.getLogger("windagent.providers.routing")


class NoMatchingRuleError(Exception):
    """Raised when no enabled rule matches the given context."""

    def __init__(self, scope_id: str, scope_type: str):
        super().__init__(f"No routing rule matched for scope={scope_type}:{scope_id}")
        self.scope_id = scope_id
        self.scope_type = scope_type


class CanonicalModelDisabledError(Exception):
    """Raised when the canonical model selected by a rule is disabled."""

    def __init__(self, canonical_model_id: str):
        super().__init__(
            f"Canonical model '{canonical_model_id}' is disabled and cannot be locked"
        )
        self.canonical_model_id = canonical_model_id


class LockNotFoundError(Exception):
    """Raised when an operation targets a lock_id that does not exist."""

    def __init__(self, lock_id: str):
        super().__init__(f"Lock '{lock_id}' not found")
        self.lock_id = lock_id


class RouteLockService:
    """
    Thread-safe Route Lock Service with optional durable repository.

    Parameters
    ----------
    ruleset           : The active RoutingRuleSet.
    matcher           : Optional RuleMatcher (default-constructed if not provided).
    disabled_models   : Set of canonical model IDs that are currently disabled.
    lock_repository   : Optional RouteLockRepositoryPort (durable store). If omitted,
                        an in-memory store is used (dev/test only).
    audit_repository  : Optional RoutingAuditRepositoryPort (durable audit trail).
    attempt_repository: Optional RouteAttemptRepositoryPort (durable failover tracking).
    event_handler     : Optional callback ``(RoutingEvent) -> None`` invoked
                        synchronously after each state-change event.
    """

    def __init__(
        self,
        ruleset: Optional[RoutingRuleSet] = None,
        matcher: Optional[RuleMatcher] = None,
        disabled_models: Optional[set] = None,
        lock_repository: Optional[RouteLockRepositoryPort] = None,
        audit_repository: Optional[RoutingAuditRepositoryPort] = None,
        attempt_repository: Optional[Any] = None,
        event_handler: Optional[Callable[[RoutingEvent], None]] = None,
    ):
        self._ruleset = ruleset or RoutingRuleSet()
        self._matcher: RuleMatcher = matcher or RuleMatcher()
        self._disabled_models: set = disabled_models or set()
        self._event_handler = event_handler
        self._lock_repo = lock_repository
        self._audit_repo = audit_repository
        self._attempt_repo = attempt_repository
        #: Durability is decided by injection: a lock repository was composed
        #: (cross-process durable) vs. the in-memory dev/test fallback. A
        #: repository may declare ``durable = False`` (test fakes); never
        #: derived from module identity or test imports.
        self._durable = lock_repository is not None and bool(
            getattr(lock_repository, "durable", True)
        )
        if self._lock_repo is None:
            warnings.warn(
                "RouteLockService running IN-MEMORY (dev/test only). "
                "Inject RouteLockRepositoryPort for cross-process durability.",
                stacklevel=2,
            )
            from tests.fakes.routing_fakes import InMemoryLockStore
            self._lock_repo = InMemoryLockStore()

        # Per-scope creation locks to avoid thundering herd (in-memory only helps
        # within a single process; cross-process safety comes from repo.create_lock).
        self._scope_creation_locks: Dict[str, threading.Lock] = {}
        self._scope_creation_locks_mutex = threading.Lock()

        # In-memory event log for test verification (events are NOT the authority).
        self._event_log: List[RoutingEvent] = []
        self._mutex = threading.RLock()

    @property
    def is_durable(self) -> bool:
        return self._durable

    @property
    def current_ruleset(self) -> RoutingRuleSet:
        """Return the currently active ruleset (the rebuildable runtime projection)."""
        with self._mutex:
            return self._ruleset

    def record_attempt(
        self,
        lock_id: str,
        endpoint_id: Optional[str],
        provider_model_id: Optional[str],
        attempt_number: int,
        status: str,
        failure_category: Optional[str] = None,
        retry_after: Optional[float] = None,
    ) -> Dict[str, Any]:
        if self._attempt_repo is not None:
            return self._attempt_repo.record_attempt(
                lock_id=lock_id,
                endpoint_id=endpoint_id,
                provider_model_id=provider_model_id,
                attempt_number=attempt_number,
                status=status,
                failure_category=failure_category,
                retry_after=retry_after,
            )
        return {"lock_id": lock_id, "status": status, "failure_category": failure_category}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def resolve_or_create_lock(self, context: RuleMatchContext) -> RouteLockRecord:
        scope_key = self._scope_key(context.scope_type, context.scope_id)

        # Fast path: read active lock from repository
        existing = self._repo_get_active(scope_key)
        if existing:
            self._emit_reuse_event(existing, context)
            return existing

        scope_lock = self._get_scope_creation_lock(scope_key)
        with scope_lock:
            existing = self._repo_get_active(scope_key)
            if existing:
                self._emit_reuse_event(existing, context)
                return existing
            return self._create_new_lock(context, scope_key, reselection=False)

    def release_lock(self, lock_id: str) -> RouteLockRecord:
        with self._mutex:
            record = self._repo_get_by_id(lock_id)
            if record is None:
                raise LockNotFoundError(lock_id)
            if record.status == LockStatus.RELEASED.value:
                raise LockNotFoundError(lock_id)

        released = self._lock_repo.release_lock(lock_id)
        if not released:
            raise LockNotFoundError(lock_id)

        record.status = LockStatus.RELEASED.value
        record.released_at = time.time()
        event = RouteReleased(
            scope_id=record.scope_id,
            scope_type=record.scope,
            lock_id=record.lock_id,
            canonical_model_id=record.canonical_model_id,
        )
        self._emit(event)
        return record

    def reselect_model(
        self,
        scope_type: str,
        scope_id: str,
        new_context: RuleMatchContext,
        reason: str = "explicit_reselection",
    ) -> RouteLockRecord:
        scope_key = self._scope_key(scope_type, scope_id)
        with self._mutex:
            old_record = self._repo_get_active(scope_key)
            prev_model = old_record.canonical_model_id if old_record else ""
            old_lock_id = old_record.lock_id if old_record else None

        request_event = ModelReselectionRequested(
            scope_id=scope_id,
            scope_type=scope_type,
            lock_id=old_lock_id,
            previous_canonical_model_id=prev_model,
            reason=reason,
        )
        self._emit(request_event)

        if old_record and old_record.is_active:
            self.release_lock(old_record.lock_id)

        new_context.scope_id = scope_id
        new_context.scope_type = scope_type
        scope_lock = self._get_scope_creation_lock(scope_key)
        with scope_lock:
            new_record = self._create_new_lock(
                new_context,
                scope_key,
                reselection=True,
                previous_model_id=prev_model,
                reselect_reason=reason,
            )

        # Durable audit for explicit reselection (policy-allowed, audited)
        self._audit(
            action="reselect",
            scope_type=scope_type,
            scope_id=scope_id,
            lock_id=new_record.lock_id,
            previous_canonical_model_id=prev_model,
            new_canonical_model_id=new_record.canonical_model_id,
            reason=reason,
        )
        return new_record

    def get_active_lock(self, scope_type: str, scope_id: str) -> Optional[RouteLockRecord]:
        scope_key = self._scope_key(scope_type, scope_id)
        return self._repo_get_active(scope_key)

    def get_lock_by_id(self, lock_id: str) -> Optional[RouteLockRecord]:
        return self._repo_get_by_id(lock_id)

    def update_ruleset(self, new_ruleset: RoutingRuleSet) -> None:
        with self._mutex:
            self._ruleset = new_ruleset

    def update_disabled_models(self, disabled_models: set) -> None:
        with self._mutex:
            self._disabled_models = set(disabled_models)

    # ------------------------------------------------------------------ #
    # Persistence support (for in-memory store only; durable repos persist natively)
    # ------------------------------------------------------------------ #
    def snapshot(self) -> List[dict]:
        """Serialise all lock records (for in-memory store / diagnostics)."""
        from tests.fakes.routing_fakes import InMemoryLockStore
        with self._mutex:
            if isinstance(self._lock_repo, InMemoryLockStore):
                return [rec.to_dict() for rec in self._lock_repo._lock_by_id.values()]
            return []

    def restore_snapshot(self, records: List[dict]) -> None:
        """Restore in-memory lock records (dev/test only)."""
        from tests.fakes.routing_fakes import InMemoryLockStore
        with self._mutex:
            if isinstance(self._lock_repo, InMemoryLockStore):
                for d in records:
                    rec = RouteLockRecord.from_dict(d)
                    scope_key = self._scope_key(rec.scope, rec.scope_id)
                    self._lock_repo._lock_by_id[rec.lock_id] = rec
                    if rec.is_active:
                        self._lock_repo._locks[scope_key] = rec

    # ------------------------------------------------------------------ #
    # Event log (for tests and diagnostics)
    # ------------------------------------------------------------------ #
    @property
    def event_log(self) -> List[RoutingEvent]:
        with self._mutex:
            return list(self._event_log)

    def events_of_type(self, event_type: type) -> List[RoutingEvent]:
        with self._mutex:
            return [e for e in self._event_log if isinstance(e, event_type)]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _scope_key(scope_type: str, scope_id: str) -> str:
        return f"{scope_type}:{scope_id}"

    def _repo_get_active(self, scope_key: str) -> Optional[RouteLockRecord]:
        parts = scope_key.split(":", 1)
        scope_type, scope_id = parts[0], parts[1]
        d = self._lock_repo.get_lock(scope_type, scope_id)
        return RouteLockRecord.from_dict(d) if d else None

    def _repo_get_by_id(self, lock_id: str) -> Optional[RouteLockRecord]:
        d = self._lock_repo.get_lock_by_id(lock_id)
        return RouteLockRecord.from_dict(d) if d else None

    def _get_scope_creation_lock(self, scope_key: str) -> threading.Lock:
        with self._scope_creation_locks_mutex:
            if scope_key not in self._scope_creation_locks:
                self._scope_creation_locks[scope_key] = threading.Lock()
            return self._scope_creation_locks[scope_key]

    def _create_new_lock(
        self,
        context: RuleMatchContext,
        scope_key: str,
        reselection: bool,
        previous_model_id: str = "",
        reselect_reason: str = "",
    ) -> RouteLockRecord:
        with self._mutex:
            current_ruleset = self._ruleset
            current_disabled = set(self._disabled_models)

        matched_rule: Optional[RoutingRule] = self._matcher.find_first_match(
            current_ruleset, context
        )
        if matched_rule is None:
            raise NoMatchingRuleError(context.scope_id, context.scope_type)

        canonical_model_id = matched_rule.canonical_model_id
        if canonical_model_id in current_disabled:
            raise CanonicalModelDisabledError(canonical_model_id)

        snapshot = {
            "rule_id": matched_rule.rule_id,
            "rule_version": matched_rule.rule_version,
            "canonical_model_id": canonical_model_id,
            "selected_at": time.time(),
            "reason": matched_rule.description,
        }
        select_event = ModelSelected(
            scope_id=context.scope_id,
            scope_type=context.scope_type,
            lock_id="",  # filled after create
            canonical_model_id=canonical_model_id,
            rule_id=matched_rule.rule_id,
            rule_version=matched_rule.rule_version,
            reason=matched_rule.description,
        )
        self._emit(select_event)

        # Atomic create-or-reuse in repository (dedupe across processes here)
        lock_dict = self._lock_repo.create_lock(
            scope_type=context.scope_type,
            scope_id=context.scope_id,
            canonical_model_id=canonical_model_id,
            routing_snapshot=snapshot,
            policy_version=matched_rule.rule_version,
        )
        record = RouteLockRecord.from_dict(lock_dict)
        if reselection:
            record.reselection_count = 1

        if reselection:
            reselected_event = ModelReselected(
                scope_id=context.scope_id,
                scope_type=context.scope_type,
                lock_id=record.lock_id,
                previous_canonical_model_id=previous_model_id,
                new_canonical_model_id=canonical_model_id,
                rule_id=matched_rule.rule_id,
                rule_version=matched_rule.rule_version,
                reason=reselect_reason,
            )
            self._emit(reselected_event)
        else:
            lock_event = RouteLocked(
                scope_id=context.scope_id,
                scope_type=context.scope_type,
                lock_id=record.lock_id,
                canonical_model_id=canonical_model_id,
            )
            self._emit(lock_event)
            self._audit(
                action="select",
                scope_type=context.scope_type,
                scope_id=context.scope_id,
                lock_id=record.lock_id,
                canonical_model_id=canonical_model_id,
                reason=matched_rule.description,
                metadata={
                    "rule_id": matched_rule.rule_id,
                    "rule_version": matched_rule.rule_version,
                },
            )
        return record

    def _emit_reuse_event(self, record: RouteLockRecord, context: RuleMatchContext) -> None:
        event = RouteReused(
            scope_id=record.scope_id,
            scope_type=record.scope,
            lock_id=record.lock_id,
            canonical_model_id=record.canonical_model_id,
        )
        self._emit(event)

    def _audit(self, **kwargs) -> None:
        if self._audit_repo is not None:
            try:
                self._audit_repo.record_event(**kwargs)
            except Exception as exc:  # durability boundary must not crash routing
                logger.warning(f"Routing audit write failed: {exc}")

    def _emit(self, event: RoutingEvent) -> None:
        with self._mutex:
            self._event_log.append(event)
        if self._event_handler:
            try:
                self._event_handler(event)
            except Exception:
                pass
