"""
Phase 10 integration tests: Provider V3 wiring behind feature flags.
Run from repo root so pyproject/pythonpath resolves windagent_providers and apps.backend.
"""

from __future__ import annotations

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[3]
backend_dir = root_dir / "apps" / "backend"
for d in (root_dir, backend_dir):
    if d.exists() and str(d) not in sys.path:
        sys.path.insert(0, str(d)) if d == root_dir else sys.path.append(str(d))

import os
import pytest
import uuid


from db.database import Database
from db.models import (
    CanonicalModelORM,
    ModelProviderORM,
    ModelRoutingRuleORM,
    ProviderModelBindingORM,
)
from services.model_service import ModelService
from services.provider_v3_adapter import LegacyClientV3Adapter
from services.provider_v3_coordinator import ProviderV3Coordinator
from services.provider_v3_flags import v3_execute_enabled


@pytest.fixture
async def v3_db():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.init_models()
    yield db
    await db.dispose()


@pytest.fixture
async def seeded_coordinator(v3_db):
    db = v3_db

    # Seed a cloud provider with a mock key.
    async with db.session() as session:
        provider = ModelProviderORM(
            id="mock_provider",
            site_name="Mock Provider",
            api_source="openai",
            base_url="http://localhost:9999/v1",
            api_key="mock-key-encrypted",
            provider_type="cloud",
            quota_mode="RPM_RPD",
            enabled=True,
        )
        canonical = CanonicalModelORM(
            id="mock-model",
            vendor="mock",
            family="mock",
            canonical_name="mock-model",
            context_window=8192,
            enabled=True,
        )
        binding = ProviderModelBindingORM(
            id="bind-mock",
            canonical_model_id="mock-model",
            provider_id="mock_provider",
            provider_model_id="mock-model",
            priority=10,
            enabled=True,
            equivalence_level="exact_revision",
        )
        rule = ModelRoutingRuleORM(
            role="TestRole",
            name="Test Role Route",
            primary_model_id="mock-model",
            fallback_model_id=None,
            status="Active",
        )
        session.add_all([provider, canonical, binding, rule])
        await session.commit()

    # Construct a ModelService in mock backend mode so clients don't call the network.
    old_backend = os.environ.get("WINDAGENT_MODEL_BACKEND")
    os.environ["WINDAGENT_MODEL_BACKEND"] = "mock"
    try:
        model_service = ModelService(db=db, ollama_client=None)  # type: ignore[arg-type]
        coordinator = ProviderV3Coordinator(
            db=db,
            quota_service=model_service.quota_service,
            model_service=model_service,
        )
        yield coordinator
    finally:
        if old_backend is None:
            os.environ.pop("WINDAGENT_MODEL_BACKEND", None)
        else:
            os.environ["WINDAGENT_MODEL_BACKEND"] = old_backend


@pytest.mark.asyncio
async def test_v3_coordinator_creates_route_lock(seeded_coordinator):
    coordinator = seeded_coordinator
    scope = str(uuid.uuid4())
    canonical_model_id, lock = await coordinator._resolve_canonical_and_lock(
        "TestRole", scope
    )

    assert canonical_model_id == "mock-model"
    assert lock["canonical_model_id"] == "mock-model"
    assert lock["scope_type"] == "role"
    assert lock["scope_id"] == scope

    # Subsequent resolves return the same persisted lock (DB is source of truth).
    canonical_model_id_2, lock_2 = await coordinator._resolve_canonical_and_lock(
        "TestRole", scope
    )
    assert canonical_model_id_2 == canonical_model_id
    assert lock_2["lock_id"] == lock["lock_id"]


@pytest.mark.asyncio
async def test_v3_execute_chat_mock_backend(seeded_coordinator):
    coordinator = seeded_coordinator
    # The mock backend returns JSON {"steps": []} for unknown prompts.
    text = await coordinator.execute_chat(
        role="TestRole",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=32,
    )
    assert isinstance(text, str)


@pytest.mark.asyncio
async def test_feature_flag_off_by_default():
    assert v3_execute_enabled() is False


class _ToolLegacyClient:
    async def chat_completion(self, **kwargs):
        assert "tools" in kwargs
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location":"Hanoi"}',
                    },
                }
            ],
        }


@pytest.mark.asyncio
async def test_v3_coordinator_tool_use(seeded_coordinator):
    coordinator = seeded_coordinator

    # Inject a fake client that returns tool calls instead of the mock backend.
    adapter = LegacyClientV3Adapter("openai", _ToolLegacyClient(), "mock-model")
    coordinator._coordinator._adapter_resolver = lambda _candidate: adapter

    response = await coordinator.execute_chat_with_tools(
        role="TestRole",
        messages=[{"role": "user", "content": "weather?"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "...",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                    },
                },
            }
        ],
        max_tokens=32,
    )
    assert not response.text
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["function"]["name"] == "get_weather"
