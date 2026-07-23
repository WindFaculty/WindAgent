"""V3 routing coordinator for the backend.

Selects canonical model via route-lock first turn, then runs the V3 execution
engine with legacy clients as adapters.  Falls back to legacy router when V3
execute flag is off.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_providers.base.contracts import ProviderRequest
from windagent_providers.routing.circuit_breaker import InMemoryEndpointStateManager
from windagent_providers.routing.endpoint_selector import EndpointSelector
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.routing.rules import RoutingRuleSet

from db.database import Database
from services.provider_v3_adapter import LegacyClientV3Adapter
from services.provider_v3_composition import (
    DbEndpointRegistry,
    DbQuotaStatePort,
    DbRouteAttemptPort,
    DbRouteLockPort,
)
from services.quota_service import QuotaService


class ProviderV3Coordinator:
    """Backend facade over Provider V3 routing + execution."""

    def __init__(
        self,
        db: Database,
        quota_service: QuotaService,
        model_service: Any,
        ruleset: Optional[RoutingRuleSet] = None,
    ):
        self.db = db
        self._model_service = model_service
        self._registry = DbEndpointRegistry(db)
        self._quota = DbQuotaStatePort(quota_service)
        self._state = InMemoryEndpointStateManager()
        self._attempts = DbRouteAttemptPort(db)
        self._route_lock_port = DbRouteLockPort(db)
        self._coordinator = EndpointExecutionCoordinator(
            adapter_resolver=self._resolve_adapter,
            endpoint_registry=self._registry,
            endpoint_state=self._state,
            quota_state=self._quota,
            attempt_log=self._attempts,
        )

    def _resolve_adapter(self, candidate: Any) -> LegacyClientV3Adapter:
        class _FakeProvider:
            pass
        fake = _FakeProvider()
        fake.id = getattr(candidate, "_provider_id", candidate.provider_name)
        fake.api_source = candidate.provider_name
        fake.base_url = candidate.base_url or ""
        fake.api_key = getattr(candidate, "credential_ciphertext", None)
        fake.api_key_env = getattr(candidate, "_api_key_env", None)
        fake.provider_type = "cloud"
        fake.quota_mode = "RPM_RPD"
        fake.enabled = True
        client = self._model_service.get_provider_client(fake)
        return LegacyClientV3Adapter(
            provider_name=candidate.provider_name,
            client=client,
            model_id=candidate.provider_model_id,
        )

    async def _resolve_canonical_and_lock(
        self, role: str, scope: str
    ) -> tuple[str, Dict[str, Any]]:
        lock = await self._route_lock_port.get_lock("role", scope)
        if lock:
            return lock["canonical_model_id"], lock

        # First turn: use legacy routing to pick canonical model, then persist lock.
        rules = await self._model_service.routing_service.get_routing_rules()
        mapping = rules.get(role)
        if not mapping:
            raise ValueError(f"No routing rule for role {role}")
        canonical_model_id = mapping.get("primary") or mapping.get("fallback")
        if not canonical_model_id:
            raise ValueError(f"No canonical model for role {role}")
        lock = await self._route_lock_port.create_lock(
            "role",
            scope,
            canonical_model_id,
            routing_snapshot={"role": role, "rule": mapping},
        )
        return canonical_model_id, lock

    async def execute_chat(
        self,
        role: str,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 1024,
        scope_id: Optional[str] = None,
    ) -> str:
        scope = scope_id or "_global_"
        canonical_model_id, lock = await self._resolve_canonical_and_lock(role, scope)
        request = ProviderRequest(
            messages=messages,
            max_output_tokens=max_tokens,
        )
        lock_dict = {
            "lock_id": lock.get("lock_id", ""),
            "canonical_model_id": canonical_model_id,
            "scope": "role",
            "scope_id": scope,
        }
        response = await self._coordinator.execute(request, lock_dict, turn_id=scope)
        return response.text or ""

    async def execute_chat_stream(
        self,
        role: str,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 1024,
        scope_id: Optional[str] = None,
    ):
        scope = scope_id or "_global_"
        canonical_model_id, lock = await self._resolve_canonical_and_lock(role, scope)
        request = ProviderRequest(
            messages=messages,
            max_output_tokens=max_tokens,
        )
        lock_dict = {
            "lock_id": lock.get("lock_id", ""),
            "canonical_model_id": canonical_model_id,
            "scope": "role",
            "scope_id": scope,
        }
        async for event in self._coordinator.execute_stream(request, lock_dict, turn_id=scope):
            yield event
