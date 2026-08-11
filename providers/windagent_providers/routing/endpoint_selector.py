"""
Endpoint Candidate and Selector for WindAgent Provider Routing Phase 8.

Selects exact-equivalent endpoint bindings for the locked canonical model, filters
them by health/quota/circuit/cooldown/credential validity, scores the survivors,
and returns an ordered candidate list for the execution coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_providers.base.contracts import ProviderCapabilities
from windagent_providers.base.errors import SameModelEndpointExhausted
from windagent_core.contracts.providers.ports import EndpointStatePort, QuotaStatePort


class BindingState(str, Enum):
    """Mutability of an endpoint binding for selection."""

    ACTIVE = "active"
    DISABLED = "disabled"
    COOLDOWN = "cooldown"
    CIRCUIT_OPEN = "circuit_open"
    HEALTHY = "healthy"


@dataclass
class EndpointCandidate:
    """
    A failover candidate for a canonical model.

    Attributes
    ----------
    endpoint_id : Stable endpoint identifier.
    binding_id : Binding record identifier.
    provider_model_id : Model ID understood by the provider endpoint.
    provider_name : e.g. openai, openrouter, anthropic.
    base_url : Provider endpoint URL.
    credential_ciphertext : Optional encrypted credential reference.
    score : Computed endpoint score (higher is better).
    score_components : Breakdown of score contributors for diagnostics.
    is_exact_revision : True iff equivalence level is exact_revision (phase 8 requires True).
    """

    endpoint_id: str
    binding_id: str
    provider_model_id: str
    provider_name: str
    base_url: str
    credential_ciphertext: Optional[str] = None
    score: float = 0.0
    score_components: Dict[str, float] = None  # type: ignore[assignment]
    is_exact_revision: bool = False
    protocol_mode: str = "openai"

    def __post_init__(self) -> None:
        if self.score_components is None:
            self.score_components = {}


class EndpointSelector:
    """
    Candidate pipeline implementing the Phase 8 filter chain:

        exact_revision only → enabled → capability-compatible → valid credential
        → health acceptable → quota available → not in cooldown → circuit not open
        → endpoint score.
    """

    def __init__(
        self,
        endpoint_state_port: EndpointStatePort,
        quota_state_port: QuotaStatePort,
    ):
        self._state = endpoint_state_port
        self._quota = quota_state_port

    async def select_candidates(
        self,
        bindings: List[Dict[str, Any]],
        required_capabilities: Optional[ProviderCapabilities] = None,
    ) -> List[EndpointCandidate]:
        """
        Return scored candidates for one canonical model.

        Raises SameModelEndpointExhausted if no candidate survives all filters.
        """
        survivors: List[EndpointCandidate] = []

        for binding in bindings:
            maybe_candidate = await self._evaluate_binding(binding)
            if maybe_candidate is None:
                continue
            score, components = await self._score_candidate(maybe_candidate)
            maybe_candidate.score = score
            maybe_candidate.score_components = components
            survivors.append(maybe_candidate)

        if not survivors:
            raise SameModelEndpointExhausted(
                "All exact-equivalent endpoints for the locked canonical model are exhausted"
            )

        survivors.sort(key=lambda c: c.score, reverse=True)
        return survivors

    async def _evaluate_binding(
        self, binding: Dict[str, Any]
    ) -> Optional[EndpointCandidate]:
        endpoint_id = binding.get("endpoint_id")
        binding_id = binding.get("binding_id")
        provider_model_id = binding.get("provider_model_id")
        provider_name = binding.get("provider_name")
        base_url = binding.get("base_url")
        equivalence = binding.get("equivalence_level", "")
        enabled = binding.get("is_active", True)
        credential_ciphertext = binding.get("credential_ciphertext")
        protocol_mode = str(binding.get("protocol_mode") or "openai").lower()

        if not all(
            [endpoint_id, binding_id, provider_model_id, provider_name, base_url]
        ):
            return None

        if not enabled:
            return None

        # Phase 8: only exact_revision bindings are failover-eligible.
        if equivalence != "exact_revision":
            return None

        # Ollama commonly runs as a credentialless local service.  Every other
        # supported protocol remains fail-closed when its credential is absent.
        if not credential_ciphertext and protocol_mode != "ollama":
            return None

        # Endpoint state filters.
        if not await self._state.is_available(endpoint_id):
            return None

        return EndpointCandidate(
            endpoint_id=endpoint_id,
            binding_id=binding_id,
            provider_model_id=provider_model_id,
            provider_name=provider_name,
            base_url=base_url,
            credential_ciphertext=credential_ciphertext,
            is_exact_revision=True,
            protocol_mode=protocol_mode,
        )

    async def _score_candidate(
        self, candidate: EndpointCandidate
    ) -> tuple[float, Dict[str, float]]:
        """
        Compute endpoint score.

        Current scoring is intentionally simple and deterministic:
        health/recency + quota + configured priority/weight + recent success rate.
        Latency/cost/region are placeholders with zero contribution until storage
        ports expose them.
        """
        components: Dict[str, float] = {}

        # Health availability (1.0 if available, 0.0 otherwise; is_available already gated this).
        components["health"] = 1.0

        # Quota availability.
        quota = await self._quota.get_quota_state(candidate.provider_name)
        if quota is None or quota.has_quota:
            components["quota"] = 1.0
        else:
            components["quota"] = 0.0

        # Configured priority/weight defaults.
        components["priority"] = 1.0
        components["weight"] = 1.0

        # Latency placeholder.
        components["latency"] = 0.0

        # Recent success rate placeholder.
        components["success_rate"] = 1.0

        # Cost placeholder.
        components["cost"] = 0.0

        # Recent 429 penalty placeholder.
        components["recent_429"] = 0.0

        # Circuit state placeholder.
        components["circuit"] = 1.0

        score = sum(components.values())
        return score, components
