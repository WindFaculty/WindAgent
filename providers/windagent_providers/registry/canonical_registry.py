"""
Canonical Model Registry Service for WindAgent Provider Subsystem V3.

Phase 1: database is the source of truth.  The service depends only on
``EndpointBindingRepositoryPort``; when no repository is injected it falls back
to an in-memory store (development / tests only — NOT for production, see
ban_ke_hoach.md §1.4).  All production composition roots inject the SQL
repository so API and Worker share one durable authority.
"""

from __future__ import annotations
import time
import logging
import warnings
from typing import List, Optional
from dataclasses import dataclass, field

from windagent_providers.base.contracts import DiscoveredModel
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
            from tests.fakes.routing_fakes import InMemoryBindingStore
            self._repo = InMemoryBindingStore()

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
        from tests.fakes.routing_fakes import InMemoryBindingStore
        return not isinstance(self._repo, InMemoryBindingStore)

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
