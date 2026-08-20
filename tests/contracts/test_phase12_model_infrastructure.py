"""
Phase 12 — Models, Providers & Routing Infrastructure Contract Tests.
Verifies:
- Canonical Model Registry & Capability Matrices
- Provider Registry, Physical Endpoints & Secure Credential Status (No raw secrets)
- Provider Connection Testing & Live Model Discovery Handshake
- Priority-based Versioned Routing Rules & Optimistic Concurrency
- Routing Graph Topology & Traffic Metrics
- Simulation & Explainable RouteDecision with Route Lock Audit
- End-to-end Model Infrastructure Integration
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


# ─────────────────────────────────────────────────────────────────────────────
# Phase 12.2 — Models API
# ─────────────────────────────────────────────────────────────────────────────

class TestModelsApi:
    def test_list_canonical_models(self, client):
        r = client.get("/api/v3/models")
        assert r.status_code == 200
        models = r.json()
        assert isinstance(models, list)
        assert len(models) >= 5
        model_ids = {m["id"] for m in models}
        assert "anthropic/claude-3-5-sonnet" in model_ids
        assert "google/gemini-1.5-pro" in model_ids
        assert "openai/gpt-4o" in model_ids

    def test_filter_models_by_provider(self, client):
        r = client.get("/api/v3/models", params={"provider": "google"})
        assert r.status_code == 200
        models = r.json()
        assert len(models) >= 2
        for m in models:
            assert m["vendor"].lower() == "google" or any(b["provider_id"] == "google" for b in m["bindings"])

    def test_filter_models_by_capability(self, client):
        r = client.get("/api/v3/models", params={"capability": "reasoning"})
        assert r.status_code == 200
        models = r.json()
        assert len(models) >= 2
        for m in models:
            assert "reasoning" in m["capabilities"]

    def test_filter_models_by_local(self, client):
        r = client.get("/api/v3/models", params={"is_local": True})
        assert r.status_code == 200
        models = r.json()
        assert len(models) >= 1
        for m in models:
            assert m["is_local"] is True

    def test_get_model_detail(self, client):
        r = client.get("/api/v3/models/anthropic/claude-3-5-sonnet")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Claude 3.5 Sonnet"
        assert data["context_window"] == 200000
        assert "tools" in data["capabilities"]
        assert len(data["bindings"]) >= 1
        assert "benchmarks" in data

    def test_get_model_not_found(self, client):
        r = client.get("/api/v3/models/non-existent/model-xyz")
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Phase 12.1 & 12.2 — Providers API & Secure Credential Status
# ─────────────────────────────────────────────────────────────────────────────

class TestProvidersApi:
    def test_list_providers(self, client):
        r = client.get("/api/v3/providers")
        assert r.status_code == 200
        providers = r.json()
        assert isinstance(providers, list)
        assert len(providers) >= 4
        provider_ids = {p["id"] for p in providers}
        assert "google" in provider_ids
        assert "anthropic" in provider_ids
        assert "openai" in provider_ids
        assert "ollama" in provider_ids

    def test_provider_detail_and_no_secrets_exposed(self, client):
        r = client.get("/api/v3/providers/anthropic")
        assert r.status_code == 200
        data = r.json()
        assert data["display_name"] == "Anthropic"
        assert data["status"] == "healthy"
        assert len(data["endpoints"]) >= 1

        # Check endpoints and ensure raw secrets are never returned
        for ep in data["endpoints"]:
            assert "base_url" in ep
            assert "is_configured" in ep
            assert "status" in ep
            assert "latency_ms" in ep
            # Ensure no secret fields like api_key or secret
            assert "api_key" not in ep
            assert "secret" not in ep
            assert "token" not in ep

    def test_get_provider_models(self, client):
        r = client.get("/api/v3/providers/google/models")
        assert r.status_code == 200
        models = r.json()
        assert len(models) >= 2
        for m in models:
            assert m["vendor"].lower() == "google" or any(b["provider_id"] == "google" for b in m["bindings"])

    def test_get_provider_endpoints(self, client):
        r = client.get("/api/v3/providers/google/endpoints")
        assert r.status_code == 200
        endpoints = r.json()
        assert len(endpoints) >= 2
        assert any(ep["id"] == "ep-google-ai-studio" for ep in endpoints)

    def test_get_providers_health(self, client):
        r = client.get("/api/v3/providers/health")
        assert r.status_code == 200
        health = r.json()
        assert "google" in health
        assert "anthropic" in health
        assert health["google"]["status"] == "healthy"
        assert "avg_latency_ms" in health["google"]


# ─────────────────────────────────────────────────────────────────────────────
# Phase 12.3 — Provider Connection Testing
# ─────────────────────────────────────────────────────────────────────────────

class TestProviderConnectionTesting:
    def test_connection_handshake(self, client):
        r = client.post("/api/v3/providers/google/test-connection")
        assert r.status_code == 200
        res = r.json()
        assert res["provider_id"] == "google"
        assert res["reachable"] is True
        assert res["auth_valid"] is True
        assert res["latency_ms"] > 0
        assert len(res["model_discovery"]) >= 1
        assert "test_id" in res
        assert "completed_at" in res

    def test_connection_test_target_endpoint(self, client):
        r = client.post(
            "/api/v3/providers/google/test-connection",
            json={"endpoint_id": "ep-google-vertex"},
        )
        assert r.status_code == 200
        res = r.json()
        assert res["endpoint_id"] == "ep-google-vertex"
        assert res["reachable"] is True

    def test_connection_test_unknown_provider(self, client):
        r = client.post("/api/v3/providers/unknown-xyz/test-connection")
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Phase 12.4 — Routing Rules & Optimistic Concurrency
# ─────────────────────────────────────────────────────────────────────────────

class TestRoutingRulesApi:
    def test_list_rules_ordered_by_priority(self, client):
        r = client.get("/api/v3/routing/rules")
        assert r.status_code == 200
        rules = r.json()
        assert isinstance(rules, list)
        assert len(rules) >= 4
        # Verify priority ordering
        priorities = [rule["priority"] for rule in rules]
        assert priorities == sorted(priorities)

    def test_create_routing_rule(self, client):
        payload = {
            "name": "Custom Code Reviewer Policy",
            "canonical_model_id": "deepseek/deepseek-r1",
            "fallback_model_id": "anthropic/claude-3-5-sonnet",
            "description": "Rule for strict automated code review",
            "priority": 15,
            "agent_types": ["Reviewer", "SecurityAuditor"],
            "required_capabilities": ["code", "reasoning"],
        }
        r = client.post("/api/v3/routing/rules", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["id"].startswith("rule-")
        assert data["name"] == "Custom Code Reviewer Policy"
        assert data["version"] == 1
        assert data["priority"] == 15

    def test_get_routing_rule_detail(self, client):
        r = client.get("/api/v3/routing/rules/rule-planner-core")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "rule-planner-core"
        assert data["canonical_model_id"] == "anthropic/claude-3-5-sonnet"

    def test_update_routing_rule_optimistic_locking(self, client):
        r = client.get("/api/v3/routing/rules/rule-code-agent")
        assert r.status_code == 200
        current = r.json()
        cur_version = current["version"]

        # Conflict check with stale expected_version
        r_conf = client.patch(
            "/api/v3/routing/rules/rule-code-agent",
            json={"priority": 5, "expected_version": cur_version + 99},
        )
        assert r_conf.status_code == 409

        # Successful update
        r_ok = client.patch(
            "/api/v3/routing/rules/rule-code-agent",
            json={"priority": 8, "expected_version": cur_version},
        )
        assert r_ok.status_code == 200
        assert r_ok.json()["version"] == cur_version + 1
        assert r_ok.json()["priority"] == 8

    def test_delete_routing_rule(self, client):
        # Create temp rule
        r_create = client.post(
            "/api/v3/routing/rules",
            json={
                "name": "Temp Rule for Deletion",
                "canonical_model_id": "google/gemini-1.5-flash",
            },
        )
        assert r_create.status_code == 201
        rule_id = r_create.json()["id"]

        # Delete rule
        r_del = client.delete(f"/api/v3/routing/rules/{rule_id}")
        assert r_del.status_code == 200
        assert r_del.json()["deleted"] is True

        # Verify not found
        r_check = client.get(f"/api/v3/routing/rules/{rule_id}")
        assert r_check.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Phase 12.4 & 12.5 — Routing Topology Graph, Metrics & Explainable Simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestRoutingSimulationAndDecisions:
    def test_get_routing_graph(self, client):
        r = client.get("/api/v3/routing/graph")
        assert r.status_code == 200
        graph = r.json()
        assert "nodes" in graph
        assert "links" in graph
        node_types = {n["type"] for n in graph["nodes"]}
        assert "role" in node_types
        assert "rule" in node_types
        assert "model" in node_types

    def test_get_routing_metrics(self, client):
        r = client.get("/api/v3/routing/metrics")
        assert r.status_code == 200
        metrics = r.json()
        assert metrics["total_routes"] > 0
        assert metrics["active_rules"] > 0
        assert metrics["avg_latency_ms"] > 0
        assert metrics["success_rate_percent"] > 90
        assert len(metrics["traffic_distribution"]) >= 3

    def test_simulate_route_decision_explainability(self, client):
        payload = {
            "role": "Coordinator",
            "prompt": "Create an overarching episode structure for Season 1 Episode 2.",
            "estimated_tokens": 12000,
            "required_capabilities": ["reasoning", "tools"],
        }
        r = client.post("/api/v3/routing/simulations", json=payload)
        assert r.status_code == 200
        decision = r.json()

        assert decision["requested_role"] == "Coordinator"
        assert decision["canonical_model_id"] == "anthropic/claude-3-5-sonnet"
        assert "rule_id" in decision
        assert "reason" in decision
        assert decision["route_lock_id"].startswith("lock-")
        assert len(decision["fallback_chain"]) >= 1

        # Audit route lock explanation
        lock_id = decision["route_lock_id"]
        r_lock = client.get(f"/api/v3/routing/locks/{lock_id}")
        assert r_lock.status_code == 200
        lock_detail = r_lock.json()
        assert lock_detail["lock_id"] == lock_id
        assert lock_detail["canonical_model_id"] == decision["canonical_model_id"]
        assert "routing_snapshot" in lock_detail


# ─────────────────────────────────────────────────────────────────────────────
# Phase 12.10 — End-to-End Integration Flow
# ─────────────────────────────────────────────────────────────────────────────

class TestModelInfraIntegration:
    def test_full_model_infra_flow(self, client):
        # 1. Fetch available models
        r_models = client.get("/api/v3/models")
        assert r_models.status_code == 200
        models = r_models.json()
        claude_model = next(m for m in models if m["id"] == "anthropic/claude-3-5-sonnet")
        assert claude_model["context_window"] == 200000

        # 2. Test provider connection for the bound provider
        bound_provider = claude_model["bindings"][0]["provider_id"]
        r_test = client.post(f"/api/v3/providers/{bound_provider}/test-connection")
        assert r_test.status_code == 200
        assert r_test.json()["reachable"] is True

        # 3. Simulate routing decision for Planner
        r_sim = client.post(
            "/api/v3/routing/simulations",
            json={"role": "Planner", "prompt": "Outline scenes for Episode 1"},
        )
        assert r_sim.status_code == 200
        sim = r_sim.json()
        assert sim["canonical_model_id"] == "anthropic/claude-3-5-sonnet"
        assert len(sim["fallback_chain"]) >= 1

        # 4. Verify Route Lock persisted
        lock_id = sim["route_lock_id"]
        r_lock = client.get(f"/api/v3/routing/locks/{lock_id}")
        assert r_lock.status_code == 200
        assert r_lock.json()["canonical_model_id"] == "anthropic/claude-3-5-sonnet"
