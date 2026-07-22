"""
Multi-factor Model Router Policy Engine for WindAgent Architecture V2.
Evaluates capabilities, provider health, quota, latency, and cost to lock routes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from windagent_core.domain.types import TaskId, SessionId
from windagent_core.domain.models import TaskRequest
from windagent_providers.capabilities import (
    ModelCapability, ModelCapabilityProfile, KNOWN_MODEL_PROFILES
)
from windagent_providers.base import BaseModelProvider, ProviderHealth, QuotaSnapshot
from windagent_intelligence.model_router.route_lock import RouteLock


@dataclass
class RoutingContext:
    session_id: SessionId
    task_id: TaskId
    required_capabilities: List[ModelCapability] = field(default_factory=list)
    estimated_context_tokens: int = 1000
    privacy_required: bool = False
    max_budget_usd: Optional[float] = None
    preferred_provider: Optional[str] = None


class ModelRouterPolicy:
    def __init__(
        self,
        providers: Optional[Dict[str, BaseModelProvider]] = None,
        model_profiles: Optional[Dict[str, ModelCapabilityProfile]] = None,
    ):
        self.providers = providers or {}
        self.model_profiles = model_profiles or KNOWN_MODEL_PROFILES

    def register_provider(self, provider: BaseModelProvider) -> None:
        self.providers[provider.provider_name] = provider

    async def route(self, ctx: RoutingContext) -> RouteLock:
        """Evaluates multi-factor policy rules and returns a RouteLock decision."""
        reasons: List[str] = []
        candidates: List[tuple[str, ModelCapabilityProfile, float]] = []

        for model_id, profile in self.model_profiles.items():
            # 1. Capability filter
            if not profile.supports_all(ctx.required_capabilities):
                continue

            # 2. Context window filter
            if profile.context_window < ctx.estimated_context_tokens:
                continue

            # 3. Privacy filter
            if ctx.privacy_required and profile.provider_name not in ("ollama", "local", "mock"):
                continue

            # 4. Provider health & quota filter
            provider_name = profile.provider_name
            provider = self.providers.get(provider_name)
            if provider:
                health = await provider.health()
                if not health.healthy:
                    continue

                quota = await provider.get_quota()
                if not quota.has_quota:
                    continue

            # Calculate suitability score
            score = 100.0
            if ctx.preferred_provider and profile.provider_name == ctx.preferred_provider:
                score += 50.0

            # Favor lower cost if budget specified
            if ctx.max_budget_usd:
                cost_est = (ctx.estimated_context_tokens / 1000.0) * profile.cost_per_1k_prompt_tokens
                if cost_est > ctx.max_budget_usd:
                    continue
                score += max(0, 20.0 - cost_est * 1000.0)

            candidates.append((model_id, profile, score))

        if not candidates:
            # Fallback to mock provider if no candidate matches criteria
            reasons.append("No candidate matched strict filters; assigned emergency mock fallback.")
            return RouteLock(
                session_id=ctx.session_id,
                task_id=ctx.task_id,
                canonical_model="mock-gpt-4o",
                provider_name="mock",
                fallback_chain=[],
                selection_reasons=reasons,
                estimated_cost=0.0,
            )

        # Sort candidates by score descending
        candidates.sort(key=lambda c: c[2], reverse=True)
        selected_model, selected_profile, top_score = candidates[0]

        reasons.append(f"Selected {selected_model} via provider {selected_profile.provider_name} (Score: {top_score:.1f})")
        if ctx.required_capabilities:
            reasons.append(f"Matched required capabilities: {[c.value for c in ctx.required_capabilities]}")

        fallback_chain = [c[0] for c in candidates[1:4]]

        return RouteLock(
            session_id=ctx.session_id,
            task_id=ctx.task_id,
            canonical_model=selected_model,
            provider_name=selected_profile.provider_name,
            fallback_chain=fallback_chain,
            selection_reasons=reasons,
            estimated_cost=0.002,
        )
