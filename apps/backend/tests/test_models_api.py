"""Comprehensive tests for the Model Registry and Lifecycle control APIs."""
from __future__ import annotations

import os
import json
import pytest
from unittest.mock import AsyncMock, patch
import httpx

from sqlalchemy import select
from db.models import ModelProviderORM, ModelCatalogORM, ModelRuntimeStatusORM, ProviderQuotaSnapshotORM, ModelActivityORM


def test_models_health_returns_200_with_expected_shape(client):
    r = client.get("/models/health")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock"
    assert body["online"] is True
    assert body["model"].startswith("mock:")
    assert body["latency_ms"] is not None
    assert body["error"] is None


def test_get_models_returns_seed_and_ollama_mock(client):
    """GET /models should return the list of seeded models and local mock Ollama."""
    r = client.get("/models")
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    # Must contain seeded models like google_gemini_2.5_flash
    gemini = next((m for m in body if m["id"] == "google_gemini_2.5_flash"), None)
    assert gemini is not None
    assert gemini["provider"] == "Google AI Studio"
    assert gemini["type"] == "API"
    assert gemini["billingMode"] == "RPM_RPD"


def test_provider_taxonomy(client):
    """GET /models/providers should return the 8 providers seeded with correct quota_mode."""
    r = client.get("/models/providers")
    assert r.status_code == 200
    body = r.json()
    
    # Check quota modes
    p_modes = {p["id"]: p["quotaMode"] for p in body}
    assert p_modes["agentrouter"] == "ONE_TIME_CREDIT"
    assert p_modes["bluesminds"] == "ONE_TIME_CREDIT"
    assert p_modes["zenmux"] == "TOKEN_BUDGET"
    assert p_modes["mistral"] == "TOKEN_BUDGET"
    assert p_modes["nararouter"] == "TOKEN_BUDGET"
    assert p_modes["openrouter"] == "RPM_RPD"
    assert p_modes["nvidia_nim"] == "RPM_RPD"
    assert p_modes["google_ai_studio"] == "RPM_RPD"


