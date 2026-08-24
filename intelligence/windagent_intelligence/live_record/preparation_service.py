"""RECORDING_PREPARER intelligence service — Phase 2 (ban_ke_hoach_v1.md Section 5).

Reads screenplay / scenes / demo flow + source workspace and produces a
Recording Preparation Package via the deterministic domain builder.
In production the LLM (configured via Providers + Model Routing, role
RECORDING_PREPARER) generates the package; here we expose a deterministic
fallback so the pipeline is verifiable without live model credentials.
"""

from __future__ import annotations

from typing import Any, Dict

from windagent_core.domain.live_record.preparation import RecordingPreparationBuilder


class RecordingPreparationIntelligenceService:
    """Bridge between Episode workspace and the domain preparation builder.

    Production flow:
        Episode → screenplay + scene drafts + demo objective
        → RECORDING_PREPARER (intelligence prompt) → Recording Preparation Package
        → LiveExecutionPlan (DRAFT → PREPARED → VALIDATED → FROZEN)

    This service currently delegates to the deterministic builder. When a
    Provider + Model Router resolves RECORDING_PREPARER to a real model,
    `generate_via_model()` will call the model with the prompt template at
    `intelligence/windagent_intelligence/live_record/prompts/prepare.yaml`.
    """

    @staticmethod
    def build_deterministic(payload: Dict[str, Any]):
        """Build without a model — deterministic, testable, hash-stable."""
        return RecordingPreparationBuilder.build_from_api_payload(payload)

    async def generate_via_model(self, payload: Dict[str, Any], *, model_client=None):
        """Placeholder for LLM-backed generation — falls back to deterministic.

        When `model_client` is None (no credential / no provider), the method
        returns the deterministic package so callers can proceed in CI.
        """
        if model_client is None:
            return self.build_deterministic(payload)
        # Real implementation would:
        #   prompt = load_prompt("live_record/prepare.yaml", version="v1")
        #   response = await model_client.generate(prompt.format(episode=payload))
        #   return RecordingPreparationBuilder.build_from_api_payload(response)
        return self.build_deterministic(payload)
