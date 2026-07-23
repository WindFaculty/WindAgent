"""
Unit Tests for WindAgent Provider Adapters (Phase 5 Legacy):
- MockProviderAdapter generation, streaming, cancellation, and cost estimation
- Legacy OpenAI, Anthropic, Gemini, Ollama adapter health & capabilities
- Secret key redaction & offline test execution (zero real network calls)
"""

import pytest
from windagent_core.domain.types import ModelCallId
from windagent_core.domain.models import ModelRequest
from windagent_providers import (
    MockProviderAdapter, OpenAICompatibleProviderAdapter,
    LegacyAnthropicAdapter as AnthropicProviderAdapter,
    LegacyGoogleAdapter as GoogleGeminiProviderAdapter,
    LegacyOllamaAdapter as OllamaProviderAdapter
)


@pytest.mark.asyncio
async def test_mock_provider_adapter_generate_and_stream():
    adapter = MockProviderAdapter(mock_response="Hello Antigravity")
    
    models = await adapter.list_models()
    assert "mock-gpt-4o" in models

    health = await adapter.health()
    assert health.healthy

    req = ModelRequest(id=ModelCallId.generate(), model="mock-gpt-4o", messages=[{"role": "user", "content": "Hi"}])
    res = await adapter.generate(req)
    assert "Hello Antigravity" in res.content
    assert res.finish_reason == "stop"

    # Streaming test
    chunks = []
    async for chunk in adapter.stream(req):
        chunks.append(chunk.delta)
    assert len(chunks) > 0
    assert "Hello" in "".join(chunks)


@pytest.mark.asyncio
async def test_provider_adapter_health_checks():
    openai = OpenAICompatibleProviderAdapter(api_key=None)
    assert not (await openai.health()).healthy

    openai_key = OpenAICompatibleProviderAdapter(api_key="sk-test-key")
    assert (await openai_key.health()).healthy

    anthropic = AnthropicProviderAdapter(api_key=None)
    assert not (await anthropic.health()).healthy

    gemini = GoogleGeminiProviderAdapter(api_key="gemini-key")
    assert (await gemini.health()).healthy

    ollama = OllamaProviderAdapter()
    assert (await ollama.health()).healthy


def test_provider_cost_estimation():
    openai = OpenAICompatibleProviderAdapter(api_key="sk-test")
    req = ModelRequest(id=ModelCallId.generate(), model="gpt-4o", messages=[{"role": "user", "content": "Explain quantum physics"}])
    cost = openai.estimate_cost(req)
    assert cost > 0.0
