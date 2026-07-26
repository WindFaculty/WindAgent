"""
Canonical Model Registry Service for WindAgent Provider Subsystem V3.

Phase 1: database is the source of truth.  The service depends only on
``EndpointBindingRepositoryPort``; when no repository is injected it falls back
to an in-memory store (development / tests only — NOT for production, see
ban_ke_hoach.md §1.4).  All production composition roots inject the SQL
repository so API and Worker share one durable authority.
"""

from __future__ import annotations
import uuid
import time
import logging
import warnings
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from windagent_providers.base.contracts import DiscoveredModel
from windagent_providers.registry.model_normalizer import normalize_model_id
from windagent_providers.registry.equivalence import (
    classify_equivalence,
    EquivalenceLevel,
)
from windagent_providers.routing.ports import EndpointBindingRepositoryPort

logger = logging.getLogger("windagent.providers.registry")


@dataclass
class CanonicalModelRecord:
    id: str
    name: str
    family: str
    vendor: str
    revision: Optional[str]
    context_window: int = 128000
    created_at: float = field(default_factory=time.time)


@dataclass
class EndpointBindingRecord:
    id: str
    endpoint_id: str
    canonical_model_id: str
    provider_model_id: str
    equivalence_level: str
    confidence: float
    is_active: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class AuditTrailRecord:
    id: str
    action: str  # "merge", "split"
    source_id: str
    target_id: str
    actor: str
    timestamp: float = field(default_factory=time.time)


class _InMemoryBindingStore(EndpointBindingRepositoryPort):
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


class CanonicalModelRegistryService:
    """Canonical model registry. Durable when a repository is injected."""

    def __init__(self, binding_repository: Optional[EndpointBindingRepositoryPort] = None):
        self._repo = binding_repository
        if self._repo is None:
            warnings.warn(
                "CanonicalModelRegistryService running IN-MEMORY (dev/test only). "
                "Inject EndpointBindingRepositoryPort for production durability.",
                stacklevel=2,
            )
            self._repo = _InMemoryBindingStore()

    # ------------------------------------------------------------------ #
    # Public API (unchanged signatures for existing call sites/tests)
    # ------------------------------------------------------------------ #
    def register_discovery_snapshot(
        self, endpoint_id: str, discovered_models: List[DiscoveredModel]
    ) -> List[EndpointBindingRecord]:
        raw = self._repo.register_discovery_snapshot(endpoint_id, discovered_models)
        return [self._coerce_binding(b) for b in raw]

    def get_exact_equivalent_endpoints(
        self, canonical_model_id: str
    ) -> List[EndpointBindingRecord]:
        raw = self._repo.get_exact_equivalent_endpoints(canonical_model_id)
        return [self._coerce_binding(b) for b in raw]

    def merge_canonical_models(
        self, source_canonical_id: str, target_canonical_id: str, actor: str = "system"
    ) -> bool:
        return self._repo.merge_canonical_models(source_canonical_id, target_canonical_id, actor)

    def split_binding(
        self, binding_id: str, new_canonical_name: str, actor: str = "system"
    ) -> Optional[EndpointBindingRecord]:
        r = self._repo.split_binding(binding_id, new_canonical_name, actor)
        return self._coerce_binding(r) if r else None

    def get_audit_trails(self) -> List[AuditTrailRecord]:
        return self._repo.get_audit_trails()

    @property
    def is_durable(self) -> bool:
        return not isinstance(self._repo, _InMemoryBindingStore)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _coerce_binding(b) -> EndpointBindingRecord:
        if isinstance(b, EndpointBindingRecord):
            return b
        return EndpointBindingRecord(
            id=b["id"],
            endpoint_id=b["endpoint_id"],
            canonical_model_id=b["canonical_model_id"],
            provider_model_id=b["provider_model_id"],
            equivalence_level=b["equivalence_level"],
            confidence=b.get("confidence", 1.0),
            is_active=b.get("is_active", True),
            created_at=b.get("created_at", time.time()),
            updated_at=b.get("updated_at", time.time()),
        )
