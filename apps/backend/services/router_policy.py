"""Scoring policies for router model selection inspired by OmniRoute."""
from __future__ import annotations

import logging
import json
from typing import Optional

from db.models import ModelCatalogORM, ModelProviderORM, ModelRuntimeStatusORM
from services.quota_service import QuotaService

log = logging.getLogger(__name__)


class RouterPolicy:
    """Evaluates suitability scores for models based on multiple dimensions."""

    def __init__(self, quota_service: QuotaService) -> None:
        self.quota_service = quota_service

    async def calculate_score(
        self,
        role: str,
        catalog: ModelCatalogORM,
        provider: ModelProviderORM,
        runtime: Optional[ModelRuntimeStatusORM],
        estimated_tokens: int = 1000,
    ) -> float:
        """Calculate composite routing suitability score from 0.0 to 1.0.

        Formula:
        score = 0.25*health + 0.20*quota + 0.20*task_fit + 0.15*cost_inverse + 0.10*latency_inverse + 0.10*context_fit
        """
        # Base checks: if disabled or missing required API keys, score is 0
        if not catalog.enabled or not provider.enabled:
            return 0.0

        if provider.provider_type == "cloud" and provider.api_key_env:
            import os
            if not os.environ.get(provider.api_key_env) and not provider.api_key:
                return 0.0

        if runtime and runtime.status == "Offline":
            return 0.0

        # 1. Health Score (weight: 0.25)
        health = 0.5
        if runtime:
            if runtime.status in ("Running", "Ready"):
                health = 1.0
            if runtime.health == "Healthy":
                health = 1.0
            elif runtime.health == "Unhealthy":
                health = 0.1
        else:
            # If API is cloud, default to healthy if credentials are present
            if catalog.type == "API":
                health = 0.9

        # 2. Quota Score (weight: 0.20)
        quota = 0.0
        try:
            quota_allowed = await self.quota_service.should_route(provider.id, estimated_tokens)
            if quota_allowed:
                quota = 1.0
        except Exception:
            # Fallback if quota service raises error
            quota = 0.8

        # 3. Task Fit Score (weight: 0.20)
        task_fit = 0.5
        capabilities = []
        try:
            capabilities = json.loads(catalog.capabilities_json)
        except Exception:
            pass

        role_lower = role.lower()
        if "planner" in role_lower or "chat" in role_lower:
            # Prefer local models for Planner and local chat
            if catalog.type == "Local":
                task_fit = 1.0
            else:
                task_fit = 0.6
        elif "coder" in role_lower:
            if any(c in capabilities for c in ("coding", "code", "tool_use")):
                task_fit = 1.0
            else:
                task_fit = 0.3
        elif "gui" in role_lower or "vision" in role_lower:
            if any(c in capabilities for c in ("vision", "gui", "multimodal")):
                task_fit = 1.0
            else:
                task_fit = 0.2
        elif "research" in role_lower:
            if catalog.context_window and catalog.context_window >= 32000:
                task_fit = 1.0
            elif any(c in capabilities for c in ("long_context", "research")):
                task_fit = 0.9
            else:
                task_fit = 0.4

        # 4. Cost Inverse Score (weight: 0.15)
        # Local models are free (cost_inverse = 1.0).
        # Cloud API models might have a cost.
        cost_inverse = 0.5
        if catalog.type == "Local":
            cost_inverse = 1.0
        else:
            if provider.quota_mode == "RPM_RPD":  # often Google free tier or OpenRouter free models
                cost_inverse = 0.8
            else:
                # Standard paid API
                cost_inverse = 0.4

        # 5. Latency Inverse Score (weight: 0.10)
        latency_inverse = 0.5
        if runtime and runtime.latency_p50_ms:
            latency_inverse = 1.0 / (1.0 + (runtime.latency_p50_ms / 1000.0))

        # 6. Context Fit Score (weight: 0.10)
        context_fit = 0.5
        cw = catalog.context_window or 4096
        if cw >= 128000:
            context_fit = 1.0
        elif cw >= 32000:
            context_fit = 0.8
        elif cw >= 8000:
            context_fit = 0.6
        else:
            context_fit = 0.4

        # Compute composite score
        score = (
            0.25 * health +
            0.20 * quota +
            0.20 * task_fit +
            0.15 * cost_inverse +
            0.10 * latency_inverse +
            0.10 * context_fit
        )
        return float(round(score, 4))
