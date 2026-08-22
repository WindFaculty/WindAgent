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

from windagent_core.contracts.providers.capabilities import DiscoveredModel
from windagent_core.contracts.providers.model_normalizer import normalize_model_id
from windagent_core.contracts.providers.equivalence import (
    classify_equivalence,
    EquivalenceLevel,
)
from windagent_core.contracts.repositories.routing_repository import (
    EndpointBindingRepositoryPort,
    RoutingAuditRepositoryPort,
)
from windagent_storage.orm.v3_models import (
    CanonicalModelV3ORM,
    EndpointModelBindingORM,
    ModelRouteReceiptV3ORM,
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
        self.session.flush()
        self.session.commit()
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
                self.session.flush()
                self.session.commit()
            results.append(self._binding_to_dict(binding))
        return results

    def reconcile_discovery_snapshot(
        self, endpoint_id: str, discovered_models: List[DiscoveredModel]
    ) -> Dict[str, Any]:
        """P0.2.4 — classify one sync into ADDED/UPDATED/UNCHANGED/UNAVAILABLE.

        A model missing from one discovery pass is marked ``unavailable`` and
        NEVER deleted. Rediscovering it later flips it back to ``active``.
        Pricing is persisted only from provider-advertised values; anything
        else stays ``UNKNOWN``.
        """
        from windagent_core.contracts.providers.capabilities import (
            classify_pricing_class,
        )

        now = datetime.now(timezone.utc)
        added: List[str] = []
        updated: List[str] = []
        unchanged: List[str] = []
        discovered_raw_ids = {disc.raw_model_id for disc in discovered_models}

        for disc in discovered_models:
            norm = normalize_model_id(disc.raw_model_id, default_vendor=disc.provider_id)
            canonical = self._find_or_create_canonical(norm)
            norm_c = normalize_model_id(canonical.canonical_name, default_vendor=canonical.vendor)
            assessment = classify_equivalence(norm, norm_c)

            pricing_class = classify_pricing_class(disc.pricing_prompt, disc.pricing_completion)
            try:
                input_price = float(str(disc.pricing_prompt)) if disc.pricing_prompt is not None else None
                output_price = float(str(disc.pricing_completion)) if disc.pricing_completion is not None else None
            except (TypeError, ValueError):
                input_price = None
                output_price = None

            binding = (
                self.session.query(EndpointModelBindingORM)
                .filter_by(
                    endpoint_id=endpoint_id,
                    canonical_model_id=canonical.id,
                    provider_model_id=disc.raw_model_id,
                )
                .first()
            )
            if binding is None:
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
                    availability="active",
                    pricing_class=pricing_class,
                    input_price=input_price,
                    output_price=output_price,
                    currency="USD" if input_price is not None else None,
                    last_discovered_at=now,
                )
                self.session.add(binding)
                added.append(disc.raw_model_id)
            else:
                changed = (
                    binding.availability != "active"
                    or binding.equivalence_level != assessment.level.value
                    or binding.pricing_class != pricing_class
                    or binding.input_price != input_price
                    or binding.output_price != output_price
                )
                binding.availability = "active"
                binding.enabled = True
                binding.equivalence_level = assessment.level.value
                binding.pricing_class = pricing_class
                binding.input_price = input_price
                binding.output_price = output_price
                binding.currency = "USD" if input_price is not None else None
                binding.last_discovered_at = now
                binding.updated_at = now
                if changed:
                    updated.append(disc.raw_model_id)
                else:
                    unchanged.append(disc.raw_model_id)

        # Active bindings NOT seen in this pass become unavailable — never
        # deleted; already-unavailable rows stay as-is without re-counting.
        unavailable: List[str] = []
        for row in (
            self.session.query(EndpointModelBindingORM)
            .filter_by(endpoint_id=endpoint_id, availability="active")
            .all()
        ):
            if row.provider_model_id not in discovered_raw_ids:
                row.availability = "unavailable"
                row.enabled = False
                row.updated_at = now
                unavailable.append(row.provider_model_id)

        self.session.flush()
        self.session.commit()
        return {
            "added": added,
            "updated": updated,
            "unchanged": unchanged,
            "unavailable": unavailable,
        }

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
        self.session.flush()
        self.session.commit()
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
        self.session.flush()
        self.session.commit()
        binding.canonical_model_id = new_cm.id
        binding.equivalence_level = EquivalenceLevel.EXACT_REVISION.value
        binding.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.commit()
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
            "availability": getattr(b, "availability", "active"),
            "pricing_class": getattr(b, "pricing_class", "UNKNOWN"),
            "input_price": getattr(b, "input_price", None),
            "output_price": getattr(b, "output_price", None),
            "currency": getattr(b, "currency", None),
            "last_discovered_at": (
                b.last_discovered_at.isoformat()
                if getattr(b, "last_discovered_at", None) else None
            ),
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
        from windagent_core.security.redaction import redact_before_persist

        # Phase 1 (G9.4): audit metadata is redacted before it is persisted.
        safe_metadata = redact_before_persist(metadata or {})
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
            metadata_json=json.dumps(safe_metadata),
        )
        self.session.add(row)
        self.session.flush()
        self.session.commit()
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


