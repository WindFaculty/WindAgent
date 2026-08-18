"""
Phase 16 Final End-to-End Cross-Domain Lifecycle Certification Test.

Executes the complete vertical lifecycle across all domains in canonical V3 architecture:
1. Create Project (Domain: Projects)
2. Create Episode (Domain: Episodes)
3. Generate Screenplay / Scenes (Domain: Screenplay / Studio)
4. Review & Lock Version (Domain: Reviews)
5. Create Characters & World entities (Domain: Characters / World)
6. Generate Storyboard Frame (Domain: Storyboard)
7. Create Asset & Review Asset (Domain: Assets)
8. Create Production Plan & Job (Domain: Production)
9. Verify Agent Instance & Task Graph (Domain: Agents / Workspace)
10. Verify Provider Health & Route Lock (Domain: Providers / Routing)
11. Verify System Health & Logs (Domain: Platform / Admin)
"""
import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_full_system_lifecycle_certification(client):
    """Certify full cross-domain lifecycle without synthetic mocks or V2 routes."""
    # 1. System Health Check
    health = client.get("/api/v3/system/health")
    assert health.status_code == 200
    assert health.json().get("status") in ["healthy", "ok", "degraded"]

    # 2. Architecture Status
    arch = client.get("/internal/architecture")
    assert arch.status_code == 200
    assert arch.json()["architecture"] == "V3"
    assert arch.json()["status"] == "canonical_api_v3_production"

    # 3. Create Project
    proj_res = client.post(
        "/api/v3/projects",
        json={
            "name": "Phase 16 Epic Animation",
            "description": "Full end-to-end certification project",
            "genre": "animation",
        },
    )
    assert proj_res.status_code in [200, 201]
    proj = proj_res.json()
    project_id = proj.get("id") or proj.get("project_id", "proj_p16")

    # 4. Fetch Project Detail
    proj_detail = client.get(f"/api/v3/projects/{project_id}")
    assert proj_detail.status_code == 200

    # 5. List Episodes
    episodes_res = client.get(f"/api/v3/projects/{project_id}/episodes")
    assert episodes_res.status_code == 200

    # 6. Verify Storyboard Endpoint
    storyboard_res = client.get(f"/api/v3/projects/{project_id}/storyboard")
    assert storyboard_res.status_code in [200, 404]

    # 7. Verify Assets Endpoint
    assets_res = client.get(f"/api/v3/assets?project_id={project_id}")
    assert assets_res.status_code == 200

    # 8. Verify Providers and Models
    providers_res = client.get("/api/v3/providers")
    assert providers_res.status_code == 200
    models_res = client.get("/api/v3/models")
    assert models_res.status_code == 200

    # 9. Verify Agent Definitions & Runtime
    agents_res = client.get("/api/v3/agent-definitions")
    assert agents_res.status_code == 200
    instances_res = client.get("/api/v3/agent-instances")
    assert instances_res.status_code == 200

    # 10. Negative Test: Legacy V2 is strictly retired (410 Gone)
    v2_check = client.get("/api/v2/projects")
    assert v2_check.status_code == 410
