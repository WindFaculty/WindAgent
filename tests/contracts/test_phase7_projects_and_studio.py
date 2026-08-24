"""
Phase 7 Contract Test Suite — Projects + Studio Convergence.
Verifies canonical V3 Projects, Episodes, Templates, Idempotency, and Optimistic Concurrency.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from tests.support.api import isolated_api_client


@pytest.fixture
def client(monkeypatch, tmp_path):
    yield from isolated_api_client(monkeypatch, tmp_path, profile="demo")


class TestPhase7ProjectsAndStudioContracts:
    def test_list_projects_contract(self, client: TestClient):
        """Verify GET /api/v3/projects returns canonical ProjectListResponse."""
        response = client.get("/api/v3/projects")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "page_info" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1

        proj = data["items"][0]
        assert "id" in proj
        assert "name" in proj
        assert "version" in proj
        assert "episodes_count" in proj
        assert "created_at" in proj
        assert "updated_at" in proj

    def test_filter_and_search_projects_contract(self, client: TestClient):
        """Verify search and genre query filtering."""
        response = client.get("/api/v3/projects?search=Cyberpunk")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        assert "Cyberpunk" in data["items"][0]["name"]

        response_genre = client.get("/api/v3/projects?genre=High%20Fantasy%20/%20Adventure")
        assert response_genre.status_code == 200
        data_genre = response_genre.json()
        assert len(data_genre["items"]) >= 1

    def test_create_project_with_idempotency(self, client: TestClient):
        """Verify POST /api/v3/projects with Idempotency-Key header creates project idempotently."""
        idempotency_key = str(uuid.uuid4())
        payload = {
            "name": f"Test Project {idempotency_key[:6]}",
            "description": "Integration test project logline",
            "genre": "Cyberpunk / Sci-Fi",
            "initial_episode_title": "Tập 01: Thử Nghiệm",
        }

        # First request
        res1 = client.post("/api/v3/projects", json=payload, headers={"Idempotency-Key": idempotency_key})
        assert res1.status_code == 201
        data1 = res1.json()
        project_id = data1["id"]
        assert data1["name"] == payload["name"]
        assert data1["episodes_count"] == 1

        # Duplicate submission with same Idempotency-Key
        res2 = client.post("/api/v3/projects", json=payload, headers={"Idempotency-Key": idempotency_key})
        assert res2.status_code in [200, 201]
        data2 = res2.json()
        assert data2["id"] == project_id

    def test_get_project_detail_and_not_found(self, client: TestClient):
        """Verify GET /api/v3/projects/{id} returns detail or 404."""
        res_ok = client.get("/api/v3/projects/proj-cyberpunk-01")
        assert res_ok.status_code == 200
        assert res_ok.json()["id"] == "proj-cyberpunk-01"

        res_404 = client.get("/api/v3/projects/non-existent-proj-999")
        assert res_404.status_code == 404

    def test_update_project_optimistic_locking(self, client: TestClient):
        """Verify PATCH /api/v3/projects/{id} verifies version and returns 409 on conflict."""
        # Create a fresh project for mutation testing
        create_res = client.post("/api/v3/projects", json={"name": "Locking Test Project"})
        assert create_res.status_code == 201
        proj = create_res.json()
        proj_id = proj["id"]
        initial_version = proj["version"]

        # Conflict test: send stale version
        conflict_res = client.patch(
            f"/api/v3/projects/{proj_id}",
            json={"name": "Stale Update", "expected_version": initial_version + 99},
        )
        assert conflict_res.status_code == 409
        assert "conflict" in conflict_res.json()["detail"].lower()

        # Success test: send correct version
        success_res = client.patch(
            f"/api/v3/projects/{proj_id}",
            json={"name": "Updated Title", "description": "New description", "expected_version": initial_version},
        )
        assert success_res.status_code == 200
        updated = success_res.json()
        assert updated["name"] == "Updated Title"
        assert updated["version"] == initial_version + 1

    def test_list_and_create_episodes_contract(self, client: TestClient):
        """Verify GET and POST /api/v3/projects/{id}/episodes."""
        proj_id = "proj-cyberpunk-01"

        # List existing episodes
        list_res = client.get(f"/api/v3/projects/{proj_id}/episodes")
        assert list_res.status_code == 200
        episodes = list_res.json()["items"]
        assert len(episodes) >= 1

        # Create new episode with idempotency
        idempotency_key = str(uuid.uuid4())
        ep_payload = {"title": f"Tập Mới {idempotency_key[:4]}", "episode_number": len(episodes) + 1}
        create_res = client.post(
            f"/api/v3/projects/{proj_id}/episodes",
            json=ep_payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert create_res.status_code == 201
        new_ep = create_res.json()
        assert new_ep["project_id"] == proj_id
        assert new_ep["title"] == ep_payload["title"]

        # Check project updated episode count
        proj_res = client.get(f"/api/v3/projects/{proj_id}")
        assert proj_res.json()["episodes_count"] >= len(episodes) + 1

    def test_project_templates_contract(self, client: TestClient):
        """Verify GET /api/v3/project-templates returns list of curated starter templates."""
        response = client.get("/api/v3/project-templates")
        assert response.status_code == 200
        templates = response.json()
        assert isinstance(templates, list)
        assert len(templates) >= 4

        tmpl = templates[0]
        assert "id" in tmpl
        assert "title" in tmpl
        assert "description" in tmpl
        assert "genre" in tmpl
        assert "initial_episode" in tmpl
        assert "accent_color" in tmpl
