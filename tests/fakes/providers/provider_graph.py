"""Seed a minimal provider reference graph for FK-enforced tests.

With SQLite ``PRAGMA foreign_keys=ON`` (Stage 1 GAP A), inserts into
``agent_turns`` and ``route_attempts_v3`` must reference existing rows in
``route_locks_v3``, ``canonical_models_v3`` and ``endpoint_model_bindings``.
Production seeds this graph from discovery/onboarding; tests that exercise the
routed turn path (phase3 unit, phase8 integration) seed just enough reference
rows here.

Two pieces are provided:

- ``seed_provider_graph``  — one-time static reference graph (vendor, endpoints,
  bindings, canonical model) that never changes across a scenario.
- ``PersistentRouteLocks`` — a drop-in replacement for the old in-memory
  ``RouteLocks`` fakes that also persists each resolved lock into
  ``route_locks_v3``, mirroring ``SQLRouteLockRepository.create_lock``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session


def _now() -> datetime:
    return datetime.now(timezone.utc)


def seed_canonical_model(session: Session, canonical_model_id: str, vendor: str = "seed") -> None:
    """Ensure a canonical model row exists for FK-referencing lock/attempt inserts."""
    now = _now()
    session.execute(
        text(
            """
            INSERT INTO canonical_models_v3
            (id, vendor, family, canonical_name, revision, context_window,
             capabilities_json, tool_call_protocol, enabled, created_at, updated_at)
            VALUES (:id, :vendor, :family, :name, 'latest', 128000, '[]', NULL, TRUE, :now, :now)
            ON CONFLICT(id) DO NOTHING
            """
        ),
        {
            "id": canonical_model_id,
            "vendor": vendor,
            "family": vendor,
            "name": canonical_model_id,
            "now": now,
        },
    )
    session.commit()


def seed_provider_graph(
    session: Session,
    *,
    canonical_model_id: str,
    bindings: Sequence[Mapping[str, Any]],
) -> None:
    """Insert the canonical model, vendor, endpoints and bindings a scenario uses.

    ``bindings`` entries follow the ``InMemoryEndpointRegistry`` shape used by
    the routed-turn tests (endpoint_id / binding_id / canonical_model_id /
    provider_model_id / provider_name / base_url / equivalence_level / enabled).
    """
    now = _now()
    session.execute(
        text(
            """
            INSERT INTO canonical_models_v3
            (id, vendor, family, canonical_name, revision, context_window,
             capabilities_json, tool_call_protocol, enabled, created_at, updated_at)
            VALUES (:id, :vendor, :family, :name, 'latest', 128000, '[]', NULL, TRUE, :now, :now)
            ON CONFLICT(id) DO NOTHING
            """
        ),
        {
            "id": canonical_model_id,
            "vendor": "seed",
            "family": "seed",
            "name": canonical_model_id,
            "now": now,
        },
    )
    for binding in bindings:
        vendor_id = f"vendor-{binding['provider_name']}"
        session.execute(
            text(
                """
                INSERT INTO provider_vendors
                (id, name, vendor_type, supports_model_discovery,
                 supports_openai_compatible, enabled, created_at, updated_at)
                VALUES (:id, :name, 'cloud', TRUE, TRUE, TRUE, :now, :now)
                ON CONFLICT(id) DO NOTHING
                """
            ),
            {"id": vendor_id, "name": binding["provider_name"], "now": now},
        )
        session.execute(
            text(
                """
                INSERT INTO provider_endpoints
                (id, vendor_id, credential_id, base_url, protocol_mode,
                 configured_protocol, detected_protocol, protocol_confidence,
                 region, priority, weight, enabled, test_status, last_tested_at,
                 created_at, updated_at)
                VALUES (:id, :vendor_id, NULL, :base_url, 'openai', NULL, NULL, 1.0,
                        'global', 50, 100, TRUE, 'pass', NULL, :now, :now)
                ON CONFLICT(id) DO NOTHING
                """
            ),
            {
                "id": binding["endpoint_id"],
                "vendor_id": vendor_id,
                "base_url": binding["base_url"],
                "now": now,
            },
        )
        session.execute(
            text(
                """
                INSERT INTO endpoint_model_bindings
                (id, endpoint_id, canonical_model_id, provider_model_id,
                 model_revision, equivalence_level, equivalence_fingerprint,
                 capabilities_json, pricing_overrides_json, enabled, priority,
                 availability, pricing_class, created_at, updated_at)
                VALUES (:id, :endpoint_id, :canonical_model_id, :provider_model_id,
                        'latest', :equivalence, NULL, '[]', '{}', :enabled, 50,
                        'active', 'UNKNOWN', :now, :now)
                ON CONFLICT(id) DO NOTHING
                """
            ),
            {
                "id": binding["binding_id"],
                "endpoint_id": binding["endpoint_id"],
                "canonical_model_id": canonical_model_id,
                "provider_model_id": binding["provider_model_id"],
                "equivalence": binding.get("equivalence_level", "exact_revision"),
                "enabled": bool(binding.get("is_active", True)),
                "now": now,
            },
        )
    session.commit()


class PersistentRouteLocks:
    """Deterministic route-lock boundary that persists into ``route_locks_v3``.

    Replaces the in-memory fakes so ``agent_turns.route_lock_id`` satisfies the
    FK now enforced by GAP A.  A per-version key env is *not* required: the
    reference ``canonical_model_id`` must have been seeded first via
    ``seed_provider_graph``.
    """

    def __init__(
        self,
        session_factory: Any,
        canonical_model_id: str,
        *,
        rule_id: str = "test-lock-rule",
        rule_version: int = 1,
        reason: str = "persisted test lock",
    ) -> None:
        self._session_factory = session_factory
        self.canonical_model_id = canonical_model_id
        self._rule_id = rule_id
        self._rule_version = rule_version
        self._reason = reason
        self._locks: dict[str, Any] = {}

    def resolve_or_create_lock(self, context: Any) -> Any:
        lock = self._locks.setdefault(
            context.scope_id,
            SimpleNamespace(
                lock_id=f"lock-{context.scope_id}",
                canonical_model_id=self.canonical_model_id,
                routing_snapshot=SimpleNamespace(
                    rule_id=self._rule_id,
                    rule_version=self._rule_version,
                    reason=self._reason,
                ),
            ),
        )
        self._persist(context, lock)
        return lock

    def _persist(self, context: Any, lock: Any) -> None:
        now = _now()
        with self._session_factory() as session:
            # The lock FK references canonical_models_v3; make the reference row
            # exist for scenarios that never seed a provider graph explicitly.
            session.execute(
                text(
                    """
                    INSERT INTO canonical_models_v3
                    (id, vendor, family, canonical_name, revision, context_window,
                     capabilities_json, tool_call_protocol, enabled, created_at, updated_at)
                    VALUES (:id, 'seed', 'seed', :name, 'latest', 128000, '[]', NULL, TRUE, :now, :now)
                    ON CONFLICT(id) DO NOTHING
                    """
                ),
                {
                    "id": self.canonical_model_id,
                    "name": self.canonical_model_id,
                    "now": now,
                },
            )
            session.execute(
                text(
                    """
                    INSERT INTO route_locks_v3
                    (id, scope_type, scope_id, canonical_model_id, policy_version,
                     version, routing_snapshot_json, status, reselection_reason,
                     created_at, updated_at, released_at)
                    VALUES (:id, :scope_type, :scope_id, :canonical_model_id,
                            :policy_version, 1, :snapshot, 'active', NULL,
                            :now, :now, NULL)
                    ON CONFLICT(id) DO NOTHING
                    """
                ),
                {
                    "id": lock.lock_id,
                    "scope_type": getattr(context, "scope_type", "agent_session"),
                    "scope_id": context.scope_id,
                    "canonical_model_id": self.canonical_model_id,
                    "policy_version": self._rule_version,
                    "snapshot": json.dumps(
                        {
                            "rule_id": self._rule_id,
                            "rule_version": self._rule_version,
                            "canonical_model_id": self.canonical_model_id,
                            "reason": self._reason,
                        }
                    ),
                    "now": now,
                },
            )
            session.commit()
