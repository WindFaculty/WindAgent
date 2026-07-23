"""
RouteLockService — Phase 7 core service.

Responsibilities
----------------
1. Resolve or create a route lock for a (scope_type, scope_id) pair.
   - If an active lock exists → reuse it (RouteReused event).
   - If no lock exists → evaluate rules → atomically create lock (RouteLocked).
2. Explicit unlock (RouteReleased event).
3. Explicit model reselection: release old lock, create new lock
   (ModelReselectionRequested + ModelReselected events).
4. Persist / reload locks across process restart via to_dict / from_dict.

Concurrency model
-----------------
A threading.Lock guards the internal state dict so that concurrent first
requests for the same scope_id only create one lock.  A "write-lock then
check-again" pattern (double-checked locking on the stable dict key)
ensures exactly-once creation under concurrent entry.

No external database is required for in-process use.  The service exposes
``snapshot()`` / ``restore_snapshot()`` for persistence integration.

Key invariants (validated in tests)
-------------------------------------
* One active lock per scope_id.
* 100+ turns on the same session all return the same canonical_model_id.
* Concurrent first requests → only one lock created.
* Process-restart simulation: snapshot → restore → resolve returns same ID.
* Rule update after lock creation → lock unchanged.
* No silent fallback to another model.
* Reselection always emits ModelReselectionRequested + ModelReselected.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Callable, Dict, List, Optional

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
    RoutingSnapshot,
)
from windagent_providers.routing.rule_matcher import RuleMatchContext, RuleMatcher
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet


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
    Thread-safe in-process Route Lock Service.

    Parameters
    ----------
    ruleset         : The active RoutingRuleSet.
    matcher         : Optional RuleMatcher (default-constructed if not provided).
    disabled_models : Set of canonical model IDs that are currently disabled.
                      The service will not lock a disabled model.
    event_handler   : Optional callback ``(RoutingEvent) -> None`` invoked
                      synchronously after each state-change event.
    """

    def __init__(
        self,
        ruleset: RoutingRuleSet,
        matcher: Optional[RuleMatcher] = None,
        disabled_models: Optional[set] = None,
        event_handler: Optional[Callable[[RoutingEvent], None]] = None,
    ):
        self._ruleset = ruleset
        self._matcher: RuleMatcher = matcher or RuleMatcher()
        self._disabled_models: set = disabled_models or set()
        self._event_handler = event_handler

        # Primary lock storage: scope_key → RouteLockRecord
        # scope_key = f"{scope_type}:{scope_id}"
        self._locks: Dict[str, RouteLockRecord] = {}

        # Secondary index: lock_id → RouteLockRecord
        self._lock_by_id: Dict[str, RouteLockRecord] = {}

        # Per-scope event log for audit / test verification
        self._event_log: List[RoutingEvent] = []

        # Global mutex for all mutations
        self._mutex = threading.Lock()

        # Per-scope creation locks to avoid thundering herd
        self._scope_creation_locks: Dict[str, threading.Lock] = {}
        self._scope_creation_locks_mutex = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def resolve_or_create_lock(
        self,
        context: RuleMatchContext,
    ) -> RouteLockRecord:
        """
        Main entry point for every model call.

        - If an ACTIVE lock exists for (scope_type, scope_id) → return it
          (RouteReused event).
        - If no lock exists → evaluate rules → atomically create lock
          (ModelSelected + RouteLocked events).

        Raises
        ------
        NoMatchingRuleError          : if no rule matches the context.
        CanonicalModelDisabledError  : if the matched model is disabled.
        """
        scope_key = self._scope_key(context.scope_type, context.scope_id)

        # Fast path: check without acquiring creation lock
        existing = self._get_active_lock_by_key(scope_key)
        if existing:
            self._emit_reuse_event(existing, context)
            return existing

        # Slow path: per-scope creation lock (prevents duplicate creation under
        # concurrent first requests for the same scope_id)
        scope_lock = self._get_scope_creation_lock(scope_key)
        with scope_lock:
            # Double-check after acquiring scope lock
            existing = self._get_active_lock_by_key(scope_key)
            if existing:
                self._emit_reuse_event(existing, context)
                return existing

            return self._create_new_lock(context, scope_key, reselection=False)

    def release_lock(self, lock_id: str) -> RouteLockRecord:
        """
        Explicitly release an active lock.  Emits RouteReleased.

        Raises LockNotFoundError if lock_id is unknown or already released.
        """
        with self._mutex:
            record = self._lock_by_id.get(lock_id)
            if record is None:
                raise LockNotFoundError(lock_id)
            if record.status == LockStatus.RELEASED.value:
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
        """
        Explicit model reselection for a scope.

        Steps:
        1. Emit ModelReselectionRequested.
        2. Release existing active lock (if any).
        3. Evaluate rules with new_context → create new lock.
        4. Emit ModelReselected.

        Raises
        ------
        NoMatchingRuleError          : if no rule matches new_context.
        CanonicalModelDisabledError  : if the matched model is disabled.
        """
        scope_key = self._scope_key(scope_type, scope_id)

        # Capture previous model for event
        with self._mutex:
            old_record = self._locks.get(scope_key)
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

        # Release old lock if active
        if old_record and old_record.is_active:
            self.release_lock(old_record.lock_id)

        # Ensure new_context matches scope
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

        return new_record

    def get_active_lock(
        self, scope_type: str, scope_id: str
    ) -> Optional[RouteLockRecord]:
        """Return the active lock for a scope, or None."""
        scope_key = self._scope_key(scope_type, scope_id)
        return self._get_active_lock_by_key(scope_key)

    def get_lock_by_id(self, lock_id: str) -> Optional[RouteLockRecord]:
        """Return any lock record by lock_id (active or released)."""
        return self._lock_by_id.get(lock_id)

    def update_ruleset(self, new_ruleset: RoutingRuleSet) -> None:
        """
        Replace the active ruleset.  Does NOT affect existing locks.
        Future resolve_or_create_lock calls will use the new rules.
        """
        with self._mutex:
            self._ruleset = new_ruleset

    def update_disabled_models(self, disabled_models: set) -> None:
        """Replace the disabled model set (affects future lock creation only)."""
        with self._mutex:
            self._disabled_models = set(disabled_models)

    # ------------------------------------------------------------------ #
    # Persistence support
    # ------------------------------------------------------------------ #

    def snapshot(self) -> List[dict]:
        """Serialise all lock records for persistence."""
        with self._mutex:
            return [rec.to_dict() for rec in self._lock_by_id.values()]

    def restore_snapshot(self, records: List[dict]) -> None:
        """
        Restore lock records from a persisted snapshot.
        Existing in-memory state is preserved; snapshot records are merged.
        """
        with self._mutex:
            for d in records:
                rec = RouteLockRecord.from_dict(d)
                scope_key = self._scope_key(rec.scope, rec.scope_id)
                self._lock_by_id[rec.lock_id] = rec
                # Only overwrite the active slot if this record is active
                if rec.is_active:
                    self._locks[scope_key] = rec

    # ------------------------------------------------------------------ #
    # Event log (for tests and diagnostics)
    # ------------------------------------------------------------------ #

    @property
    def event_log(self) -> List[RoutingEvent]:
        """Read-only view of all events emitted since construction."""
        return list(self._event_log)

    def events_of_type(self, event_type: type) -> List[RoutingEvent]:
        """Filter event log by Python type."""
        return [e for e in self._event_log if isinstance(e, event_type)]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _scope_key(scope_type: str, scope_id: str) -> str:
        return f"{scope_type}:{scope_id}"

    def _get_active_lock_by_key(self, scope_key: str) -> Optional[RouteLockRecord]:
        with self._mutex:
            rec = self._locks.get(scope_key)
            if rec and rec.is_active:
                return rec
            return None

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
        """
        Evaluate rules and atomically create a new lock.
        Must be called while holding the per-scope creation lock.
        """
        # Read ruleset under global mutex (it may be updated concurrently)
        with self._mutex:
            current_ruleset = self._ruleset
            current_disabled = set(self._disabled_models)

        # --- Rule evaluation (outside mutex; stateless) ---
        matched_rule: Optional[RoutingRule] = self._matcher.find_first_match(
            current_ruleset, context
        )

        if matched_rule is None:
            raise NoMatchingRuleError(context.scope_id, context.scope_type)

        canonical_model_id = matched_rule.canonical_model_id

        if canonical_model_id in current_disabled:
            raise CanonicalModelDisabledError(canonical_model_id)

        # --- Emit ModelSelected ---
        new_lock_id = f"lk-{uuid.uuid4().hex[:10]}"
        select_event = ModelSelected(
            scope_id=context.scope_id,
            scope_type=context.scope_type,
            lock_id=new_lock_id,
            canonical_model_id=canonical_model_id,
            rule_id=matched_rule.rule_id,
            rule_version=matched_rule.rule_version,
            reason=matched_rule.description,
        )
        self._emit(select_event)

        snapshot = RoutingSnapshot(
            rule_id=matched_rule.rule_id,
            rule_version=matched_rule.rule_version,
            canonical_model_id=canonical_model_id,
            reason=matched_rule.description,
        )

        record = RouteLockRecord(
            lock_id=new_lock_id,
            scope=context.scope_type,
            scope_id=context.scope_id,
            canonical_model_id=canonical_model_id,
            routing_snapshot=snapshot,
        )
        if reselection:
            record.reselection_count = 1

        # --- Atomic commit ---
        with self._mutex:
            self._locks[scope_key] = record
            self._lock_by_id[new_lock_id] = record

        # --- Emit RouteLocked or ModelReselected ---
        if reselection:
            reselected_event = ModelReselected(
                scope_id=context.scope_id,
                scope_type=context.scope_type,
                lock_id=new_lock_id,
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
                lock_id=new_lock_id,
                canonical_model_id=canonical_model_id,
            )
            self._emit(lock_event)

        return record

    def _emit_reuse_event(
        self, record: RouteLockRecord, context: RuleMatchContext
    ) -> None:
        event = RouteReused(
            scope_id=record.scope_id,
            scope_type=record.scope,
            lock_id=record.lock_id,
            canonical_model_id=record.canonical_model_id,
        )
        self._emit(event)

    def _emit(self, event: RoutingEvent) -> None:
        self._event_log.append(event)
        if self._event_handler:
            try:
                self._event_handler(event)
            except Exception:
                # Event handler failure must never crash core routing
                pass
