"""Endpoint selection over the durable store.

The application half of the frozen ``endpoint_selector``: the pure filter
chain and scoring live in ``domain.selection``; this service loads runtime
state (circuit/cooldown and quota) and applies the same chain per binding.
"""

from __future__ import annotations

from ..domain.circuit import CircuitBreakerPolicy
from ..domain.errors import SameModelEndpointExhausted
from ..domain.selection import EndpointCandidate, binding_is_selectable, score_candidate
from .ports import ModelGatewayStore


class EndpointSelector:
    """Selects scored candidates for one locked canonical model."""

    def __init__(self, *, circuit_policy: CircuitBreakerPolicy | None = None) -> None:
        self._circuit_policy = circuit_policy or CircuitBreakerPolicy()

    async def select(
        self,
        store: ModelGatewayStore,
        canonical_model_id: str,
        *,
        now: object,
    ) -> tuple[EndpointCandidate, ...]:
        """Return survivors ordered by descending score.

        Raises ``SameModelEndpointExhausted`` when no binding survives the
        filter chain — exactly the frozen behavior.
        """
        from windagent.kernel.time import normalize_utc

        bindings = await store.list_selectable_bindings(canonical_model_id)
        current = normalize_utc(now)  # type: ignore[arg-type]
        survivors: list[EndpointCandidate] = []

        for binding in bindings:
            state = await store.get_endpoint_state(binding.endpoint_id)
            available = self._circuit_policy.is_available(state, current)
            if not binding_is_selectable(
                enabled=binding.endpoint_enabled and binding.binding_enabled,
                equivalence_level=binding.equivalence_level,
                has_credential=binding.has_credential,
                protocol_mode=binding.protocol_mode,
                endpoint_available=available,
            ):
                continue
            quota = await store.get_quota_state(binding.provider_name)
            candidate = EndpointCandidate(
                endpoint_id=binding.endpoint_id,
                binding_id=binding.binding_id,
                provider_name=binding.provider_name,
                provider_model_id=binding.provider_model_id,
                base_url=binding.base_url,
                protocol_mode=binding.protocol_mode,
                credential_reference=binding.credential_secret_name,
            )
            score, components = score_candidate(
                candidate, quota_has_quota=quota.has_quota
            )
            survivors.append(
                EndpointCandidate(
                    endpoint_id=candidate.endpoint_id,
                    binding_id=candidate.binding_id,
                    provider_name=candidate.provider_name,
                    provider_model_id=candidate.provider_model_id,
                    base_url=candidate.base_url,
                    protocol_mode=candidate.protocol_mode,
                    credential_reference=candidate.credential_reference,
                    score=score,
                    score_components=components,
                )
            )

        if not survivors:
            raise SameModelEndpointExhausted(
                "All exact-equivalent endpoints for the locked canonical model "
                "are exhausted",
                context={"canonical_model_id": canonical_model_id},
            )
        survivors.sort(key=lambda candidate: candidate.score, reverse=True)
        return tuple(survivors)