class SQLCanonicalModelRepository:
    """SQL-backed canonical model repository."""

    def __init__(self, session: Session):
        self.session = session

    def get_canonical_model(self, canonical_model_id: str) -> Optional[Dict[str, Any]]:
        row = self.session.query(CanonicalModelV3ORM).filter_by(id=canonical_model_id).first()
        return self._to_dict(row) if row else None

    def list_canonical_models(self) -> List[Dict[str, Any]]:
        rows = self.session.query(CanonicalModelV3ORM).all()
        return [self._to_dict(r) for r in rows]

    def save_canonical_model(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        cm_id = model_data.get("id") or f"cm-{uuid.uuid4().hex[:12]}"
        existing = self.session.query(CanonicalModelV3ORM).filter_by(id=cm_id).first()
        if existing:
            existing.vendor = model_data.get("vendor", existing.vendor)
            existing.family = model_data.get("family", existing.family)
            existing.canonical_name = model_data.get("canonical_name", existing.canonical_name)
            existing.revision = model_data.get("revision", existing.revision)
            existing.context_window = model_data.get("context_window", existing.context_window)
            row = existing
        else:
            row = CanonicalModelV3ORM(
                id=cm_id,
                vendor=model_data.get("vendor", "custom"),
                family=model_data.get("family", model_data.get("canonical_name", "unknown")),
                canonical_name=model_data.get("canonical_name", cm_id),
                revision=model_data.get("revision", "latest"),
                context_window=model_data.get("context_window", 128000),
            )
            self.session.add(row)
        self.session.flush()
        self.session.commit()
        return self._to_dict(row)

    @staticmethod
    def _to_dict(r: CanonicalModelV3ORM) -> Dict[str, Any]:
        return {
            "id": r.id,
            "vendor": r.vendor,
            "family": r.family,
            "canonical_name": r.canonical_name,
            "revision": r.revision,
            "context_window": r.context_window,
            "enabled": r.enabled,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }


class SQLRouteAttemptRepository:
    """SQL-backed route attempt repository for recording failover and attempt tracking."""

    def __init__(self, session: Session):
        self.session = session

    def record_attempt(
        self,
        lock_id: str,
        endpoint_id: Optional[str],
        provider_model_id: Optional[str],
        attempt_number: int,
        status: str,
        failure_category: Optional[str] = None,
        retry_after: Optional[float] = None,
        started_at: Optional[float] = None,
        finished_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        from windagent_storage.orm.v3_models import RouteAttemptV3ORM

        row = RouteAttemptV3ORM(
            route_lock_id=lock_id,
            attempt_index=attempt_number,
            status=status,
            error_class=failure_category,
        )
        self.session.add(row)
        self.session.flush()
        self.session.commit()
        return {
            "id": row.id,
            "route_lock_id": row.route_lock_id,
            "attempt_number": row.attempt_index,
            "status": row.status,
            "failure_category": row.error_class,
            "started_at": row.started_at,
        }

    def get_attempts_for_lock(self, lock_id: str) -> List[Dict[str, Any]]:
        from windagent_storage.orm.v3_models import RouteAttemptV3ORM

        rows = self.session.query(RouteAttemptV3ORM).filter_by(route_lock_id=lock_id).all()
        return [
            {
                "id": r.id,
                "route_lock_id": r.route_lock_id,
                "attempt_number": r.attempt_index,
                "status": r.status,
                "failure_category": r.error_class,
                "started_at": r.started_at,
            }
            for r in rows
        ]


class SQLModelRouteReceiptRepository:
    """Durable per-task route receipts (P0.3.6).

    One row per LLM task executed through the model router: which rule
    resolved, which provider/model served it, whether the declared fallback
    was used and why, and the exact execution window. This is the debugging
    authority for story-quality investigations — never fabricated, only
    written by the real executor.
    """

    def __init__(self, session: Session):
        self.session = session

    def record_receipt(
        self,
        *,
        task_id: str,
        role: str,
        rule_id: str,
        route_lock_id: str,
        selected_provider: Optional[str],
        selected_model_id: str,
        provider_model_id: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        fallback_used: bool = False,
        fallback_reason: Optional[str] = None,
        status: str = "success",
        error_code: Optional[str] = None,
        started_at: datetime,
        completed_at: datetime,
    ) -> str:
        row = ModelRouteReceiptV3ORM(
            id=f"rcpt-{uuid.uuid4().hex[:16]}",
            task_id=task_id[:128],
            role=(role or "")[:128],
            rule_id=(rule_id or "")[:128],
            route_lock_id=route_lock_id,
            selected_provider=(selected_provider or None),
            selected_model_id=selected_model_id[:128],
            provider_model_id=(provider_model_id or None),
            endpoint_id=(endpoint_id or None),
            fallback_used=bool(fallback_used),
            fallback_reason=fallback_reason,
            status=status if status in {"success", "failed"} else "failed",
            error_code=error_code,
            started_at=started_at,
            completed_at=completed_at,
        )
        self.session.add(row)
        self.session.flush()
        self.session.commit()
        return str(row.id)

    def list_receipts(
        self,
        *,
        task_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        self.session.expire_all()
        query = self.session.query(ModelRouteReceiptV3ORM)
        if task_id:
            query = query.filter(ModelRouteReceiptV3ORM.task_id == task_id)
        if role:
            query = query.filter(ModelRouteReceiptV3ORM.role == role)
        rows = (
            query.order_by(ModelRouteReceiptV3ORM.created_at.desc())
            .limit(max(1, min(int(limit), 500)))
            .all()
        )
        return [self._to_dict(r) for r in rows]

    def count_receipts(self) -> int:
        return int(self.session.query(ModelRouteReceiptV3ORM).count())

    @staticmethod
    def _to_dict(r: ModelRouteReceiptV3ORM) -> Dict[str, Any]:
        return {
            "id": r.id,
            "task_id": r.task_id,
            "role": r.role,
            "rule_id": r.rule_id,
            "route_lock_id": r.route_lock_id,
            "selected_provider": r.selected_provider,
            "selected_model_id": r.selected_model_id,
            "provider_model_id": r.provider_model_id,
            "endpoint_id": r.endpoint_id,
            "fallback_used": bool(r.fallback_used),
            "fallback_reason": r.fallback_reason,
            "status": r.status,
            "error_code": r.error_code,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }


class SQLRoutingUnitOfWork:
    """SQL-backed transactional Unit of Work scope for routing operations."""

    def __init__(self, session: Session):
        self.session = session

    def __enter__(self) -> "SQLRoutingUnitOfWork":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.rollback()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


from windagent_storage.repositories.v3_repositories import SQLRouteLockRepository  # noqa: E402  (bottom import to avoid repo cycle)

# Exact class aliases matching ban_ke_hoach.md §1.3
SqlCanonicalModelRepository = SQLCanonicalModelRepository
SqlEndpointBindingRepository = SQLEndpointBindingRepository
SqlRouteLockRepository = SQLRouteLockRepository
SqlRouteAttemptRepository = SQLRouteAttemptRepository
SqlProviderRoutingAuditRepository = SQLProviderRoutingAuditRepository
SqlModelRouteReceiptRepository = SQLModelRouteReceiptRepository
SqlRoutingUnitOfWork = SQLRoutingUnitOfWork

