"""
API retirement contract tests (Architecture V3).

V1 and V2 are permanently retired (Phase 8 / Phase 15): every /api/v1/* and
/api/v2/* request must return 410 Gone pointing at /api/v3/*. The canonical
surface is /api/v3/*.
"""

from fastapi.testclient import TestClient
from windagent_api.main import app

client = TestClient(app)


def test_health_and_architecture_endpoints():
    r1 = client.get("/health/live")
    assert r1.status_code == 200
    assert r1.json()["status"] == "live"

    r2 = client.get("/internal/architecture")
    assert r2.status_code == 200
    assert r2.json()["architecture"] == "V3"
    assert r2.json()["status"] == "canonical_api_v3_production"
    assert r2.json()["api_version"] == "v3"


def test_api_v2_tombstone_returns_410():
    """All V2 endpoints return 410 Gone after Phase 15 retirement."""
    for method, path, payload in (
        ("post", "/api/v2/tasks", {"prompt": "test"}),
        ("get", "/api/v2/tasks", None),
        ("get", "/api/v2/runs", None),
        ("get", "/api/v2/workflows", None),
        ("get", "/api/v2/events", None),
        ("get", "/api/v2/providers", None),
        ("get", "/api/v2/tools", None),
        ("get", "/api/v2/artifacts", None),
        ("get", "/api/v2/evals/reports", None),
    ):
        if payload is None:
            res = getattr(client, method)(path)
        else:
            res = getattr(client, method)(path, json=payload)
        assert res.status_code == 410, f"{method.upper()} {path} -> {res.status_code}"
        body = res.json()
        assert body["title"] == "API V2 Retired"
        assert body["status"] == 410
        assert "/api/v3" in body["detail"]
        assert res.headers.get("Deprecation") == "true"


def test_api_v1_tombstone_returns_410():
    """Test that all V1 endpoints return 410 Gone after removal."""
    # Test GET /api/v1/tasks
    r_v1_get = client.get("/api/v1/tasks")
    assert r_v1_get.status_code == 410
    assert r_v1_get.json()["title"] == "API V1 Removed"
    assert r_v1_get.json()["detail"] == "API V1 has been permanently removed. Please migrate to API V3."

    # Test POST /api/v1/tasks
    r_v1_post = client.post("/api/v1/tasks", json={"prompt": "test"})
    assert r_v1_post.status_code == 410
    assert r_v1_post.json()["status"] == 410

    # The parity matrix concept died with V2: now behind the V2 tombstone.
    r_parity = client.get("/api/v2/parity-matrix")
    assert r_parity.status_code == 410


def test_api_v3_is_canonical_surface():
    """The canonical V3 API answers on its system/health surface."""
    r_system = client.get("/api/v3/system/health")
    assert r_system.status_code == 200
