"""Comprehensive integration tests for the new OmniRoute-inspired Router module."""
from __future__ import annotations

import json
import pytest
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select

from db.models import ModelRoutingRuleORM, RouterExecutionLogORM, ModelCatalogORM
from schemas.router import RoutingRuleCreate, RoutingRulePatch


def test_orm_routing_rule_new_fields(client, app_state):
    """Test that ModelRoutingRuleORM has all the new columns and holds default values."""
    db = app_state.db
    
    # We can inspect the seeded Planner rule
    async def get_planner_rule():
        async with db.session() as session:
            stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == "Planner")
            res = await session.execute(stmt)
            return res.scalar_one_or_none()
            
    # Run in asyncio block
    import asyncio
    rule = asyncio.run(get_planner_rule())
    assert rule is not None
    assert rule.name == "Planner → Local Chat"
    assert "lightweight planning" in rule.description
    assert rule.status == "Active"
    assert "tags_json" in dir(rule)
    assert "policy_json" in dir(rule)
    assert rule.final_fallback_model_id == "ollama_qwen"


def test_router_execution_log_orm_insert_and_query(client, app_state):
    """Test that we can insert and query execution logs in database."""
    db = app_state.db
    
    async def insert_and_check():
        async with db.session() as session:
            log = RouterExecutionLogORM(
                role="Planner",
                selected_model_id="google_gemini_2.5_flash",
                selection_tier="primary",
                status="success",
                latency_ms=250,
                prompt_tokens=15,
                completion_tokens=25,
                estimated_cost=0.0005,
            )
            session.add(log)
            await session.commit()
            
            stmt = select(RouterExecutionLogORM).where(RouterExecutionLogORM.role == "Planner")
            res = await session.execute(stmt)
            logs = res.scalars().all()
            return logs
            
    import asyncio
    logs = asyncio.run(insert_and_check())
    assert len(logs) > 0
    assert logs[-1].latency_ms == 250
    assert logs[-1].status == "success"


def test_list_rules_api(client):
    """GET /models/routing/rules should return the list of rules with stats."""
    r = client.get("/models/routing/rules")
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    planner = next((item for item in body if item["id"] == "Planner"), None)
    assert planner is not None
    assert planner["name"] == "Planner → Local Chat"
    assert planner["status"] == "Active"
    assert planner["successRate"] == 100
    assert len(planner["health"]) > 0
    assert len(planner["activity"]) > 0


def test_routing_rules_crud_endpoints(client):
    """CRUD endpoints for rules (POST, PATCH, DELETE) should work correctly."""
    # 1. Create Rule
    new_rule = {
        "role": "custom_test_role",
        "name": "Custom Test Route",
        "description": "For testing CRUD",
        "primary_model_id": "google_gemini_2.5_flash",
        "fallback_model_id": "openrouter_free",
        "final_fallback_model_id": None,
        "status": "Active",
        "tags": ["Test"],
        "policy": {}
    }
    r_create = client.post("/models/routing/rules", json=new_rule)
    assert r_create.status_code == 201
    assert r_create.json()["status"] == "success"
    
    # 2. Patch Rule
    patched = {
        "name": "Updated Test Route",
        "status": "Weighted"
    }
    r_patch = client.patch("/models/routing/rules/custom_test_role", json=patched)
    assert r_patch.status_code == 200
    assert r_patch.json()["status"] == "success"
    
    # Verify patch
    r_list = client.get("/models/routing/rules")
    rule_dto = next((item for item in r_list.json() if item["id"] == "custom_test_role"), None)
    assert rule_dto is not None
    assert rule_dto["name"] == "Updated Test Route"
    assert rule_dto["status"] == "Weighted"
    
    # 3. Delete Rule
    r_delete = client.delete("/models/routing/rules/custom_test_role")
    assert r_delete.status_code == 200
    
    # Verify deletion
    r_list2 = client.get("/models/routing/rules")
    rule_dto2 = next((item for item in r_list2.json() if item["id"] == "custom_test_role"), None)
    assert rule_dto2 is None


def test_bulk_import_rules(client):
    """POST /models/routing/import should handle bulk uploads and partial errors gracefully."""
    import_data = {
        "rules": [
            {
                "role": "import_role_1",
                "name": "Imported Route 1",
                "description": "Valid rule 1",
                "primary_model_id": "google_gemini_2.5_flash",
                "status": "Active",
                "tags": ["Imported"],
                "policy": {}
            },
            {
                "role": "import_role_2",
                "name": "Imported Route 2",
                # Invalid rule: missing primary_model_id or description is fine, but role is required.
                # Let's send an invalid field types or trigger validation error.
                "primary_model_id": 12345, # will cast to string or trigger string constraint
                "status": "InvalidStatus" # invalid enum literal
            }
        ]
    }
    r = client.post("/models/routing/import", json=import_data)
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 1
    assert body["failed"] == 1
    assert len(body["errors"]) == 1


def test_router_stats_api(client):
    """GET /models/routing/stats should return stable aggregate KPI values."""
    r = client.get("/models/routing/stats")
    assert r.status_code == 200
    body = r.json()
    assert "totalRoutes" in body
    assert "activeRules" in body
    assert "fallbackChains" in body
    assert "avgLatency" in body
    assert "successRate" in body
    assert "trafficBalance" in body
    
    assert body["totalRoutes"]["value"] > 0
    assert body["activeRules"]["value"] > 0


