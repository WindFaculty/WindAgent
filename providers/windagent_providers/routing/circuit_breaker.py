"""
Endpoint State Manager for WindAgent Provider Routing Phase 8.

Implements in-memory cooldown, failure tracking, success tracking, and a simple
circuit breaker per endpoint.  This is the default development implementation;
production wiring can swap in a Redis-backed `EndpointStatePort` adapter without
changing caller code.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from windagent_core.contracts.providers.ports import EndpointStatePort


@dataclass
class _EndpointState:
    """Mutable state record for a single endpoint."""

    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    circuit_open_until: float = 0.0
    last_latency_ms: float = 0.0
    last_success_at: Optional[float] = None
    last_failure_at: Optional[float] = None


class InMemoryEndpointStateManager(EndpointStatePort):
    """
    Thread-safe in-memory endpoint state manager.

    Circuit breaker rules (configurable on construction):
        * failure_threshold: consecutive failures before opening circuit.
        * half_open_timeout_seconds: how long circuit stays open before half-open.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        half_open_timeout_seconds: float = 30.0,
    ):
        self._failure_threshold = max(1, failure_threshold)
        self._half_open_timeout_seconds = half_open_timeout_seconds
        self._states: Dict[str, _EndpointState] = {}
        self._mutex = threading.Lock()

    def _get_or_create(self, endpoint_id: str) -> _EndpointState:
        with self._mutex:
            if endpoint_id not in self._states:
                self._states[endpoint_id] = _EndpointState()
            return self._states[endpoint_id]

    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        state = self._get_or_create(endpoint_id)
        with self._mutex:
            now = time.time()
            state.success_count += 1
            state.consecutive_failures = 0
            state.last_latency_ms = latency_ms
            state.last_success_at = now
            # Closing circuit on success in half-open state.
            state.circuit_open_until = 0.0

    async def record_failure(
        self,
        endpoint_id: str,
        error_class: str,
        status_code: Optional[int] = None,
    ) -> None:
        state = self._get_or_create(endpoint_id)
        with self._mutex:
            now = time.time()
            state.failure_count += 1
            state.consecutive_failures += 1
            state.last_failure_at = now

            if state.consecutive_failures >= self._failure_threshold:
                state.circuit_open_until = now + self._half_open_timeout_seconds

    async def set_cooldown(self, endpoint_id: str, cooldown_until: datetime) -> None:
        state = self._get_or_create(endpoint_id)
        with self._mutex:
            timestamp = cooldown_until.timestamp()
            if timestamp > state.cooldown_until:
                state.cooldown_until = timestamp

    async def is_available(self, endpoint_id: str) -> bool:
        state = self._get_or_create(endpoint_id)
        now = time.time()
        with self._mutex:
            if now < state.cooldown_until:
                return False
            if now < state.circuit_open_until:
                return False
            return True

    def apply_rate_limit_cooldown(
        self,
        endpoint_id: str,
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        """Synchronous helper to set 429 cooldown (used by execution coordinator)."""
        seconds = retry_after_seconds or 1.0
        until = datetime.now(timezone.utc).timestamp() + seconds
        state = self._get_or_create(endpoint_id)
        with self._mutex:
            state.cooldown_until = max(state.cooldown_until, until)

    def open_circuit(self, endpoint_id: str) -> None:
        """Synchronous helper to open circuit (used by execution coordinator)."""
        state = self._get_or_create(endpoint_id)
        with self._mutex:
            state.circuit_open_until = time.time() + self._half_open_timeout_seconds

    async def get_state(self, endpoint_id: str) -> _EndpointState:
        return self._get_or_create(endpoint_id)
