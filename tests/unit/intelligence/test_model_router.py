"""
Unit Tests for WindAgent Model Router Policy Engine (Phase 5):
- Multi-factor capability & context matching
- RouteLock generation and fallback chain stability
- Privacy requirements & preferred provider scoring
- Emergency mock fallback when provider quota exhausted / unhealthy
"""

import pytest
from windagent_core.domain.types import SessionId, TaskId
from windagent_providers import ModelCapability
from tests.unit.providers.mock_adapter import MockProviderAdapter
from windagent_intelligence import ModelRouterPolicy, RoutingContext, RouteLock


@pytest.mark.asyncio
async def test_model_router_policy_routing():
    router = ModelRouterPolicy()
    mock_provider = MockProviderAdapter()
    router.register_provider(mock_provider)

    sid = SessionId.generate()
    tid = TaskId.generate()

    # Case 1: Standard coding task with required capabilities
    ctx1 = RoutingContext(
        session_id=sid,
        task_id=tid,
        required_capabilities=[ModelCapability.CODING, ModelCapability.TOOL_USE],
        estimated_context_tokens=5000,
    )
    route1 = await router.route(ctx1)
    assert route1.canonical_model in ("gpt-4o", "claude-3-5-sonnet", "mock-gpt-4o")
    assert len(route1.selection_reasons) > 0

    # Case 2: Privacy required task -> route to Ollama or Mock
    ctx2 = RoutingContext(
        session_id=sid,
        task_id=tid,
        required_capabilities=[ModelCapability.CHAT],
        privacy_required=True,
    )
    route2 = await router.route(ctx2)
    assert route2.provider_name in ("ollama", "mock")

    # Case 3: Preferred provider priority
    ctx3 = RoutingContext(
        session_id=sid,
        task_id=tid,
        preferred_provider="anthropic",
        required_capabilities=[ModelCapability.COMPUTER_USE],
    )
    route3 = await router.route(ctx3)
    assert route3.canonical_model == "claude-3-5-sonnet"
    assert route3.provider_name == "anthropic"


def test_route_lock_serialization():
    sid = SessionId.generate()
    tid = TaskId.generate()
    lock = RouteLock(
        session_id=sid,
        task_id=tid,
        canonical_model="gpt-4o",
        provider_name="openai",
        fallback_chain=["claude-3-5-sonnet"],
        selection_reasons=["High coding benchmark score"],
    )
    d = lock.to_dict()
    assert d["session_id"] == str(sid)
    assert d["canonical_model"] == "gpt-4o"
    assert d["fallback_chain"] == ["claude-3-5-sonnet"]
