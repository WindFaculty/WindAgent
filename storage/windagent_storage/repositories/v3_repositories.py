"""
SQL concrete repository implementations for WindAgent Provider Routing Subsystem V3 ports.
Decouples domain logic from database drivers while satisfying Phase 1 port interfaces.
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from windagent_providers.base.contracts import (
    ModelDescriptor, ProviderCapabilities, QuotaState
)
from windagent_core.contracts.providers.ports import (
    CanonicalModelRegistryPort, EndpointRegistryPort, EndpointStatePort,
    QuotaStatePort, RouteAttemptPort, RouteLockPort, UsageLedgerPort
)
from storage.windagent_storage.orm.v3_models import (
    CanonicalModelV3ORM, EndpointModelBindingORM,
    EndpointRuntimeStateORM, ProviderEndpointORM,
    ProviderQuotaSnapshotV3ORM, ProviderUsageLedgerORM, RouteAttemptV3ORM, RouteLockV3ORM
)


class SQLEndpointRegistryRepository(EndpointRegistryPort):
    """SQL Implementation of EndpointRegistryPort."""

    def __init__(self, session: Session):
        self.session = session

    async def get_endpoint(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        ep = self.session.query(ProviderEndpointORM).filter_by(id=endpoint_id).first()
        if not ep:
            return None
        return {
            "id": ep.id,
            "vendor_id": ep.vendor_id,
            "credential_id": ep.credential_id,
            "base_url": ep.base_url,
            "protocol_mode": ep.protocol_mode,
            "configured_protocol": ep.configured_protocol,
            "detected_protocol": ep.detected_protocol,
            "protocol_confidence": ep.protocol_confidence,
            "priority": ep.priority,
            "enabled": ep.enabled,
        }

    async def list_endpoints_for_canonical_model(self, canonical_model_id: str) -> List[Dict[str, Any]]:
        bindings = self.session.query(EndpointModelBindingORM).filter_by(
            canonical_model_id=canonical_model_id, enabled=True
        ).order_by(EndpointModelBindingORM.priority.desc()).all()

        results = []
        for b in bindings:
            ep = self.session.query(ProviderEndpointORM).filter_by(id=b.endpoint_id, enabled=True).first()
            if ep:
                results.append({
                    "binding_id": b.id,
                    "endpoint_id": ep.id,
                    "canonical_model_id": b.canonical_model_id,
                    "provider_model_id": b.provider_model_id,
                    "model_revision": b.model_revision,
                    "equivalence_level": b.equivalence_level,
                    "base_url": ep.base_url,
                    "protocol_mode": ep.protocol_mode,
                    "priority": b.priority,
                })
        return results


class SQLCanonicalModelRegistryRepository(CanonicalModelRegistryPort):
    """SQL Implementation of CanonicalModelRegistryPort."""

    def __init__(self, session: Session):
        self.session = session

    async def get_canonical_model(self, canonical_model_id: str) -> Optional[ModelDescriptor]:
        model_orm = self.session.query(CanonicalModelV3ORM).filter_by(id=canonical_model_id).first()
        if not model_orm:
            return None
        return ModelDescriptor(
            model_id=model_orm.id,
            provider_id=model_orm.vendor,
            display_name=model_orm.canonical_name,
            vendor=model_orm.vendor,
            family=model_orm.family,
            revision=model_orm.revision,
            capabilities=ProviderCapabilities(
                max_context_window=model_orm.context_window or 128000
            )
        )

    async def list_canonical_models(self) -> List[ModelDescriptor]:
        models = self.session.query(CanonicalModelV3ORM).filter_by(enabled=True).all()
        return [
            ModelDescriptor(
                model_id=m.id,
                provider_id=m.vendor,
                display_name=m.canonical_name,
                vendor=m.vendor,
                family=m.family,
                revision=m.revision,
                capabilities=ProviderCapabilities(
                    max_context_window=m.context_window or 128000
                )
            ) for m in models
        ]


class SQLRouteLockRepository(RouteLockPort):
    """SQL Implementation of RouteLockPort guaranteeing single active lock per scope."""

    def __init__(self, session: Session):
        self.session = session

    async def get_lock(self, scope_type: str, scope_id: str) -> Optional[Dict[str, Any]]:
        lock = self.session.query(RouteLockV3ORM).filter_by(
            scope_type=scope_type, scope_id=scope_id, status="active"
        ).first()
        if not lock:
            return None
        return {
            "id": lock.id,
            "scope_type": lock.scope_type,
            "scope_id": lock.scope_id,
            "canonical_model_id": lock.canonical_model_id,
            "policy_version": lock.policy_version,
            "routing_snapshot": json.loads(lock.routing_snapshot_json) if lock.routing_snapshot_json else {},
            "status": lock.status,
            "created_at": lock.created_at,
        }

    async def create_lock(
        self,
        scope_type: str,
        scope_id: str,
        canonical_model_id: str,
        routing_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        # Atomic single active lock check
        existing = self.session.query(RouteLockV3ORM).filter_by(
            scope_type=scope_type, scope_id=scope_id, status="active"
        ).first()
        if existing:
            return await self.get_lock(scope_type, scope_id)

        lock_id = f"lock-{uuid.uuid4().hex[:12]}"
        lock = RouteLockV3ORM(
            id=lock_id,
            scope_type=scope_type,
            scope_id=scope_id,
            canonical_model_id=canonical_model_id,
            policy_version=1,
            routing_snapshot_json=json.dumps(routing_snapshot),
            status="active",
        )
        self.session.add(lock)
        self.session.flush()
        return {
            "id": lock.id,
            "scope_type": lock.scope_type,
            "scope_id": lock.scope_id,
            "canonical_model_id": lock.canonical_model_id,
            "policy_version": lock.policy_version,
            "routing_snapshot": routing_snapshot,
            "status": lock.status,
            "created_at": lock.created_at,
        }

    async def release_lock(self, lock_id: str) -> bool:
        lock = self.session.query(RouteLockV3ORM).filter_by(id=lock_id).first()
        if not lock or lock.status != "active":
            return False
        lock.status = "released"
        lock.released_at = datetime.now(timezone.utc)
        self.session.flush()
        return True


class SQLRouteAttemptRepository(RouteAttemptPort):
    """SQL Implementation of RouteAttemptPort."""

    def __init__(self, session: Session):
        self.session = session

    async def record_attempt(
        self,
        route_lock_id: str,
        turn_id: Optional[str],
        attempt_index: int,
        provider_binding_id: Optional[str],
        status: str,
        http_status: Optional[int] = None,
        error_class: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        endpoint_id: Optional[str] = None,
    ) -> str:
        attempt = RouteAttemptV3ORM(
            route_lock_id=route_lock_id,
            turn_id=turn_id,
            attempt_index=attempt_index,
            provider_binding_id=provider_binding_id,
            status=status,
            http_status=http_status,
            error_class=error_class,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finished_at=datetime.now(timezone.utc),
        )
        self.session.add(attempt)
        self.session.flush()
        return str(attempt.id)


class SQLQuotaStateRepository(QuotaStatePort):
    """SQL Implementation of QuotaStatePort."""

    def __init__(self, session: Session):
        self.session = session

    async def get_quota_state(self, provider_id: str) -> Optional[QuotaState]:
        snapshot = self.session.query(ProviderQuotaSnapshotV3ORM).filter_by(
            vendor_id=provider_id
        ).order_by(ProviderQuotaSnapshotV3ORM.created_at.desc()).first()

        if not snapshot:
            return QuotaState(provider_id=provider_id, has_quota=True)

        return QuotaState(
            provider_id=provider_id,
            has_quota=(snapshot.remaining_requests_today is None or snapshot.remaining_requests_today > 0),
            remaining_requests_today=snapshot.remaining_requests_today,
            remaining_tokens_today=snapshot.remaining_tokens_today,
            remaining_credit=snapshot.remaining_credit,
            credit_currency=snapshot.credit_currency,
            reset_at=snapshot.reset_at,
        )

    async def update_quota_state(self, provider_id: str, snapshot: QuotaState) -> None:
        orm = ProviderQuotaSnapshotV3ORM(
            vendor_id=provider_id,
            quota_mode="RPM_RPD",
            remaining_requests_today=snapshot.remaining_requests_today,
            remaining_tokens_today=snapshot.remaining_tokens_today,
            remaining_credit=snapshot.remaining_credit,
            credit_currency=snapshot.credit_currency,
            reset_at=snapshot.reset_at,
        )
        self.session.add(orm)
        self.session.flush()


class SQLEndpointStateRepository(EndpointStatePort):
    """SQL Implementation of EndpointStatePort."""

    def __init__(self, session: Session):
        self.session = session

    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        state = self.session.query(EndpointRuntimeStateORM).filter_by(endpoint_id=endpoint_id).first()
        if not state:
            state = EndpointRuntimeStateORM(
                endpoint_id=endpoint_id,
                consecutive_successes=0,
                consecutive_failures=0
            )
            self.session.add(state)

        state.consecutive_successes = (state.consecutive_successes or 0) + 1
        state.consecutive_failures = 0
        state.circuit_state = "closed"
        state.cooldown_until = None
        state.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    async def record_failure(self, endpoint_id: str, error_class: str, status_code: Optional[int]) -> None:
        state = self.session.query(EndpointRuntimeStateORM).filter_by(endpoint_id=endpoint_id).first()
        if not state:
            state = EndpointRuntimeStateORM(
                endpoint_id=endpoint_id,
                consecutive_failures=0,
                consecutive_successes=0
            )
            self.session.add(state)

        state.consecutive_failures = (state.consecutive_failures or 0) + 1
        state.consecutive_successes = 0
        state.last_failure_at = datetime.now(timezone.utc)
        state.last_error_class = error_class

        if status_code == 429:
            state.last_429_at = datetime.now(timezone.utc)

        if state.consecutive_failures >= 3:
            state.circuit_state = "open"

        state.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    async def set_cooldown(self, endpoint_id: str, cooldown_until: datetime) -> None:
        state = self.session.query(EndpointRuntimeStateORM).filter_by(endpoint_id=endpoint_id).first()
        if not state:
            state = EndpointRuntimeStateORM(endpoint_id=endpoint_id)
            self.session.add(state)

        state.cooldown_until = cooldown_until
        state.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    async def is_available(self, endpoint_id: str) -> bool:
        state = self.session.query(EndpointRuntimeStateORM).filter_by(endpoint_id=endpoint_id).first()
        if not state:
            return True

        if state.circuit_state == "open":
            return False

        if state.cooldown_until and state.cooldown_until > datetime.now(timezone.utc):
            return False

        return True


class SQLUsageLedgerRepository(UsageLedgerPort):
    """SQL Implementation of UsageLedgerPort."""

    def __init__(self, session: Session):
        self.session = session

    async def log_usage(
        self,
        canonical_model_id: str,
        provider_model_id: str,
        endpoint_id: Optional[str],
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        cost_usd: float,
    ) -> None:
        record = ProviderUsageLedgerORM(
            canonical_model_id=canonical_model_id,
            provider_model_id=provider_model_id,
            endpoint_id=endpoint_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )
        self.session.add(record)
        self.session.flush()
