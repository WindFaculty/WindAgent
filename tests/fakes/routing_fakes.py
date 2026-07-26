"""
In-memory fake stores for provider routing tests and dev mode.
Moved from production service files per ban_ke_hoach.md §1.4.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from windagent_providers.base.contracts import DiscoveredModel
from windagent_providers.registry.equivalence import (
    EquivalenceLevel,
    classify_equivalence,
)
from windagent_providers.registry.model_normalizer import normalize_model_id
from windagent_providers.routing.ports import (
    EndpointBindingRepositoryPort,
    RouteLockRepositoryPort,
)
from windagent_providers.routing.route_lock import (
    LockStatus,
    RouteLockRecord,
    RoutingSnapshot,
)


from windagent_providers.registry.canonical_registry import (
    AuditTrailRecord,
    CanonicalModelRecord,
    EndpointBindingRecord,
)


class InMemoryBindingStore(EndpointBindingRepositoryPort):
    """Dev/test-only in-memory fallback implementing the routing port."""

    def __init__(self):
        self._canonical_models: Dict[str, CanonicalModelRecord] = {}
        self._bindings: Dict[str, EndpointBindingRecord] = {}
        self._audit_trails: List[AuditTrailRecord] = []

    def register_discovery_snapshot(self, endpoint_id, discovered_models):
        results: List[Dict[str, Any]] = []
        for disc in discovered_models:
            norm = normalize_model_id(disc.raw_model_id, default_vendor=disc.provider_id)
            canonical_id = None
            for c_id, c_rec in self._canonical_models.items():
                if c_rec.name == norm.canonical_name:
                    canonical_id = c_id
                    break
            if not canonical_id:
                canonical_id = f"cm-{uuid.uuid4().hex[:8]}"
                self._canonical_models[canonical_id] = CanonicalModelRecord(
                    id=canonical_id,
                    name=norm.canonical_name,
                    family=norm.family,
                    vendor=norm.vendor,
                    revision=norm.revision,
                    context_window=disc.context_window or 128000,
                )
            c_rec = self._canonical_models[canonical_id]
            norm_c = normalize_model_id(c_rec.name, default_vendor=c_rec.vendor)
            assessment = classify_equivalence(norm, norm_c)
            existing = None
            for b in self._bindings.values():
                if (
                    b.endpoint_id == endpoint_id
                    and b.canonical_model_id == canonical_id
                    and b.provider_model_id == disc.raw_model_id
                ):
                    existing = b
                    break
            if existing:
                existing.updated_at = time.time()
                existing.equivalence_level = assessment.level.value
                existing.confidence = assessment.confidence
                binding = existing
            else:
                binding = EndpointBindingRecord(
                    id=f"bnd-{uuid.uuid4().hex[:8]}",
                    endpoint_id=endpoint_id,
                    canonical_model_id=canonical_id,
                    provider_model_id=disc.raw_model_id,
                    equivalence_level=assessment.level.value,
                    confidence=assessment.confidence,
                )
                self._bindings[binding.id] = binding
            results.append(binding)
        return results

    def get_exact_equivalent_endpoints(self, canonical_model_id):
        return [
            self._binding_to_dict(b)
            for b in self._bindings.values()
            if b.canonical_model_id == canonical_model_id
            and b.is_active
            and b.equivalence_level == EquivalenceLevel.EXACT_REVISION.value
        ]

    def merge_canonical_models(self, source_canonical_id, target_canonical_id, actor="system"):
        if (
            source_canonical_id not in self._canonical_models
            or target_canonical_id not in self._canonical_models
        ):
            return False
        for b in self._bindings.values():
            if b.canonical_model_id == source_canonical_id:
                b.canonical_model_id = target_canonical_id
                b.updated_at = time.time()
        del self._canonical_models[source_canonical_id]
        self._audit_trails.append(
            AuditTrailRecord(
                id=f"aud-{uuid.uuid4().hex[:8]}",
                action="merge",
                source_id=source_canonical_id,
                target_id=target_canonical_id,
                actor=actor,
            )
        )
        return True

    def split_binding(self, binding_id, new_canonical_name, actor="system"):
        if binding_id not in self._bindings:
            return None
        binding = self._bindings[binding_id]
        old_canonical_id = binding.canonical_model_id
        new_canonical_id = f"cm-{uuid.uuid4().hex[:8]}"
        self._canonical_models[new_canonical_id] = CanonicalModelRecord(
            id=new_canonical_id,
            name=new_canonical_name,
            family=new_canonical_name,
            vendor="custom",
            revision=None,
        )
        binding.canonical_model_id = new_canonical_id
        binding.equivalence_level = EquivalenceLevel.EXACT_REVISION.value
        binding.confidence = 1.0
        binding.updated_at = time.time()
        self._audit_trails.append(
            AuditTrailRecord(
                id=f"aud-{uuid.uuid4().hex[:8]}",
                action="split",
                source_id=old_canonical_id,
                target_id=new_canonical_id,
                actor=actor,
            )
        )
        return self._binding_to_dict(binding)

    def get_audit_trails(self):
        return list(self._audit_trails)

    @staticmethod
    def _binding_to_dict(b: EndpointBindingRecord) -> Dict[str, Any]:
        return {
            "id": b.id,
            "endpoint_id": b.endpoint_id,
            "canonical_model_id": b.canonical_model_id,
            "provider_model_id": b.provider_model_id,
            "equivalence_level": b.equivalence_level,
            "is_active": b.is_active,
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        }


class InMemoryLockStore(RouteLockRepositoryPort):
    """Dev/test-only in-memory fallback implementing the route lock port."""

    def __init__(self):
        self._locks: Dict[str, RouteLockRecord] = {}
        self._lock_by_id: Dict[str, RouteLockRecord] = {}
        self._mutex = threading.RLock()

    def _get_active_lock_dict(self, scope_type, scope_id):
        for rec in self._locks.values():
            if rec.scope == scope_type and rec.scope_id == scope_id and rec.is_active:
                return rec.to_dict()
        return None

    def get_lock(self, scope_type, scope_id):
        with self._mutex:
            return self._get_active_lock_dict(scope_type, scope_id)

    def get_lock_by_id(self, lock_id):
        with self._mutex:
            rec = self._lock_by_id.get(lock_id)
            return rec.to_dict() if rec else None

    def create_lock(self, scope_type, scope_id, canonical_model_id, routing_snapshot, policy_version=1):
        with self._mutex:
            existing = self._get_active_lock_dict(scope_type, scope_id)
            if existing:
                return existing
            lock_id = f"lk-{uuid.uuid4().hex[:10]}"
            rec = RouteLockRecord(
                lock_id=lock_id,
                scope=scope_type,
                scope_id=scope_id,
                canonical_model_id=canonical_model_id,
                routing_snapshot=RoutingSnapshot(
                    rule_id=routing_snapshot.get("rule_id", ""),
                    rule_version=routing_snapshot.get("rule_version", 1),
                    canonical_model_id=canonical_model_id,
                    reason=routing_snapshot.get("reason", ""),
                ),
            )
            self._locks[f"{scope_type}:{scope_id}"] = rec
            self._lock_by_id[lock_id] = rec
            return rec.to_dict()

    def release_lock(self, lock_id):
        with self._mutex:
            rec = self._lock_by_id.get(lock_id)
            if rec is None or not rec.is_active:
                return False
            rec.status = LockStatus.RELEASED.value
            rec.released_at = time.time()
            return True
