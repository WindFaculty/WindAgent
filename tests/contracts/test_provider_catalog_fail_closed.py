"""Provider/model catalog must never expose demo rows outside demo profile."""

from __future__ import annotations


def test_default_profile_exposes_only_durable_provider_state(no_demo_client):
    providers = no_demo_client.get("/api/v3/providers")
    health = no_demo_client.get("/api/v3/providers/health")
    models = no_demo_client.get("/api/v3/models")

    assert providers.status_code == 200
    assert providers.json() == []
    assert health.status_code == 200
    assert health.json() == {}
    assert models.status_code == 200
    assert models.json() == []


def test_default_profile_does_not_resolve_catalog_only_ids(no_demo_client):
    assert no_demo_client.get("/api/v3/providers/openai").status_code == 404
    assert no_demo_client.get("/api/v3/providers/openai/models").status_code == 404
    assert no_demo_client.get("/api/v3/providers/openai/endpoints").status_code == 404
    assert no_demo_client.get("/api/v3/providers/openai/health").status_code == 404
    assert no_demo_client.post("/api/v3/providers/openai/test-connection").status_code == 404
    assert no_demo_client.get("/api/v3/models/gpt-4o").status_code == 404