def test_traffic_distribution_api(client):
    """GET /models/routing/traffic should calculate model usage percentages."""
    r = client.get("/models/routing/traffic")
    assert r.status_code == 200
    body = r.json()
    assert "totalRequests" in body
    assert "distribution" in body
    assert isinstance(body["distribution"], list)


def test_routing_graph_api(client):
    """GET /models/routing/graph should return roles, models, and type links."""
    r = client.get("/models/routing/graph")
    assert r.status_code == 200
    body = r.json()
    assert "roles" in body
    assert "models" in body
    assert "links" in body
    assert len(body["roles"]) > 0
    assert len(body["links"]) > 0
    assert body["links"][0]["type"] in ("primary", "fallback", "final_fallback")


def test_route_simulation_api(client):
    """POST /models/routing/simulate should run dry-run resolving model without LLM calls."""
    payload = {
        "prompt": "write a python function to add two numbers",
        "role": "Coder"
    }
    r = client.post("/models/routing/simulate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "decision" in body
    assert "selectedModel" in body
    assert "confidence" in body
    assert "estimatedCost" in body
    assert "etaSeconds" in body
    assert len(body["flowSteps"]) > 0


@pytest.mark.anyio
async def test_live_route_test_probe(client, app_state):
    """POST /models/routing/rules/{role}/test executes live model probe and records logs."""
    # Trigger live test probe via client
    # Let's mock probe_model to succeed quickly
    from unittest.mock import AsyncMock, patch
    
    mock_probe = AsyncMock(return_value={"success": True, "latency_ms": 120, "error": None})
    
    with patch.object(app_state.model_service, "probe_model", mock_probe):
        r = client.post("/models/routing/rules/Planner/test", json={"prompt": "test prompt"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["selectedModel"] == "google_gemini_2.5_flash"
        assert body["tier"] == "primary"
        assert body["latencyMs"] >= 0
        
        # Verify a new log row is created in db
        async with app_state.db.session() as session:
            stmt = (
                select(RouterExecutionLogORM)
                .where(RouterExecutionLogORM.role == "Planner")
                .order_by(RouterExecutionLogORM.created_at.desc())
            )
            res = await session.execute(stmt)
            latest_log = res.scalars().first()
            assert latest_log is not None
            assert latest_log.status == "success"
            assert latest_log.selection_tier == "primary"


def test_backward_compatibility_endpoints(client):
    """GET and PATCH /models/routing compatibility paths should work identically to old API."""
    # 1. GET compatibility
    r_get = client.get("/models/routing")
    assert r_get.status_code == 200
    body_get = r_get.json()
    assert "Planner" in body_get
    assert "primary" in body_get["Planner"]
    
    # 2. PATCH compatibility
    payload = {
        "Planner": {"primary": "google_gemini_2.5_flash_lite", "fallback": "openrouter_free"}
    }
    r_patch = client.patch("/models/routing", json=payload)
    assert r_patch.status_code == 200
    assert r_patch.json()["status"] == "success"
    
    # Verify rule updated in new rules endpoint
    r_rules = client.get("/models/routing/rules")
    planner_dto = next((item for item in r_rules.json() if item["id"] == "Planner"), None)
    assert planner_dto is not None
    assert planner_dto["primaryModel"] == "Gemini 2.5 Flash Lite" or planner_dto["secondaryModel"] == "OpenRouter Free"


def test_openai_compatible_gateway_endpoints(client, app_state):
    """GET /v1/models and POST /v1/chat/completions should return OpenAI-compatible JSON responses."""
    # Enable all seeded catalog models and set status to Ready in test database
    db = app_state.db
    async def enable_all_models():
        async with db.session() as session:
            from sqlalchemy import update
            from db.models import ModelRuntimeStatusORM
            stmt_cat = update(ModelCatalogORM).values(enabled=True)
            await session.execute(stmt_cat)
            stmt_status = update(ModelRuntimeStatusORM).values(status="Ready")
            await session.execute(stmt_status)
            await session.commit()
    import asyncio
    asyncio.run(enable_all_models())

    # 1. Models list
    r_models = client.get("/v1/models")
    assert r_models.status_code == 200
    body_models = r_models.json()
    assert body_models["object"] == "list"
    assert len(body_models["data"]) > 0
    assert "id" in body_models["data"][0]
    
    # 2. Chat completions simulation / skeletal resolution
    # Let's mock the provider client to return dummy text
    from unittest.mock import AsyncMock, patch
    
    mock_client = AsyncMock()
    mock_client.chat_completion.return_value = "Mocked chat completions response"
    mock_client.has_api_key.return_value = True
    
    with patch.object(client.app.state.model_service, "get_provider_client", return_value=mock_client), \
         patch("os.environ.get", return_value="some_key"):
        payload = {
            "model": "role:Planner",
            "messages": [{"role": "user", "content": "hello planner"}],
            "max_tokens": 100
        }
        r_chat = client.post("/v1/chat/completions", json=payload)
        assert r_chat.status_code == 200
        body_chat = r_chat.json()
        assert body_chat["object"] == "chat.completion"
        assert body_chat["choices"][0]["message"]["content"] == "Mocked chat completions response"
        assert body_chat["usage"]["prompt_tokens"] > 0
