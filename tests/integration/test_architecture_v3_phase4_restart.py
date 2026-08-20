"""Phase 4 — durable single authority: V3 resource survives full API restart.

P4-R2: a V3 resource created through API instance A survives full
client/lifespan/container shutdown and is read through a fresh API instance B
using the same persistent temporary SQLite database.

This is an HTTP integration test (not a repository/service reopen test). Each
app lifespan creates its own ApplicationContainer, DatabaseManager,
V3ResourceService, UoW sessions, and repository instances while pointing at the
same SQLite file. No module-level mutable authority is shared.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from windagent_api.lifespan import lifespan
from windagent_api.routers.v3 import v3_router


def _build_app() -> FastAPI:
    """A fresh FastAPI instance with the production lifespan and canonical V3
    router tree. Each call yields an independent app whose lifespan builds its
    own container from the current WINDAGENT_DATABASE_URL."""
    app = FastAPI(lifespan=lifespan)
    app.include_router(v3_router)
    return app


def test_v3_resource_survives_full_api_restart(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "p4_r2_restart.db"
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    # Explicit non-production environment; explicitly not the demo profile.
    monkeypatch.setenv("WINDAGENT_ENV", "test")
    monkeypatch.setenv("WINDAGENT_PROFILE", "test")

    # --- App A: create a uniquely named project through HTTP ---
    app_a = _build_app()
    with TestClient(app_a) as client_a:
        container_a = app_a.state.container
        service_a = container_a.v3_resource_service

        # A fresh DB must not contain any demo seed.
        listed = client_a.get("/api/v3/projects/")
        assert listed.status_code == 200, listed.text
        assert listed.json()["items"] == []

        created = client_a.post(
            "/api/v3/projects/",
            json={
                "name": "P4-R2 durable project",
                "description": "Created through API instance A, read through B",
                "genre": "durability",
            },
        )
        assert created.status_code == 201, created.text
        created_body = created.json()
        project_id = created_body["id"]
        assert project_id.startswith("proj-")
        assert created_body["name"] == "P4-R2 durable project"
        assert created_body["description"] == (
            "Created through API instance A, read through B"
        )
        assert created_body["metadata"].get("genre") == "durability"

    # App A's client/lifespan/container fully shut down here.

    # --- App B: fresh app/container, read the same resource ---
    app_b = _build_app()
    assert app_b is not app_a
    with TestClient(app_b) as client_b:
        container_b = app_b.state.container
        service_b = container_b.v3_resource_service

        # Distinct identities between A and B.
        assert container_b is not container_a
        assert container_b.db is not container_a.db
        assert service_b is not service_a

        got = client_b.get(f"/api/v3/projects/{project_id}")
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["id"] == project_id
        assert body["name"] == "P4-R2 durable project"
        assert body["description"] == (
            "Created through API instance A, read through B"
        )
        assert body["metadata"].get("genre") == "durability"
        assert body["version"] == created_body["version"]
        # Timestamps are persisted on the row and survive the restart; the
        # repository normalizes their string form on the SQLite round-trip, so
        # assert presence rather than byte-for-byte equality.
        assert body["created_at"]
        assert body["updated_at"]
