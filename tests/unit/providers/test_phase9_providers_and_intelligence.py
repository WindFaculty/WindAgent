"""
Unit tests for WindAgent Providers and Intelligence Adoption (Phase 9).
Verifies canonical Provider models, error inheritance from windagent_core ProviderError,
ModelRouterPolicy using CanonicalModelId & RouteLockId, and SecretRef protection.
"""

import pytest
from windagent_core.domain.types import CanonicalModelId, ProviderId, TaskId, SessionId, RouteLockId
from windagent_core.providers.models import (
    ProviderRequest, ProviderResponse, ProviderUsage, ProviderToolCall, ProviderStreamChunk
)
from windagent_core.errors.exceptions import ProviderError, WindAgentError
from windagent_core.security import SecretRef
from windagent_providers.base.errors import (
    ProviderFailure, RateLimitFailure, AuthenticationFailure, QuotaExhaustedFailure, TimeoutFailure
)
from windagent_intelligence.model_router.policy import ModelRouterPolicy, RoutingContext
from windagent_intelligence.model_router.route_lock import RouteLock


def test_canonical_provider_models():
    usage = ProviderUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, estimated_cost_usd=0.003)
    tool_call = ProviderToolCall(call_id="call_123", tool_name="view_file", arguments={"path": "/tmp/test.py"})

    req = ProviderRequest(
        provider_id=ProviderId("openai"),
        model_id=CanonicalModelId("gpt-4o"),
        prompt="Analyze codebase architecture",
        temperature=0.2,
        secret_ref=SecretRef.create("OPENAI_API_KEY", "sk-secret-token")
    )
    assert req.provider_id == ProviderId("openai")
    assert req.model_id == CanonicalModelId("gpt-4o")

    res = ProviderResponse(
        provider_id=ProviderId("openai"),
        model_id=CanonicalModelId("gpt-4o"),
        content="Architecture analysis complete.",
        tool_calls=[tool_call],
        usage=usage
    )
    assert res.content == "Architecture analysis complete."
    assert len(res.tool_calls) == 1
    assert res.usage.total_tokens == 150

    chunk = ProviderStreamChunk(delta_content="Part 1 ", finish_reason=None)
    assert chunk.delta_content == "Part 1 "


def test_provider_errors_inherit_from_core_provider_error():
    err = RateLimitFailure("API Rate limit exceeded", provider_id="openai", model_id="gpt-4o")
    assert isinstance(err, ProviderFailure)
    assert isinstance(err, ProviderError)
    assert isinstance(err, WindAgentError)
    assert err.retryable is True
    assert err.status_code == 429

    auth_err = AuthenticationFailure("Invalid key", provider_id="anthropic")
    assert isinstance(auth_err, ProviderError)
    assert auth_err.retryable is False


@pytest.mark.asyncio
async def test_model_router_canonical_model_id_and_route_lock():
    router = ModelRouterPolicy()
    ctx = RoutingContext(
        session_id=SessionId.generate(),
        task_id=TaskId.generate(),
        estimated_context_tokens=2000
    )

    lock = await router.route(ctx)
    assert isinstance(lock, RouteLock)
    assert isinstance(lock.lock_id, RouteLockId)
    assert isinstance(lock.canonical_model, CanonicalModelId)
    assert isinstance(lock.provider_name, ProviderId)
    assert lock.lock_id.value is not None
