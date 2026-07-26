"""
SQL concrete repositories for Phase 1 durable routing authority.

Implements the SYNCHRONOUS routing ports defined in
``windagent_providers.routing.ports``:

- SQLEndpointBindingRepository     (EndpointBindingRepositoryPort)
- SQLProviderRoutingAuditRepository (RoutingAuditRepositoryPort)

These keep the provider package free of ORM imports (ban_ke_hoach.md §1.3).
They receive a synchronous SQLAlchemy ``Session``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from windagent_providers.base.contracts import DiscoveredModel
from windagent_providers.registry.model_normalizer import normalize_model_id
from windagent_providers.registry.equivalence import (
    classify_equivalence,
    EquivalenceLevel,
)
from windagent_providers.routing.ports import (
    EndpointBindingRepositoryPort,
    RoutingAuditRepositoryPort,
)
from windagent_storage.orm.v3_models import (
    CanonicalModelV3ORM,
    EndpointModelBindingORM,
    ProviderRoutingAuditV3ORM,
)


class SQLEndpointBindingRepository(EndpointBindingRepositoryPort):
    """SQL-backed canonical model registry + endpoint binding repository."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ #
    # Canonical model helpers
    # ------------------------------------------------------------------ #
    def _find_or_create_canonical(self, norm) -> CanonicalModelV3ORM:
        existing = (
            self.session.query(CanonicalModelV3ORM)
            .filter_by(canonical_name=norm.canonical_name)
            .first()
        )
        if existing:
            return existing
        cm = CanonicalModelV3ORM(
            id=f"cm-{uuid.uuid4().hex[:12]}",
            vendor=norm.vendor,
            family=norm.family,
            canonical_name=norm.canonical_name,
            revision=norm.revision or "latest",
            context_window=128000,
        )
        self.session.add(cm)
        self.session.flush(); self.session.commit()
        return cm

    # ------------------------------------------------------------------ #
    # EndpointBindingRepositoryPort
    # ------------------------------------------------------------------ #
    def register_discovery_snapshot(
        self, endpoint_id: str, discovered_models: List[DiscoveredModel]
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for disc in discovered_models:
            norm = normalize_model_id(
                disc.raw_model_id, default_vendor=disc.provider_id
            )
            canonical = self._find_or_create_canonical(norm)
            norm_c = normalize_model_id(
                canonical.canonical_name, default_vendor=canonical.vendor
            )
            assessment = classify_equivalence(norm, norm_c)

            existing = (
                self.session.query(EndpointModelBindingORM)
                .filter_by(
                    endpoint_id=endpoint_id,
                    canonical_model_id=canonical.id,
                    provider_model_id=disc.raw_model_id,
                )
                .first()
            )
            if existing:
                existing.updated_at = datetime.now(timezone.utc)
                existing.equivalence_level = assessment.level.value
                binding = existing
            else:
                binding = EndpointModelBindingORM(
                    id=f"bnd-{uuid.uuid4().hex[:12]}",
                    endpoint_id=endpoint_id,
                    canonical_model_id=canonical.id,
                    provider_model_id=disc.raw_model_id,
                    model_revision=norm.revision or "latest",
                    equivalence_level=assessment.level.value,
                    equivalence_fingerprint=f"{canonical.id}:{disc.raw_model_id}",
                    enabled=True,
                    priority=50,
                )
                self.session.add(binding)
                self.session.flush(); self.session.commit()
            results.append(self._binding_to_dict(binding))
        return results

    def get_exact_equivalent_endpoints(
        self, canonical_model_id: str
    ) -> List[Dict[str, Any]]:
        bindings = (
            self.session.query(EndpointModelBindingORM)
            .filter_by(
                canonical_model_id=canonical_model_id,
                enabled=True,
                equivalence_level=EquivalenceLevel.EXACT_REVISION.value,
            )
            .all()
        )
        return [self._binding_to_dict(b) for b in bindings]

    def merge_canonical_models(
        self, source_canonical_id: str, target_canonical_id: str, actor: str = "system"
    ) -> bool:
        src = self.session.query(CanonicalModelV3ORM).filter_by(
            id=source_canonical_id
        ).first()
        tgt = self.session.query(CanonicalModelV3ORM).filter_by(
            id=target_canonical_id
        ).first()
        if not src or not tgt:
            return False
        self.session.query(EndpointModelBindingORM).filter_by(
            canonical_model_id=source_canonical_id
        ).update({EndpointModelBindingORM.canonical_model_id: target_canonical_id})
        self.session.delete(src)
        self.session.flush(); self.session.commit()
        return True

    def split_binding(
        self, binding_id: str, new_canonical_name: str, actor: str = "system"
    ) -> Optional[Dict[str, Any]]:
        binding = self.session.query(EndpointModelBindingORM).filter_by(
            id=binding_id
        ).first()
        if not binding:
            return None
        new_cm = CanonicalModelV3ORM(
            id=f"cm-{uuid.uuid4().hex[:12]}",
            vendor="custom",
            family=new_canonical_name,
            canonical_name=new_canonical_name,
            revision="latest",
            context_window=128000,
        )
        self.session.add(new_cm)
        self.session.flush(); self.session.commit()
        binding.canonical_model_id = new_cm.id
        binding.equivalence_level = EquivalenceLevel.EXACT_REVISION.value
        binding.updated_at = datetime.now(timezone.utc)
        self.session.flush(); self.session.commit()
        return self._binding_to_dict(binding)

    def get_audit_trails(self) -> List[Dict[str, Any]]:
        rows = (
            self.session.query(ProviderRoutingAuditV3ORM)
            .order_by(ProviderRoutingAuditV3ORM.created_at.desc())
            .all()
        )
        return [self._audit_to_dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _binding_to_dict(b: EndpointModelBindingORM) -> Dict[str, Any]:
        return {
            "id": b.id,
            "endpoint_id": b.endpoint_id,
            "canonical_model_id": b.canonical_model_id,
            "provider_model_id": b.provider_model_id,
            "equivalence_level": b.equivalence_level,
            "is_active": b.enabled,
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        }

    @staticmethod
    def _audit_to_dict(r: ProviderRoutingAuditV3ORM) -> Dict[str, Any]:
        return {
            "id": r.id,
            "action": r.action,
            "scope_type": r.scope_type,
            "scope_id": r.scope_id,
            "lock_id": r.lock_id,
            "canonical_model_id": r.canonical_model_id,
            "previous_canonical_model_id": r.previous_canonical_model_id,
            "new_canonical_model_id": r.new_canonical_model_id,
            "endpoint_id": r.endpoint_id,
            "reason": r.reason,
            "actor": r.actor,
            "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
            "created_at": r.created_at,
        }


class SQLProviderRoutingAuditRepository(RoutingAuditRepositoryPort):
    """SQL-backed durable provider routing audit trail."""

    def __init__(self, session: Session):
        self.session = session

    def record_event(
        self,
        action: str,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        lock_id: Optional[str] = None,
        canonical_model_id: Optional[str] = None,
        previous_canonical_model_id: Optional[str] = None,
        new_canonical_model_id: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        reason: Optional[str] = None,
        actor: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        row = ProviderRoutingAuditV3ORM(
            id=f"aud-{uuid.uuid4().hex[:12]}",
            action=action,
            scope_type=scope_type,
            scope_id=scope_id,
            lock_id=lock_id,
            canonical_model_id=canonical_model_id,
            previous_canonical_model_id=previous_canonical_model_id,
            new_canonical_model_id=new_canonical_model_id,
            endpoint_id=endpoint_id,
            reason=reason,
            actor=actor,
            metadata_json=json.dumps(metadata or {}),
        )
        self.session.add(row)
        self.session.flush(); self.session.commit()
        return str(row.id)

    def get_audit_trails(self) -> List[Dict[str, Any]]:
        self.session.expire_all()
        rows = (
            self.session.query(ProviderRoutingAuditV3ORM)
            .order_by(ProviderRoutingAuditV3ORM.created_at.desc())
            .all()
        )
        return [self._audit_to_dict(r) for r in rows]

    @staticmethod
    def _audit_to_dict(r: ProviderRoutingAuditV3ORM) -> Dict[str, Any]:
        return {
            "id": r.id,
            "action": r.action,
            "scope_type": r.scope_type,
            "scope_id": r.scope_id,
            "lock_id": r.lock_id,
            "canonical_model_id": r.canonical_model_id,
            "previous_canonical_model_id": r.previous_canonical_model_id,
            "new_canonical_model_id": r.new_canonical_model_id,
            "endpoint_id": r.endpoint_id,
            "reason": r.reason,
            "actor": r.actor,
            "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
            "created_at": r.created_at,
        }
