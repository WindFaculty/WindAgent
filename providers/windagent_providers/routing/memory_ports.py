"""
In-memory implementations of routing support ports for WindAgent Provider Phase 8.

These adapters satisfy the `EndpointRegistryPort`, `QuotaStatePort`, and
`RouteAttemptPort` contracts without SQLAlchemy, FastAPI, Redis, or apps code.
Production can swap them out for persistent adapters at composition time.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_providers.base.contracts import QuotaState
from windagent_providers.base.ports import EndpointRegistryPort, QuotaStatePort, RouteAttemptPort


@dataclass
class _EndpointBinding:
    endpoint_id: str
    binding_id: str
    canonical_model_id: str
    provider_model_id: str
    provider_name: str
    base_url: str
    credential_ciphertext: Optional[str]
    equivalence_level: str
    is_active: bool = True


class InMemoryEndpointRegistry(EndpointRegistryPort):
    """In-memory registry of endpoint bindings, seeded by caller."""

    def __init__(self, bindings: Optional[List[Dict[str, Any]]] = None):
        self._bindings: List[_EndpointBinding] = []
        self._mutex = threading.Lock()
        for b in bindings or []:
            self.register_binding(b)

    def register_binding(self, binding: Dict[str, Any]) -> None:
        with self._mutex:
            self._bindings.append(
                _EndpointBinding(
                    endpoint_id=binding["endpoint_id"],
                    binding_id=binding.get("binding_id", f"bnd-{uuid.uuid4().hex[:8]}"),
                    canonical_model_id=binding["canonical_model_id"],
                    provider_model_id=binding["provider_model_id"],
                    provider_name=binding["provider_name"],
                    base_url=binding["base_url"],
                    credential_ciphertext=binding.get("credential_ciphertext"),
                    equivalence_level=binding.get("equivalence_level", "exact_revision"),
                    is_active=binding.get("is_active", True),
                )
            )

    async def get_endpoint(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        with self._mutex:
            for b in self._bindings:
                if b.endpoint_id == endpoint_id and b.is_active:
                    return self._binding_to_dict(b)
        return None

    async def list_endpoints_for_canonical_model(self, canonical_model_id: str) -> List[Dict[str, Any]]:
        with self._mutex:
            return [
                self._binding_to_dict(b)
                for b in self._bindings
                if b.canonical_model_id == canonical_model_id and b.is_active
            ]

    def _binding_to_dict(self, binding: _EndpointBinding) -> Dict[str, Any]:
        return {
            "endpoint_id": binding.endpoint_id,
            "binding_id": binding.binding_id,
            "canonical_model_id": binding.canonical_model_id,
            "provider_model_id": binding.provider_model_id,
            "provider_name": binding.provider_name,
            "base_url": binding.base_url,
            "credential_ciphertext": binding.credential_ciphertext,
            "equivalence_level": binding.equivalence_level,
            "is_active": binding.is_active,
        }


class InMemoryQuotaStateManager(QuotaStatePort):
    """In-memory quota snapshot store."""

    def __init__(self, states: Optional[Dict[str, QuotaState]] = None):
        self._states: Dict[str, QuotaState] = dict(states or {})
        self._mutex = threading.Lock()

    async def get_quota_state(self, provider_id: str) -> Optional[QuotaState]:
        with self._mutex:
            return self._states.get(provider_id)

    async def update_quota_state(self, provider_id: str, snapshot: QuotaState) -> None:
        with self._mutex:
            self._states[provider_id] = snapshot


class InMemoryRouteAttemptLog(RouteAttemptPort):
    """In-memory route attempt audit log used by the execution coordinator."""

    def __init__(self):
        self._records: List[Dict[str, Any]] = []
        self._mutex = threading.Lock()

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
        attempt_id = f"att-{uuid.uuid4().hex[:8]}"
        record = {
            "attempt_id": attempt_id,
            "route_lock_id": route_lock_id,
            "turn_id": turn_id,
            "attempt_index": attempt_index,
            "provider_binding_id": provider_binding_id,
            "endpoint_id": endpoint_id,
            "status": status,
            "http_status": http_status,
            "error_class": error_class,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "created_at": time.time(),
        }
        with self._mutex:
            self._records.append(record)
        return attempt_id

    def all_records(self) -> List[Dict[str, Any]]:
        with self._mutex:
            return list(self._records)
