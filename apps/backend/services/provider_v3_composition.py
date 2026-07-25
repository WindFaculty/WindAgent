"""DB-backed port adapters for the Provider V3 subsystem.

Lives in apps/backend so provider package stays free of ORM/FastAPI.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from db.database import Database
from db.models import (
    ModelProviderORM,
    ProviderModelBindingORM,
    RouteAttemptORM,
    RouteLockORM,
)
from services.quota_service import QuotaService
from windagent_providers.base.contracts import QuotaState
from windagent_core.contracts.providers.ports import (
    EndpointRegistryPort,
    QuotaStatePort,
    RouteAttemptPort,
    RouteLockPort,
)


class DbEndpointRegistry(EndpointRegistryPort):
    """Map canonical model bindings from SQLAlchemy to V3 endpoint dicts."""

    def __init__(self, db: Database):
        self.db = db

    async def get_endpoint(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        async with self.db.session() as session:
            stmt = (
                select(ProviderModelBindingORM, ModelProviderORM)
                .join(
                    ModelProviderORM,
                    ProviderModelBindingORM.provider_id == ModelProviderORM.id,
                )
                .where(ProviderModelBindingORM.id == endpoint_id)
            )
            row = (await session.execute(stmt)).first()
            if not row:
                return None
            return self._to_dict(*row)

    async def list_endpoints_for_canonical_model(
        self, canonical_model_id: str
    ) -> List[Dict[str, Any]]:
        async with self.db.session() as session:
            stmt = (
                select(ProviderModelBindingORM, ModelProviderORM)
                .join(
                    ModelProviderORM,
                    ProviderModelBindingORM.provider_id == ModelProviderORM.id,
                )
                .where(ProviderModelBindingORM.canonical_model_id == canonical_model_id)
                .where(ProviderModelBindingORM.enabled.is_(True))
                .where(ModelProviderORM.enabled.is_(True))
                .order_by(ProviderModelBindingORM.priority.asc())
            )
            rows = (await session.execute(stmt)).all()
            return [self._to_dict(binding, provider) for binding, provider in rows]

    def _to_dict(
        self, binding: ProviderModelBindingORM, provider: ModelProviderORM
    ) -> Dict[str, Any]:
        return {
            "endpoint_id": binding.id,
            "binding_id": binding.id,
            "canonical_model_id": binding.canonical_model_id,
            "provider_model_id": binding.provider_model_id,
            "provider_name": provider.api_source or provider.id,
            "base_url": provider.base_url or "",
            # Store encrypted key reference; adapter resolver will decrypt.
            "credential_ciphertext": provider.api_key or "",
            "equivalence_level": "exact_revision"
            if binding.equivalence_level == "exact_revision"
            else "approximate",
            "is_active": binding.enabled and provider.enabled,
            "_provider_id": provider.id,
            "_api_key_env": provider.api_key_env,
        }


class DbQuotaStatePort(QuotaStatePort):
    """Bridge legacy QuotaService to V3 QuotaStatePort."""

    def __init__(self, quota_service: QuotaService):
        self._quota = quota_service

    async def get_quota_state(self, provider_id: str) -> Optional[QuotaState]:
        snapshot = await self._quota.get_latest_quota(provider_id)
        if not snapshot:
            return None
        return QuotaState(
            provider_id=snapshot.provider_id,
            has_quota=(
                snapshot.remaining_requests_today is None
                or snapshot.remaining_requests_today > 0
            )
            and (
                snapshot.remaining_tokens_today is None
                or snapshot.remaining_tokens_today > 0
            ),
            remaining_requests_today=snapshot.remaining_requests_today,
            remaining_tokens_today=snapshot.remaining_tokens_today,
            remaining_credit=snapshot.remaining_credit,
            reset_at=snapshot.reset_at,
        )

    async def update_quota_state(self, provider_id: str, snapshot: QuotaState) -> None:
        await self._quota.update_quota_snapshot(
            provider_id=provider_id,
            quota_mode="RPM_RPD",
            remaining_requests_today=snapshot.remaining_requests_today,
            remaining_tokens_today=snapshot.remaining_tokens_today,
            remaining_credit=snapshot.remaining_credit,
            reset_at=snapshot.reset_at,
            source="v3_adapter",
        )


class DbRouteLockPort(RouteLockPort):
    """Persistent route lock storage.  DB is source of truth."""

    def __init__(self, db: Database):
        self.db = db

    async def get_lock(
        self, scope_type: str, scope_id: str
    ) -> Optional[Dict[str, Any]]:
        async with self.db.session() as session:
            stmt = (
                select(RouteLockORM)
                .where(RouteLockORM.scope_type == scope_type)
                .where(RouteLockORM.scope_id == scope_id)
                .where(RouteLockORM.status == "active")
            )
            res = await session.execute(stmt)
            row = res.scalar_one_or_none()
            if not row:
                return None
            return self._to_dict(row)

    async def create_lock(
        self,
        scope_type: str,
        scope_id: str,
        canonical_model_id: str,
        routing_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        async with self.db.session() as session:
            lock_id = f"lk-{uuid.uuid4().hex[:10]}"
            record = RouteLockORM(
                id=lock_id,
                scope_type=scope_type,
                scope_id=scope_id,
                canonical_model_id=canonical_model_id,
                routing_snapshot_json=json.dumps(routing_snapshot),
                status="active",
            )
            session.add(record)
            await session.commit()
            return self._to_dict(record)

    async def release_lock(self, lock_id: str) -> bool:
        async with self.db.session() as session:
            stmt = select(RouteLockORM).where(RouteLockORM.id == lock_id)
            res = await session.execute(stmt)
            row = res.scalar_one_or_none()
            if not row or row.status != "active":
                return False
            row.status = "released"
            row.released_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    def _to_dict(self, row: RouteLockORM) -> Dict[str, Any]:
        return {
            "lock_id": row.id,
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "canonical_model_id": row.canonical_model_id,
            "routing_snapshot": json.loads(row.routing_snapshot_json or "{}"),
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


class DbRouteAttemptPort(RouteAttemptPort):
    """Persist provider execution attempts."""

    def __init__(self, db: Database):
        self.db = db

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
        async with self.db.session() as session:
            record = RouteAttemptORM(
                route_lock_id=route_lock_id,
                turn_id=turn_id,
                attempt_index=attempt_index,
                provider_binding_id=provider_binding_id or endpoint_id,
                status=status,
                http_status=http_status,
                error_class=error_class,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            session.add(record)
            await session.commit()
            # scalar PK autoincrement is int; return as string
            return str(record.id)
