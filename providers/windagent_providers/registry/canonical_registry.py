"""
Canonical Model Registry Service for WindAgent Provider Subsystem V3.
Manages canonical model definitions, endpoint bindings, equivalence classification,
discovery snapshot reconciliation, and audit trails.
"""

from __future__ import annotations
import uuid
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from windagent_providers.base.contracts import DiscoveredModel
from windagent_providers.registry.model_normalizer import normalize_model_id, NormalizedModelInfo
from windagent_providers.registry.equivalence import classify_equivalence, EquivalenceLevel, EquivalenceAssessment


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
    """In-memory & persistence-backed Canonical Model Registry Engine."""

    def __init__(self):
        self._canonical_models: Dict[str, CanonicalModelRecord] = {}
        self._bindings: Dict[str, EndpointBindingRecord] = {}
        self._audit_trails: List[AuditTrailRecord] = []

    def register_discovery_snapshot(
        self, endpoint_id: str, discovered_models: List[DiscoveredModel]
    ) -> List[EndpointBindingRecord]:
        """
        Idempotently processes endpoint discovery snapshot.
        Re-running discovery updates timestamps and metadata without creating duplicates.
        """
        results: List[EndpointBindingRecord] = []

        for disc in discovered_models:
            norm = normalize_model_id(disc.raw_model_id, default_vendor=disc.provider_id)
            
            # Find or create canonical model
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

            # Check if binding already exists for this endpoint + canonical model
            existing_binding = None
            for b in self._bindings.values():
                if b.endpoint_id == endpoint_id and b.canonical_model_id == canonical_id and b.provider_model_id == disc.raw_model_id:
                    existing_binding = b
                    break

            if existing_binding:
                existing_binding.updated_at = time.time()
                existing_binding.equivalence_level = assessment.level.value
                existing_binding.confidence = assessment.confidence
                results.append(existing_binding)
            else:
                binding_id = f"bnd-{uuid.uuid4().hex[:8]}"
                new_binding = EndpointBindingRecord(
                    id=binding_id,
                    endpoint_id=endpoint_id,
                    canonical_model_id=canonical_id,
                    provider_model_id=disc.raw_model_id,
                    equivalence_level=assessment.level.value,
                    confidence=assessment.confidence,
                )
                self._bindings[binding_id] = new_binding
                results.append(new_binding)

        return results

    def get_exact_equivalent_endpoints(self, canonical_model_id: str) -> List[EndpointBindingRecord]:
        """
        Returns binding records strictly with equivalence_level == 'exact_revision'.
        Used exclusively for automatic failover candidate querying.
        """
        return [
            b for b in self._bindings.values()
            if b.canonical_model_id == canonical_model_id
            and b.is_active
            and b.equivalence_level == EquivalenceLevel.EXACT_REVISION.value
        ]

    def merge_canonical_models(self, source_canonical_id: str, target_canonical_id: str, actor: str = "system") -> bool:
        """Merges source canonical model into target canonical model with audit tracking."""
        if source_canonical_id not in self._canonical_models or target_canonical_id not in self._canonical_models:
            return False

        # Re-point bindings
        for b in self._bindings.values():
            if b.canonical_model_id == source_canonical_id:
                b.canonical_model_id = target_canonical_id
                b.updated_at = time.time()

        # Delete source model
        del self._canonical_models[source_canonical_id]

        # Audit log
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

    def split_binding(self, binding_id: str, new_canonical_name: str, actor: str = "system") -> Optional[EndpointBindingRecord]:
        """Splits an endpoint model binding into a newly created canonical model with audit tracking."""
        if binding_id not in self._bindings:
            return None

        binding = self._bindings[binding_id]
        old_canonical_id = binding.canonical_model_id

        new_canonical_id = f"cm-{uuid.uuid4().hex[:8]}"
        new_canonical = CanonicalModelRecord(
            id=new_canonical_id,
            name=new_canonical_name,
            family=new_canonical_name,
            vendor="custom",
            revision=None,
        )
        self._canonical_models[new_canonical_id] = new_canonical

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
        return binding

    def get_audit_trails(self) -> List[AuditTrailRecord]:
        """Returns recorded audit log entries."""
        return self._audit_trails.copy()
