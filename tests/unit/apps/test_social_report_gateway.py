from __future__ import annotations

from types import SimpleNamespace

import pytest

from windagent_cli.social_report import ProviderModelGateway
from windagent_workflows.social_research import ModelRoute, SocialResearchError


class FakeAdapter:
    def __init__(self, models, text):
        self.models = list(models)
        self.text = text
        self.generated = []

    async def list_models(self):
        return [SimpleNamespace(raw_model_id=model) for model in self.models]

    async def generate(self, request, model_id):
        self.generated.append((request, model_id))
        return SimpleNamespace(text=self.text)


@pytest.mark.asyncio
async def test_gateway_routes_local_qwen_and_google_synthesis_models():
    ollama = FakeAdapter(["qwen3.5:latest"], "normalized-json")
    google = FakeAdapter(
        ["gemma-4-31b", "gemini-3.5-flash-lite"],
        "synthesis",
    )
    gateway = ProviderModelGateway(
        google_api_key="test-key",
        ollama_adapter=ollama,
        google_adapter=google,
    )
    routes = (
        ModelRoute("ollama", "qwen3.5", "structured_extractor"),
        ModelRoute("google", "gemma-4-31b", "independent_synthesis"),
        ModelRoute("google", "gemini-3.5-flash-lite", "verification_synthesis"),
    )

    discovered = await gateway.validate_models(routes)
    local_text = await gateway.generate(
        provider="ollama",
        model="qwen3.5",
        system_instruction="extract",
        prompt="page",
        max_output_tokens=100,
        temperature=0.0,
    )
    google_text = await gateway.generate(
        provider="google",
        model="gemma-4-31b",
        system_instruction="synthesize",
        prompt="records",
        max_output_tokens=100,
        temperature=0.2,
    )

    assert discovered["ollama"] == ["qwen3.5:latest"]
    assert discovered["google"] == ["gemini-3.5-flash-lite", "gemma-4-31b"]
    assert local_text == "normalized-json"
    assert google_text == "synthesis"
    assert ollama.generated[0][1] == "qwen3.5"
    assert google.generated[0][1] == "gemma-4-31b"


@pytest.mark.asyncio
async def test_gateway_fails_closed_when_requested_model_is_not_discovered():
    gateway = ProviderModelGateway(
        google_api_key="test-key",
        ollama_adapter=FakeAdapter(["qwen3.5:latest"], "ok"),
        google_adapter=FakeAdapter(["gemini-3.5-flash-lite"], "ok"),
    )

    with pytest.raises(SocialResearchError, match="gemma-4-31b"):
        await gateway.validate_models(
            (
                ModelRoute("ollama", "qwen3.5", "structured_extractor"),
                ModelRoute("google", "gemma-4-31b", "independent_synthesis"),
            )
        )
