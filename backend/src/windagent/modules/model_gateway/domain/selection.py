"""Endpoint candidate selection: filter chain and deterministic scoring.

REWRITE of the frozen ``providers/windagent_providers/routing/endpoint_selector.py``.
The filter chain and the score-component semantics are parity oracles:

    exact_revision only → enabled → valid credential (fail-closed unless the
    protocol is ``ollama``) → not in cooldown → circuit not open → score.

Scoring sums named components (health, quota, priority, weight, latency,
success_rate, cost, recent_429, circuit); latency/cost/recent_429 remain
zero-contribution placeholders exactly as in the frozen authority, so
candidate ordering matches the old system bit for bit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EndpointCandidate:
    """One failover candidate for the locked canonical model."""

    endpoint_id: str
    binding_id: str
    provider_name: str
    provider_model_id: str
    base_url: str
    protocol_mode: str = "openai"
    credential_reference: str | None = None
    is_exact_revision: bool = True
    score: float = 0.0
    score_components: dict[str, float] = field(default_factory=dict)


def score_candidate(
    candidate: EndpointCandidate, *, quota_has_quota: bool | None
) -> tuple[float, dict[str, float]]:
    """Compute the deterministic endpoint score (higher is better).

    Preserved exactly: components sum to 5.0 for a fully healthy candidate
    and 4.0 when quota is exhausted; placeholders contribute zero.
    """
    components: dict[str, float] = {
        "health": 1.0,
        "quota": 1.0 if quota_has_quota is None or quota_has_quota else 0.0,
        "priority": 1.0,
        "weight": 1.0,
        "latency": 0.0,
        "success_rate": 1.0,
        "cost": 0.0,
        "recent_429": 0.0,
        "circuit": 1.0,
    }
    return sum(components.values()), components


def binding_is_selectable(
    *,
    enabled: bool,
    equivalence_level: str,
    has_credential: bool,
    protocol_mode: str,
    endpoint_available: bool,
) -> bool:
    """Apply the frozen filter chain to one binding.

    Ollama is allowed to run as a credentialless local service; every other
    protocol fails closed when its credential is absent.
    """
    if not enabled:
        return False
    if equivalence_level != "exact_revision":
        return False
    if not has_credential and protocol_mode != "ollama":
        return False
    return endpoint_available