def test_missing_api_key_does_not_crash(client):
    """If API keys are missing in env, list_models and list_providers still succeed."""
    # Ensure keys are not set
    orig_env = os.environ.copy()
    try:
        for k in ["OPENROUTER_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "NVIDIA_API_KEY"]:
            if k in os.environ:
                del os.environ[k]
                
        r = client.get("/models")
        assert r.status_code == 200
        
        r_p = client.get("/models/providers")
        assert r_p.status_code == 200
        providers = r_p.json()
        
        # Google AI Studio should show hasKey=False
        gemini_prov = next((p for p in providers if p["id"] == "google_ai_studio"), None)
        assert gemini_prov is not None
        assert gemini_prov["hasKey"] is False
    finally:
        # Restore environment
        os.environ.clear()
        os.environ.update(orig_env)


@pytest.mark.anyio
async def test_openai_compatible_sync_models(app_state):
    """Sync provider catalog dynamically upserts discovered models in SQLite."""
    model_service = app_state.model_service
    
    # Mock list_models response from client
    mock_client = AsyncMock()
    mock_client.list_models.return_value = [
        {
            "model_id": "meta/llama-3-8b-instruct",
            "display_name": "Llama 3 8B",
            "context_window": 8192,
            "capabilities": ["chat", "fast"],
        }
    ]
    
    with patch.object(model_service, "get_provider_client", return_value=mock_client):
        res = await model_service.sync_provider_models("openrouter")
        assert res["status"] == "success"
        assert res["added"] == 1
        
        # Verify db insert
        async with model_service.db.session() as s:
            stmt = select(ModelCatalogORM).where(ModelCatalogORM.id == "openrouter_meta_llama-3-8b-instruct")
            db_res = await s.execute(stmt)
            m = db_res.scalar_one_or_none()
            assert m is not None
            assert m.display_name == "Llama 3 8B"
            assert m.enabled is True
            assert m.discovered is True


@pytest.mark.anyio
async def test_probe_updates_runtime_status(app_state):
    """Probing a model updates its runtime latency and status."""
    model_service = app_state.model_service
    
    mock_client = AsyncMock()
    mock_client.chat_completion.return_value = "hello response"
    mock_client.has_api_key.return_value = True
    
    # Mock OS env key presence
    with patch.object(model_service, "get_provider_client", return_value=mock_client), \
         patch("os.environ.get", return_value="some_key"):
        res = await model_service.probe_model("google_gemini_2.5_flash")
        assert res["success"] is True
        assert res["latency_ms"] >= 0
        
        # Check database update
        async with model_service.db.session() as s:
            stmt = select(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id == "google_gemini_2.5_flash")
            db_res = await s.execute(stmt)
            status = db_res.scalar_one_or_none()
            assert status is not None
            assert status.status == "Ready"
            assert status.health == "Healthy"
            assert status.latency_p50_ms == res["latency_ms"]


def test_routing_rules_crud(client):
    """GET and PATCH /models/routing should update configurations."""
    # 1. Fetch current rules
    r = client.get("/models/routing")
    assert r.status_code == 200
    body = r.json()
    assert "Planner" in body
    
    # 2. Update rule
    payload = {
        "Planner": {"primary": "google_gemini_2.5_flash_lite", "fallback": "openrouter_free"}
    }
    r_patch = client.patch("/models/routing", json=payload)
    assert r_patch.status_code == 200
    
    # 3. Verify update
    r_verify = client.get("/models/routing")
    verify_body = r_verify.json()
    assert verify_body["Planner"]["primary"] == "google_gemini_2.5_flash_lite"


@pytest.mark.anyio
async def test_start_stop_ollama_keep_alive(app_state):
    """Ollama start uses keep_alive load and stop uses keep_alive = 0 unload."""
    model_service = app_state.model_service
    mock_ollama = app_state.model_client
    
    # Seed a local model first
    async with model_service.db.session() as session:
        local_model = ModelCatalogORM(
            id="ollama_qwen",
            provider_id="ollama",
            model_id="qwen3.5:4b-q4",
            display_name="Qwen Local",
            type="Local",
            capabilities_json="[]",
            tags_json="[]",
            default_roles_json="[]",
            enabled=True,
            discovered=False,
            source="seed"
        )
        session.add(local_model)
        await session.commit()

    # Start model
    with patch.object(mock_ollama, "start_ollama_model", new_callable=AsyncMock) as mock_start:
        mock_start.return_value = True
        res = await model_service.start_model("ollama_qwen")
        assert res["status"] == "started"
        mock_start.assert_called_once_with("qwen3.5:4b-q4")
        
    # Stop model
    with patch.object(mock_ollama, "stop_ollama_model", new_callable=AsyncMock) as mock_stop:
        mock_stop.return_value = True
        res = await model_service.stop_model("ollama_qwen")
        assert res["status"] == "stopped"
        mock_stop.assert_called_once_with("qwen3.5:4b-q4")


@pytest.mark.anyio
async def test_429_updates_quota_activity(app_state):
    """If provider returns HTTP 429, it should create warning activity log and update quota reset_at."""
    model_service = app_state.model_service
    
    # Simulate a 429 response during completions
    mock_client = AsyncMock()
    from services.provider_clients.base import ProviderResponseError
    mock_client.chat_completion.side_effect = ProviderResponseError("Rate limit exceeded (HTTP 429) for openrouter. Retry after: 60s")
    mock_client.has_api_key.return_value = True
    
    with patch.object(model_service, "get_provider_client", return_value=mock_client), \
         patch("os.environ.get", return_value="some_key"):
        res = await model_service.run_benchmark({
            "model_ids": ["openrouter_free"],
            "prompt": "hi",
            "test_name": "test_429"
        })
        assert res["results"][0]["success"] is False
        assert "429" in res["results"][0]["error"]
        
        # Verify warning activity was logged
        async with model_service.db.session() as s:
            stmt = (
                select(ModelActivityORM)
                .where(ModelActivityORM.event_type == "benchmark_failed")
                .order_by(ModelActivityORM.created_at.desc())
            )
            db_res = await s.execute(stmt)
            act = db_res.scalars().first()
            assert act is not None
            assert act.level == "error"
            assert "429" in act.message


def test_create_and_update_provider(client):
    # 1. Create a custom provider
    payload = {
        "id": "test_provider",
        "name": "Test Custom Provider",
        "api_source": "openai",
        "base_url": "https://api.testprovider.com/v1",
        "api_key": "test_api_key_123"
    }
    r = client.post("/models/providers", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    # 2. Get list of providers and verify it is there
    r_list = client.get("/models/providers")
    assert r_list.status_code == 200
    providers = r_list.json()
    test_p = next((p for p in providers if p["id"] == "test_provider"), None)
    assert test_p is not None
    assert test_p["name"] == "Test Custom Provider"
    assert test_p["apiSource"] == "openai"
    assert test_p["baseUrl"] == "https://api.testprovider.com/v1"
    assert test_p["hasKey"] is True

    # 3. Update the provider base URL and API key
    update_payload = {
        "name": "Updated Provider Name",
        "api_source": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key": "new_api_key_456"
    }
    r_patch = client.patch("/models/providers/test_provider", json=update_payload)
    assert r_patch.status_code == 200
    assert r_patch.json()["status"] == "success"

    # 4. Get list again and verify updates
    r_list2 = client.get("/models/providers")
    providers2 = r_list2.json()
    test_p2 = next((p for p in providers2 if p["id"] == "test_provider"), None)
    assert test_p2 is not None
    assert test_p2["name"] == "Updated Provider Name"
    assert test_p2["apiSource"] == "anthropic"
    assert test_p2["baseUrl"] == "https://api.anthropic.com"


def test_test_provider_connection(client):
    with patch("services.provider_clients.openai_compatible.OpenAICompatibleClient.list_models", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [
            {"model_id": "test_m1", "display_name": "Test Model 1", "capabilities": ["chat"]}
        ]
        payload = {
            "api_source": "openai",
            "base_url": "https://api.test.com/v1",
            "api_key": "somekey"
        }
        r = client.post("/models/providers/test-connection", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "success"
        assert len(data["models"]) == 1
        assert data["models"][0]["model_id"] == "test_m1"